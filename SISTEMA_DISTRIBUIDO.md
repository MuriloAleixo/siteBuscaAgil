# BuscaAgil Como Sistema Distribuído

Este documento explica a arquitetura do BuscaAgil pelo ângulo de sistemas
distribuídos: quais componentes existem, como eles se comunicam, e quais
propriedades clássicas (desacoplamento, assincronia, tolerância a falha,
escalabilidade, consistência eventual, concorrência) o projeto satisfaz —
mesmo sendo uma aplicação pequena. Serve de roteiro para uma apresentação.

## 1. Visão Geral Dos Componentes

O sistema não é um processo único: são pelo menos **cinco processos/serviços
independentes**, que podem rodar em máquinas diferentes, que se comunicam
por rede/IPC em vez de chamada de função direta:

| Componente | Papel | Onde vive no código |
|---|---|---|
| **Servidor web (Django)** | Recebe o upload, responde à requisição HTTP do usuário | `core/views.py` |
| **Broker de mensagens (Redis)** | Fila que guarda as tarefas pendentes entre o web e o worker | `busca_agil/settings.py` (`CELERY_BROKER_URL`) |
| **Worker (Celery)** | Consome a fila e executa o trabalho pesado (classificação + upload) em segundo plano | `core/tasks.py`, `busca_agil/celery.py` |
| **Serviço externo (API Gemini)** | Serviço de terceiros, fora do nosso controle, chamado pela rede | `scripts/categorizer_gemini.py` |
| **Serviço externo (Google OAuth + Drive API)** | Autenticação do usuário e armazenamento definitivo dos arquivos/catálogo, fora do nosso controle | `core/google_drive.py`, `django-allauth` |
| **Cache local por usuário** | Cópia local, best-effort, do catálogo que mora no Drive — não é fonte da verdade | `data/users/<id>.json` (`core/uploaded_files_store.py`) |

Esses componentes não compartilham memória: eles trocam **mensagens**
(tarefas na fila), **chamadas de API remotas** (Gemini, Google OAuth/Drive)
e **estado em arquivos**, exatamente como processos distintos em um sistema
distribuído real trocariam mensagens via rede e estado via um
banco/storage compartilhado.

## 2. Desacoplamento Via Fila De Mensagens (Producer/Consumer)

`upload_files` (`core/views.py`) é o **produtor**: ele não sabe *quem*
vai processar a classificação, nem *quando*. Ele só publica uma tarefa na
fila e segue em frente:

```python
async_result = classify_and_catalog_task.delay(
    request.user.id, saved_name, storage.path(saved_name), uploaded_file.name
)
```

O **worker Celery** é o **consumidor**: um processo totalmente separado,
iniciado independentemente (`celery -A busca_agil worker`), que fica
observando a fila no Redis e processa o que aparecer.

Isso é o padrão clássico de **desacoplamento produtor/consumidor** via
message broker:

- o produtor e o consumidor não precisam estar no ar ao mesmo tempo;
- o produtor não trava esperando resposta (baixa latência percebida pelo
  usuário: o upload responde na hora, com status `"processing"`);
- dá pra escalar os dois lados de forma independente (mais workers, mais
  instâncias web) sem tocar no outro lado.

Prova concreta disso: quando o worker esteve fora do ar (ver histórico
desta conversa), a tarefa continuou **persistida na fila do Redis**
esperando um consumidor — o sistema não perdeu a mensagem, só ficou
"pausado" até um worker aparecer. Isso é durabilidade de mensagens, uma
propriedade central de brokers como Redis/RabbitMQ/Kafka.

## 3. Processamento Assíncrono E Consistência Eventual

O fluxo de upload é deliberadamente **assíncrono**: a resposta HTTP não
espera a classificação nem o envio ao Drive terminarem.

```text
Cliente        Web (Django)         Fila (Redis)      Worker (Celery)      Gemini API     Google Drive
  │ POST /upload    │                     │                  │                 │               │
  ├─────────────────▶ salva local (temp)  │                  │                 │               │
  │                 ├─ entry status="processing" ──▶ data/users/<id>.json      │               │
  │                 ├─ publica tarefa ─────▶│                  │                 │               │
  │ 200 OK (processing) ◀──                │                  │                 │               │
  │                 │                     │  consome tarefa ▶│                 │               │
  │                 │                     │                  ├─ classifica ────▶│               │
  │                 │                     │                  │◀─ categoria/tags ┤               │
  │                 │                     │                  ├─ sobe o arquivo ─────────────────▶│
  │                 │                     │                  │◀───────────────── file_id/link ───┤
  │                 │                     │                  ├─ atualiza catálogo local           │
  │                 │                     │                  ├─ sobe catálogo atualizado ─────────▶│
  │                 │                     │                  ├─ apaga o arquivo local              │
  │ GET /files/<id>/status                │                  │                 │               │
  ├─────────────────▶ lê data/users/<id>.json                │                 │               │
  │◀─ status="done", url=link do Drive ───┤                  │                 │               │
```

