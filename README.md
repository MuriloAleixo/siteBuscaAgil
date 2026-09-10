# siteBuscaAgil

Site para buscar suas anotações e arquivos de maneira simples e fácil. Login
exclusivamente com Google, arquivos guardados no seu próprio Google Drive, e
classificação automática (categoria/tags/descrição) via IA — local (Ollama)
ou Gemini.

Pra aprender a **usar** o sistema (login, upload, busca, editar
classificação, excluir arquivos), veja **[GUIA_DE_USO.md](GUIA_DE_USO.md)**.
Este documento aqui é só sobre **instalar e rodar** o projeto. Pra entender
como o código por dentro funciona (containers, fila, por que não tem banco
de dados), veja **[ARQUITETURA.md](ARQUITETURA.md)**.

## Estrutura Do Projeto

Sem framework "cheio" nem banco de dados — cinco peças simples:

- `frontend/` — nginx: serve o HTML/CSS/JS estático e faz proxy das rotas de dados pra `api/`
- `api/` — Flask: login com Google, upload, busca, status da fila
- `worker/` — Celery: consome a fila e roda a classificação + upload pro Drive
- `scripts/` — orquestração de IA (local via Ollama e/ou Gemini), sem dependência de framework
- `static/` — CSS/JS compartilhado entre as páginas em `frontend/pages/`
- pouso temporário de upload em `media/` (arquivo some de lá assim que o worker confirma o envio pro Drive)
- cache local (catálogo + tokens OAuth) por usuário em `data/users/<id>/`

Dentro de `api/`, vale destacar:

- `app.py` — rotas HTTP (upload, busca, exclusão, status, fila)
- `auth.py` — login OAuth2 manual com o Google, sessão (cookie assinado do Flask), `/me`
- `csrf.py` — proteção CSRF (double-submit cookie)
- `google_drive.py` — toda a integração com a Drive API (pasta do usuário, catálogo, upload/download/exclusão de arquivos)
- `stores.py` — leitura/escrita do cache local por usuário (catálogo + perfil), com lock de arquivo — não tem banco de dados nenhum, é tudo JSON em disco
- `text_match.py` — critério único de busca (normalização de acento + fuzzy matching via `rapidfuzz`), usado tanto pelo filtro no backend quanto (portado em JS) pelo fallback local do frontend

Dentro de `worker/`:

- `celery_app.py` — cria o app Celery (broker/backend = Redis)
- `tasks.py` — tarefas assíncronas (classificação + upload pro Drive)

Dentro de `scripts/`:

- `processar_upload.py` — orquestrador: tenta a IA local primeiro (se
  habilitada), cai pro Gemini em qualquer falha. Categoria é **aberta** —
  não existe uma lista fixa de categorias de negócio; cada classificação
  recebe as categorias que o próprio usuário já usou (via `worker/tasks.py`)
  como referência, e cria uma nova se nenhuma servir.
- `local_ai/` — IA local via Ollama (texto, imagem/PDF, vídeo/áudio, busca)
- `categorizer_gemini.py` / `analisador_busca.py` — classificação e busca via Gemini (nuvem)
- `extrator_conteudo.py` — extração de texto de documentos/planilhas/links,
  com tratamento dedicado pra YouTube (título + transcrição/legenda do
  vídeo via `youtube-transcript-api`, sem precisar de API key do YouTube)

O login com Google já autoriza, no mesmo consentimento, o acesso a uma pasta
própria (`buscaagil_upload`) no Drive do usuário — é lá que os arquivos
enviados e o catálogo (`uploaded_files.json`) ficam guardados de verdade.
Local (`media/`, `data/users/`) é só um pouso temporário/cache.

## Instalação

### 1. Pré-requisitos: WSL + Git (Windows)

