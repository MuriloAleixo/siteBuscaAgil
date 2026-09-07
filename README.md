# siteBuscaAgil

Site para buscar suas anotações e arquivos de maneira simples e fácil. Login
exclusivamente com Google, arquivos guardados no seu próprio Google Drive, e
classificação automática (categoria/tags/descrição) via IA — local (Ollama)
ou Gemini.

Pra aprender a **usar** o sistema (login, upload, busca, editar
classificação, excluir arquivos), veja **[GUIA_DE_USO.md](GUIA_DE_USO.md)**.
Este documento aqui é só sobre **instalar e rodar** o projeto.

## Estrutura Do Projeto

O projeto segue o padrão Django:

- `manage.py` na raiz
- pacote de projeto em `busca_agil/`
- app principal em `core/`
- utilitários/IA em `scripts/`
- templates em `templates/`
- assets estáticos em `static/`
- pouso temporário de upload em `media/` (arquivo some de lá assim que o worker confirma o envio pro Drive)
- cache local do catálogo de cada usuário em `data/users/<id>.json`

Dentro de `core/`, vale destacar:

- `views.py` — rotas HTTP (páginas, upload, busca, exclusão, `post_login_sync`)
- `tasks.py` — tarefas assíncronas do Celery (classificação + upload pro Drive)
- `google_drive.py` — toda a integração com a Drive API (pasta do usuário, catálogo, upload/download/exclusão de arquivos)
- `models.py` — `DriveProfile`, guarda os IDs da pasta/catálogo de cada usuário no Drive
- `context_processors.py` — injeta os dados do usuário logado (nome, avatar, cota de armazenamento) em todo template
- `uploaded_files_store.py` — leitura/escrita do cache local por usuário, com lock de arquivo

Dentro de `scripts/`:

- `processar_upload.py` — orquestrador: tenta a IA local primeiro (se
  habilitada), cai pro Gemini em qualquer falha
- `local_ai/` — IA local via Ollama (texto, imagem/PDF, vídeo/áudio, busca)
- `categorizer_gemini.py` / `analisador_busca.py` — classificação e busca via Gemini (nuvem)
- `extrator_conteudo.py` — extração de texto de documentos/planilhas

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
direto no WSL) mais o plugin `docker compose`, todo o resto — Django, worker
do Celery, Redis e a IA local (Ollama) — sobe com um único script, sem
precisar instalar Python/venv/Redis/ffmpeg no seu WSL.

1. Configure as credenciais no `.env` (seções **3** e **4** abaixo — os
   passos de configuração de chave são os mesmos, só quem roda o processo
   muda).
2. Rode:

   ```bash
   ./setup.sh
   ```

O script builda as imagens, sobe o Ollama, baixa os modelos de IA local,
roda as migrações, sobe o Django e o worker e, ao final, roda uma bateria
de **smoke tests** (Ollama respondendo com os modelos certos, Django
respondendo em `:8000`, worker do Celery respondendo a um ping via broker,
e uma classificação de arquivo de ponta a ponta) — se algum teste crítico
falhar, o script para e mostra o que verificar. Se tudo passar, acesse
`http://localhost:8000/`.

Comandos do dia a dia depois da primeira vez:

```bash
docker compose up -d      # subir tudo de novo
docker compose logs -f    # acompanhar os logs
docker compose down       # parar tudo
```

Pra desfazer tudo (containers, imagens, volumes com os modelos baixados,
`db.sqlite3`, cache local) e voltar a um estado zerado — só com o código e
os arquivos de configuração/instrução, pronto pra rodar `./setup.sh` de
novo do zero:

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
apontar pro serviço certo — não precisa mexer).

### 4. Configurar Login E Drive Com O Google

O login do BuscaÁgil é feito **exclusivamente com conta Google** — não existe
usuário/senha local. No mesmo consentimento, o Google já pede autorização
pro BuscaÁgil acessar a pasta `buscaagil_upload` no Drive do usuário.

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
   - **Origens JavaScript autorizadas**: `http://localhost:8000`
   - **URIs de redirecionamento autorizados**: `http://localhost:8000/accounts/google/login/callback/`

   Ao salvar, o Google mostra o **Client ID** e o **Client Secret**.
5. **Colar no `.env`**:

   ```text
   GOOGLE_OAUTH_CLIENT_ID=algo.apps.googleusercontent.com
   GOOGLE_OAUTH_CLIENT_SECRET=sua_client_secret
   ```
6. **Rodar as migrações** (o login com Google usa tabelas do `django-allauth`):

   ```bash
   python manage.py migrate
   ```

   (No fluxo Docker, o `web` já roda isso sozinho ao subir — não precisa repetir.)

> **Atenção ao host usado no navegador**: as credenciais acima só valem para
> `http://localhost:8000/`. Se você abrir o site em `http://127.0.0.1:8000/`
> em vez de `localhost`, o login falha com `redirect_uri_mismatch` (pro
> Google, são origens diferentes) — use sempre `localhost`, ou cadastre
> `127.0.0.1` também nas credenciais.

### 5. Configurar IA Local (Ollama)

Por padrão (`LOCAL_AI_ENABLED=true` no `.env`), a classificação de arquivos e
o entendimento da busca tentam rodar **localmente**, num container Ollama
(CPU, sem depender de internet nem gastar cota do Gemini), e só caem pro
Gemini se o container estiver fora do ar ou o modelo local falhar. Pra
desligar de vez e usar só o Gemini, defina `LOCAL_AI_ENABLED=false` no
`.env`.