Isso é **consistência eventual**: logo após o upload, o estado do sistema é
inconsistente com o "resultado final" (o arquivo existe localmente, mas
ainda não tem categoria/tags nem está no Drive). O cliente não vê um erro
por isso — ele faz *polling* no endpoint `GET /files/<id>/status`
(`core/views.py`, `file_status`) até o status convergir para `"done"`
(quando o `url` retornado já é o link do Drive, não mais o arquivo local)
ou `"error"`. Não há bloqueio, não há espera síncrona: o sistema converge
com o tempo, não instantaneamente.

## 4. Tolerância A Falhas E Degradação Graciosa

O worker isola a classificação num `try/except` próprio, separado da
tentativa de upload pro Drive (`core/tasks.py`, `_classify_best_effort` e
`_run_file_upload`):

```python
def _classify_best_effort(origem: str) -> dict | None:
    try:
        return processar_upload(origem, catalog_path=CATALOG_PATH)
    except Exception as exc:
        logger.warning("Não foi possível classificar '%s': %s", origem, exc)
        return None
```

Se o Gemini cair, ficar lento, devolver erro, ou faltar a `GEMINI_API_KEY`,
**o upload pro Drive não é cancelado** — o arquivo sobe mesmo assim, só sem
categoria/tags, e o usuário ainda pode categorizar manualmente
(`update_file_metadata`, `core/views.py`). O mesmo princípio aparece na
busca assistida (`smart_search`, `core/views.py`): se o Gemini falhar, cai
num fallback de busca por substring.

Já uma falha do **Drive em si** (token expirado sem refresh, API fora do
ar) é tratada de forma diferente e mais conservadora: o worker **não apaga
o arquivo local** nesse caso (`core/tasks.py`, bloco `except` em
`_run_file_upload`) — perder a classificação é aceitável, perder o arquivo
que o usuário enviou não é. Isso é uma escolha explícita de qual falha
degrada graciosamente (classificação) e qual não pode simplesmente ser
engolida (armazenamento).

Isso é o princípio de **degradação graciosa / isolamento de falhas**: a
falha de um componente remoto (dependência externa não confiável, típica
de sistemas distribuídos) não deve derrubar o sistema inteiro — só reduz
funcionalidade daquela parte, e a severidade da degradação é proporcional
ao que está em jogo.

## 5. Escalabilidade Horizontal Independente

Como produtor (web) e consumidor (worker) são processos separados
conectados só pela fila, cada lado escala **independentemente**:

- Pico de uploads → sobe mais processos `celery worker` apontando para o
  mesmo Redis, sem tocar no Django.
- Pico de tráfego de navegação → sobe mais instâncias do Django atrás de
  um load balancer, sem tocar nos workers.

Isso é a essência de **escalabilidade horizontal** em sistemas
distribuídos: unidades de trabalho (tarefas na fila) podem ser consumidas
por N workers concorrentes, sem coordenação direta entre eles — o Redis
arbitra quem pega qual tarefa.

## 6. Concorrência E Exclusão Mútua No Estado Compartilhado

`data/users/<id>.json` é **estado compartilhado** entre o processo web (que
grava a entry no upload e lê no polling) e N processos worker (que
atualizam o status ao final da classificação/upload) — para aquele mesmo
usuário. Múltiplos processos escrevendo no mesmo arquivo ao mesmo tempo é
uma receita clássica de corrupção de dados/condição de corrida.

O projeto resolve isso com um **lock distribuído baseado em arquivo**
(`core/uploaded_files_store.py`, via `filelock.FileLock`), um lock **por
usuário**:

```python
with FileLock(_lock_path(user_id), timeout=_LOCK_TIMEOUT_SECONDS):
    files = _read_json(user_id)
    ...
    _write_json(user_id, files)
```

Isso é o mesmo problema (e a mesma solução conceitual) de bancos
distribuídos que usam locks/leases para serializar escritas concorrentes:
seção crítica protegida, timeout para não travar para sempre, e escrita
atômica em disco (grava em `.tmp` e faz `os.replace`, evitando estado
parcial/corrompido se o processo morrer no meio da escrita).

## 7. Fonte Da Verdade Na Nuvem + Cache Local Sincronizado No Login

Diferente da versão anterior do projeto (arquivo local era o único lugar
onde os dados existiam), agora o **Google Drive do próprio usuário é a
fonte da verdade**: cada usuário tem uma pasta `buscaagil_upload` no seu
Drive contendo os arquivos enviados e um `uploaded_files.json` com o
catálogo (`core/google_drive.py`). O `data/users/<id>.json` local é
deliberadamente só um **cache read-through**, nunca a origem do dado.

O ponto onde isso fica explícito é o login. `post_login_sync`
(`core/views.py`) roda **antes de qualquer página carregar**
(`settings.LOGIN_REDIRECT_URL = "/post-login/"`): garante que a pasta do
usuário existe no Drive (cria se for o primeiro login), baixa o
`uploaded_files.json` de lá pro cache local, e só então libera o dashboard.
Se essa sincronização falhar, o usuário nem chega a ver dados
potencialmente desatualizados — é redirecionado pra uma tela de erro/retry
(`auth.html`) em vez de continuar com um cache velho ou vazio por engano.