Se já tem WSL com Ubuntu e o repositório clonado, pule pra
[Rodar Com Docker](#2-rodar-com-docker-recomendado).

No PowerShell do Windows:

```powershell
wsl --install -d Ubuntu
```

Reinicie o Windows se for solicitado. Ao abrir o Ubuntu pela primeira vez,
crie o usuário e a senha do Linux, e rode os comandos abaixo dali em diante.

Se ainda não tiver uma chave SSH associada à sua conta GitHub:

```bash
ssh-keygen -t ed25519 -C "seu_email@exemplo.com"
cat ~/.ssh/id_ed25519.pub   # copie e adicione em GitHub > Settings > SSH and GPG keys
ssh -T git@github.com       # testa a conexão
```

Clone o projeto:

```bash
git clone git@github.com:MuriloAleixo/siteBuscaAgil.git
cd siteBuscaAgil
```

### 2. Rodar Com Docker (Recomendado)

Com Docker instalado (Docker Desktop com integração WSL, ou Docker Engine
direto no WSL) mais o plugin `docker compose`, todo o resto — frontend,
api, worker do Celery, Redis e a IA local (Ollama) — sobe com um único
script, sem precisar instalar Python/venv/Redis/ffmpeg no seu WSL.

1. Configure as credenciais no `.env` (seções **3** e **4** abaixo — os
   passos de configuração de chave são os mesmos, só quem roda o processo
   muda).
2. Rode:

   ```bash
   ./install.sh
   ```

O script builda as imagens, sobe o Ollama, baixa os modelos de IA local,
sobe a api, o worker e o frontend e, ao final, roda uma bateria de
**smoke tests** (Ollama respondendo com os modelos certos, frontend
respondendo em `:80`, worker do Celery respondendo a um ping via broker, e
uma classificação de arquivo de ponta a ponta) — se algum teste crítico
falhar, o script para e mostra o que verificar. Se tudo passar, acesse
`http://localhost/`.

Comandos do dia a dia depois da primeira vez:

```bash
docker compose up -d      # subir tudo de novo
docker compose logs -f    # acompanhar os logs
docker compose down       # parar tudo
```

Pra desfazer tudo (containers, imagens, volumes com os modelos baixados,
cache local) e voltar a um estado zerado — só com o código e os arquivos de
configuração/instrução, pronto pra rodar `./install.sh` de novo do zero:

```bash
./uninstall.sh
```

O script pergunta antes de cada passo destrutivo, inclusive se quer apagar
o `.env` (suas chaves do Gemini/Google) ou mantê-lo.

Se preferir configurar cada peça manualmente (sem Docker) — útil pra
depurar direto —, veja [Rodar Manualmente (Sem Docker)](#6-rodar-manualmente-sem-docker)
mais abaixo. As seções **3**, **4** e **5** valem pros dois jeitos de rodar.

### 3. Configurar Variáveis De Ambiente

Copie o arquivo de exemplo:

```bash
cp .env.example .env
```

Edite o `.env` e defina:

```text
GEMINI_API_KEY=sua_chave_aqui
```

Gere uma chave gratuita em https://aistudio.google.com/apikey. Sem essa
chave o site continua funcional (com a IA local, se habilitada — seção 5 —
ou sem classificação automática).

Opcionalmente, também é possível sobrescrever a conexão do Celery/Redis
definindo no `.env`:

```text
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Se não forem definidas, esses são os valores padrão já usados pelo projeto
(no fluxo Docker, o próprio `docker-compose.yml` já sobrescreve isso pra
apontar pro serviço `redis` — não precisa mexer).

### 4. Configurar Login E Drive Com O Google

O login do BuscaÁgil é feito **exclusivamente com conta Google** — não existe
usuário/senha local nem tabela de usuários (ver `api/auth.py`). No mesmo
consentimento, o Google já pede autorização pro BuscaÁgil acessar a pasta
`buscaagil_upload` no Drive do usuário.

Pra isso funcionar, você precisa criar um **Client ID OAuth** no Google
Cloud Console:

1. **Criar um projeto** em https://console.cloud.google.com/ (ou usar um existente).
2. **Ativar a API do Drive**: menu > **APIs e serviços > Biblioteca** > procure **Google Drive API** > **Ativar**.
3. **Configurar a tela de consentimento OAuth** (**APIs e serviços > Tela de consentimento OAuth**):
   - Tipo de usuário: **Externo** (ou **Interno**, se for Google Workspace).
   - Preencha nome do app, e-mail de suporte e e-mail de contato do desenvolvedor.
   - Em **Escopos**, adicione `.../auth/userinfo.email`, `.../auth/userinfo.profile`
     e `https://www.googleapis.com/auth/drive.file` (acesso só aos arquivos
     que o próprio BuscaÁgil cria — não ao Drive inteiro do usuário).
   - Enquanto o app estiver em modo **Teste**, adicione as contas Google que
     vão logar (incluindo a sua) em **Usuários de teste**.
4. **Criar as credenciais** (**APIs e serviços > Credenciais > Criar credenciais > ID do cliente OAuth**):
   - Tipo de aplicativo: **Aplicativo da Web**.
   - **Origens JavaScript autorizadas**: `http://localhost`
   - **URIs de redirecionamento autorizados**: `http://localhost/auth/callback`

   Ao salvar, o Google mostra o **Client ID** e o **Client Secret**.
5. **Colar no `.env`**:

   ```text
   GOOGLE_OAUTH_CLIENT_ID=algo.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=sua_client_secret
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost/auth/callback
   ```

> **Atenção ao host usado no navegador**: as credenciais acima só valem para
> `http://localhost/`. Se você abrir o site em `http://127.0.0.1/` em vez de
> `localhost`, o login falha com `redirect_uri_mismatch` (pro Google, são
> origens diferentes) — use sempre `localhost`, ou cadastre `127.0.0.1`
> também nas credenciais.

> **Nota de desenvolvimento**: como o frontend roda em `http://` puro (sem
> TLS) em `localhost`, o `docker-compose.yml` já define
> `OAUTHLIB_INSECURE_TRANSPORT=1` no serviço `api` — necessário porque a
> biblioteca OAuth exige HTTPS por padrão. **Nunca** faça isso num domínio
> público de verdade; ali o certo é servir tudo atrás de HTTPS.

### 5. Configurar IA Local (Ollama)

Por padrão (`LOCAL_AI_ENABLED=true` no `.env`), a classificação de arquivos e
o entendimento da busca tentam rodar **localmente**, num container Ollama
(CPU, sem depender de internet nem gastar cota do Gemini), e só caem pro
Gemini se o container estiver fora do ar ou o modelo local falhar. Pra
desligar de vez e usar só o Gemini, defina `LOCAL_AI_ENABLED=false` no
`.env`.

Se você já rodou `./install.sh` (seção 2), os passos abaixo já foram feitos
automaticamente — pule direto pra **"Como funciona o roteamento"**. Os
comandos abaixo servem pra quem quiser rodar na mão (fluxo manual, ou pra
trocar de modelo depois).

**1. Subir o container do Ollama** (no fluxo manual, só o serviço `ollama` —
o `docker-compose.yml` também define `api`/`worker`/`frontend`/`redis`,
usados pelo `./install.sh`):

```bash
docker compose up -d ollama
```

**2. Baixar os modelos** (uma vez só, ficam salvos no volume do container):

```bash
docker compose exec ollama ollama pull qwen2.5:7b-instruct
docker compose exec ollama ollama pull moondream
```

- `qwen2.5:7b-instruct`: classifica texto/documentos e interpreta a busca
  (mesmo papel que o Gemini faz hoje). Mais preciso que o `3b`, ao custo de
  rodar mais devagar em CPU — se a máquina não aguentar, troque
  `LOCAL_AI_TEXT_MODEL=qwen2.5:3b-instruct` no `.env` e baixe esse modelo
  em vez do `7b`.
- `moondream`: modelo de visão leve (~1.8B, roda bem em CPU) — descreve
  imagens e frames de vídeo/páginas de PDF escaneado em texto, que depois é
  classificado pelo modelo de texto acima.
- Transcrição de áudio/vídeo (`faster-whisper`) não é modelo do Ollama —
  baixa sozinha na primeira vez que for usada, tamanho controlado por
  `LOCAL_AI_WHISPER_MODEL` no `.env` (padrão `small`; `tiny` é mais rápido
  e menos preciso, `medium`/`large-v3` mais preciso e mais lento).

**3. Instalar o `ffmpeg`** (necessário só pra vídeo/áudio; já vem embutido
na imagem Docker da `api`/`worker`, só é preciso instalar manualmente no
fluxo sem Docker):

```bash
sudo apt-get install -y ffmpeg
```

Sem isso, arquivos de vídeo/áudio continuam funcionando (upload normal pro
Drive), só não ficam com categoria/tags/descrição.

**Como funciona o roteamento** — cada arquivo enviado é roteado
automaticamente pro tratamento certo, pela extensão:

- **Texto/planilha/documento** (`.txt`, `.csv`, `.xlsx`, `.docx` etc.) →
  extraído como texto e classificado direto pelo modelo de texto.
- **Imagem/PDF** (`.jpg`, `.png`, `.pdf`) → o `moondream` gera uma legenda da
  imagem (ou renderiza as primeiras páginas do PDF, se ele não tiver texto
  extraível — PDF escaneado) e o modelo de texto classifica essa legenda.
- **Vídeo/áudio** (`.mp4`, `.mov`, `.mp3` etc.) → o áudio é transcrito
  (`faster-whisper`) e, no caso de vídeo, 3 frames representativos também
  viram legenda via `moondream`; tudo isso junto é classificado pelo modelo
  de texto. Essa é uma capacidade nova — hoje vídeo/áudio não são
  classificados nem pelo Gemini.

### 6. Rodar Manualmente (Sem Docker)

Alternativa a `./install.sh` pra quem quiser rodar cada peça na mão, direto no
WSL. As seções 3, 4 e 5 (credenciais) valem pros dois jeitos de rodar.

**Criar ambiente e instalar bibliotecas:**

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Se o sistema reclamar de dependências de leitura de `.doc`, instale também:

```bash
sudo apt-get install antiword
```

**Instalar e rodar o Redis** (broker do Celery):

```bash
sudo apt-get install -y redis-server
sudo service redis-server start
redis-cli ping   # deve responder PONG
```

Como o WSL não usa `systemd` por padrão, o Redis precisa ser iniciado
manualmente com `sudo service redis-server start` toda vez que o WSL for
reiniciado.

**Rodar o worker do Celery** (terminal separado, deixe aberto):

```bash
export OAUTHLIB_INSECURE_TRANSPORT=1   # só em dev, http:// local — ver seção 4
celery -A worker.celery_app worker --loglevel=info
```

**Rodar a api** (outro terminal):

```bash
export OAUTHLIB_INSECURE_TRANSPORT=1
flask --app api.app run --debug
```

**Servir o frontend** (outro terminal — só arquivos estáticos, qualquer
servidor HTTP simples resolve; o exemplo abaixo usa o embutido do Python):

```bash
cd frontend/pages
python3 -m http.server 8080
```

No fluxo manual (sem o proxy do nginx) as duas origens são diferentes
(`:8080` pro frontend, `:5000` pra api) — pra evitar lidar com CORS/cookie
entre portas, prefira o fluxo Docker (seção 2) mesmo pra desenvolver; ele já
resolve isso com o proxy do nginx numa origem só.

**Resumo do dia a dia**, depois que o ambiente já estiver configurado uma vez:

```bash
sudo service redis-server start        # 1. Redis
docker compose up -d ollama            # 2. IA local (Ollama)
source venv/bin/activate               # 3. ambiente virtual
celery -A worker.celery_app worker --loglevel=info   # 4. worker (terminal separado)
flask --app api.app run --debug        # 5. api (outro terminal)
```

## Solução De Problemas

- Se o upload retornar erro com `redis.exceptions.ConnectionError`, o Redis
  não está rodando (fluxo manual) — repita `sudo service redis-server
  start`, ou no Docker confira `docker compose logs redis`.
- Se o upload for aceito mas o arquivo ficar travado com status
  `"processing"` para sempre (nunca vira `"done"` nem `"error"`), o worker
  do Celery não está rodando/consumindo — no fluxo manual, rode
  `celery -A worker.celery_app worker --loglevel=info`; no Docker, confira
  `docker compose ps` e `docker compose logs worker`.
- Sem `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` configurados, o
  botão "Continuar com Google" redireciona pro Google e volta com erro —
  configure as credenciais (seção 4).
- Erro `redirect_uri_mismatch` no login: veja o aviso no fim da seção 4
  (host `localhost` vs `127.0.0.1`, e `GOOGLE_OAUTH_REDIRECT_URI` tem que
  bater exatamente com o cadastrado no Google Cloud Console).
- Erro `insecure_transport` no login: falta `OAUTHLIB_INSECURE_TRANSPORT=1`
  no ambiente da `api` (já vem definido no `docker-compose.yml`; no fluxo
  manual, exporte antes de rodar `flask run`).
- Se o login funcionar mas cair na tela "Não foi possível conectar ao seu
  Google Drive" (`auth.html`), o token do Google não tem o escopo do Drive
  (geralmente porque o consentimento foi negado, ou o app ainda está em modo
  Teste sem a conta autorizada como usuário de teste). Use o botão
  "Tentar de novo / reconceder acesso" na própria tela, que força o Google a
  pedir consentimento de novo (`prompt=consent`).