Se você já rodou `./setup.sh` (seção 2), os passos abaixo já foram feitos
automaticamente — pule direto pra **"Como funciona o roteamento"**. Os
comandos abaixo servem pra quem quiser rodar na mão (fluxo manual, ou pra
trocar de modelo depois).

**1. Subir o container do Ollama** (no fluxo manual, só o serviço `ollama` —
o `docker-compose.yml` também define `web`/`worker`, usados pelo
`./setup.sh`):

```bash
docker compose up -d ollama
```

**2. Baixar os modelos** (uma vez só, ficam salvos no volume do container):

```bash
docker compose exec ollama ollama pull qwen2.5:3b-instruct
docker compose exec ollama ollama pull moondream
```

- `qwen2.5:3b-instruct`: classifica texto/documentos e interpreta a busca
  (mesmo papel que o Gemini faz hoje).
- `moondream`: modelo de visão leve (~1.8B, roda bem em CPU) — descreve
  imagens e frames de vídeo/páginas de PDF escaneado em texto, que depois é
  classificado pelo modelo de texto acima.

**3. Instalar o `ffmpeg`** (necessário só pra vídeo/áudio; já vem embutido
na imagem Docker do `web`/`worker`, só é preciso instalar manualmente no
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

Alternativa a `./setup.sh` pra quem quiser rodar cada peça na mão, direto no
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

**Rodar as migrações do banco:**

```bash
python manage.py migrate
```

**Rodar o worker do Celery** (terminal separado, deixe aberto):

```bash
celery -A busca_agil worker --loglevel=info
```

**Rodar o projeto** (outro terminal):

```bash
python manage.py runserver
```

Depois abra `http://localhost:8000/` no navegador.

**Resumo do dia a dia**, depois que o ambiente já estiver configurado uma vez:

```bash
sudo service redis-server start        # 1. Redis
docker compose up -d ollama            # 2. IA local (Ollama)
source venv/bin/activate               # 3. ambiente virtual
celery -A busca_agil worker --loglevel=info   # 4. worker (terminal separado)
python manage.py runserver             # 5. servidor Django (outro terminal)
```

## Checklist De Produção

Por padrão o projeto sobe em **modo desenvolvimento** (`DJANGO_DEBUG=true`,
`ALLOWED_HOSTS=["*"]`, chave secreta de exemplo). Antes de subir num
servidor real:

1. **Gere uma `SECRET_KEY` de verdade** e defina no `.env`:
   ```bash
   python -c "import secrets; print(secrets.token_urlsafe(50))"
   ```
   ```text
   DJANGO_SECRET_KEY=<a chave gerada>
   ```
2. **Desative o modo debug e restrinja os hosts**:
   ```text
   DJANGO_DEBUG=false
   DJANGO_ALLOWED_HOSTS=seudominio.com.br,www.seudominio.com.br
   DJANGO_CSRF_TRUSTED_ORIGINS=https://seudominio.com.br
   ```
   Com `DJANGO_DEBUG=false`, o Django recusa subir (`RuntimeError` explícito
   em `busca_agil/settings.py`) se `DJANGO_SECRET_KEY` ou
   `DJANGO_ALLOWED_HOSTS` não estiverem definidas — isso é proposital, pra
   nunca subir em produção com os valores de desenvolvimento por engano.
3. **Atualize as credenciais OAuth do Google** (seção 4) com a URI de
   redirecionamento do domínio real:
   `https://seudominio.com.br/accounts/google/login/callback/` — e mova o
   app de "Teste" pra "Em produção" na tela de consentimento OAuth.
4. **Não use `python manage.py runserver` em produção** — é um servidor de
   desenvolvimento. Use um servidor WSGI/ASGI real (Gunicorn, uWSGI,
   Daphne/Uvicorn) atrás de um proxy (Nginx), servindo os arquivos de
   `static/` diretamente pelo proxy ou via `collectstatic` +
   [WhiteNoise](https://whitenoise.readthedocs.io/).
5. **Redis e o worker Celery** precisam rodar como serviços supervisionados
   (systemd, supervisor, Docker) — não em terminais soltos como no
   desenvolvimento.
6. **Banco de dados**: `db.sqlite3` é suficiente para o volume de uso do
   Django puro (sessões, contas Google), mas considere Postgres se o
   volume de usuários crescer.

## Solução De Problemas

- Se o upload retornar erro 500 com `redis.exceptions.ConnectionError`, o
  Redis não está rodando (fluxo manual) — repita
  `sudo service redis-server start`, ou no Docker confira
  `docker compose logs worker`.
- Se o upload for aceito mas o arquivo ficar travado com status
  `"processing"` para sempre (nunca vira `"done"` nem `"error"`), o worker
  do Celery não está rodando/consumindo — no fluxo manual, rode
  `celery -A busca_agil worker --loglevel=info`; no Docker, confira
  `docker compose ps` e `docker compose logs worker`.
- Sem `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` configurados, o
  botão "Continuar com Google" redireciona pro Google e volta com erro —
  configure as credenciais (seção 4).
- Erro `redirect_uri_mismatch` no login: veja o aviso no fim da seção 4
  (host `localhost` vs `127.0.0.1`).
- Se o login funcionar mas cair na tela "Não foi possível conectar ao seu
  Google Drive" (`auth.html`), o token do Google não tem o escopo do Drive
  (geralmente porque o consentimento foi negado, ou o app ainda está em modo
  Teste sem a conta autorizada como usuário de teste). Use o botão
  "Tentar de novo / reconceder acesso" na própria tela, que força o Google a
  pedir consentimento de novo (`prompt=consent`).