```text
Login com Google (allauth)
        │
        ▼
post_login_sync (view, síncrona, roda ANTES do dashboard)
        │
        ├── garante pasta "buscaagil_upload" no Drive do usuário
        ├── baixa uploaded_files.json do Drive ──▶ escreve data/users/<id>.json
        ├── lê cota de armazenamento do Drive
        │
        ├── sucesso ──▶ redirect /dashboard.html  (cache "quente" e coerente)
        └── falha  ──▶ redirect /auth.html         (erro, oferece retry)
```

Esse é o padrão de **cache-aside com invalidação por sessão**: em vez de
manter o cache local sempre coerente por eventos (o que exigiria o Drive
notificar o BuscaÁgil a cada mudança — não é o caso, Drive não faz push pra
nós), o sistema garante coerência no único momento em que isso é barato e
suficiente: o início da sessão do usuário. Depois disso, o cache local é
quem responde às leituras (`GET /files`) até a próxima escrita, quando o
worker Celery atualiza local e nuvem juntos (`_sync_catalog_to_drive`,
`core/tasks.py`).

## 8. Particionamento De Dados Por Usuário (Multi-Tenancy)

Cada usuário tem seu próprio cache local (`data/users/<user_id>.json`,
particionado por `user_id`) e sua própria pasta no Drive — não existe mais
um catálogo global único visto por todo mundo. Isso é **particionamento
horizontal de dados (sharding) por tenant**: a chave de particionamento é o
próprio usuário, cada partição é independente das outras, e não há
contenção entre usuários diferentes fazendo upload ao mesmo tempo (os locks
do `FileLock` são por arquivo/usuário, não globais).

Esse desenho também resolve, de graça, um problema de acesso que existiria
se o catálogo fosse global mas os arquivos fossem para Drives pessoais
distintos: como cada usuário só enxerga o próprio catálogo, ele nunca vê um
link para um arquivo que não é dele e que não teria permissão de abrir.

## 9. Identidade E Rastreabilidade De Tarefas Assíncronas

Cada tarefa publicada recebe um `task_id` (UUID gerado pelo Celery) que é
guardado junto da entry (`"task_id": async_result.id`). Isso permite
rastrear uma unidade de trabalho específica através de múltiplos processos
e ao longo do tempo — necessário porque, num sistema distribuído, não dá
para simplesmente "voltar no call stack" para saber o que aconteceu com um
pedido: o produtor e o consumidor são processos diferentes, potencialmente
em máquinas diferentes.

## 10. Pontos-Chave Para A Apresentação

Resumo do que destacar como "isso aqui é sistema distribuído, não só
Django":

1. **Múltiplos processos/serviços independentes** (web, broker, worker,
   Gemini, Google OAuth/Drive) que se comunicam por rede, não por chamada
   de função.
2. **Fila de mensagens (Redis)** desacoplando produtor e consumidor —
   comunicação assíncrona, não um simples request/response.
3. **Persistência/durabilidade da fila**: tarefa sobrevive mesmo se o
   worker estiver fora do ar no momento em que ela foi criada.
4. **Consistência eventual** com *polling* de status, em vez de resposta
   síncrona bloqueante.
5. **Tolerância a falhas de dependência externa** (Gemini) com degradação
   graciosa em vez de falha total.
6. **Escalabilidade horizontal independente** de cada componente.
7. **Concorrência controlada** em estado compartilhado via lock com
   timeout e escrita atômica.
8. **Rastreabilidade** de unidades de trabalho assíncronas via ID único.
9. **Fonte da verdade na nuvem (Google Drive) + cache local por sessão**,
   sincronizados no login (`post_login_sync`) — cache-aside, não
   replicação contínua.
10. **Particionamento de dados por usuário (multi-tenancy)**: cada usuário
    tem seu próprio catálogo, sua própria pasta no Drive, seu próprio lock
    — sem contenção nem vazamento de dados entre usuários.

## 11. Limitações Conhecidas (Vale Mencionar Como "Trade-offs")

Para uma apresentação honesta, vale citar o que é simplificado em relação
a um sistema distribuído "de livro-texto":

- O cache local é um **arquivo JSON por usuário com lock de arquivo**, não
  um banco distribuído replicado — funciona bem em uma única máquina (ou
  disco compartilhado), mas não seria a escolha certa entre múltiplas
  instâncias web fisicamente separadas rodando ao mesmo tempo.
- Só existe **um broker Redis**, sem cluster/replicação — é um ponto único
  de falha nesta configuração de desenvolvimento.
- Não há *retry* automático configurado para a tarefa Celery em caso de
  falha transitória do Gemini ou do Drive (a falha vira `status="error"`
  direto, sem nova tentativa).
- A sincronização do cache local com o Drive só acontece no login e depois
  de cada escrita (upload/link) — se o mesmo usuário editar o catálogo por
  fora (direto no Drive, ou em duas abas/dispositivos ao mesmo tempo), o
  cache local pode ficar temporariamente desatualizado até o próximo login
  ou a próxima escrita re-sincronizar. Não há *websocket*/push do Drive
  avisando o BuscaÁgil de mudanças externas.
