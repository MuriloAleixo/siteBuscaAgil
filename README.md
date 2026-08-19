# siteBuscaAgil

Site para buscar suas anotações e arquivos de maneira simples e fácil.

## Estrutura Do Projeto

O projeto segue o padrão Django:

- `manage.py` na raiz
- pacote de projeto em `busca_agil/`
- app principal em `core/`
- utilitários em `scripts/`
- templates em `templates/`
- assets estáticos em `static/`
- pouso temporário de upload em `media/` (arquivo some de lá assim que o worker confirma o envio pro Drive)
- cache local do catálogo de cada usuário em `data/users/<id>.json`

Dentro de `core/`, vale destacar:

- `views.py` — rotas HTTP (páginas, upload, busca, `post_login_sync`)
- `tasks.py` — tarefas assíncronas do Celery (classificação + upload pro Drive)
- `google_drive.py` — toda a integração com a Drive API (pasta do usuário, catálogo, upload/download de arquivos)
- `models.py` — `DriveProfile`, guarda os IDs da pasta/catálogo de cada usuário no Drive
- `context_processors.py` — injeta os dados do usuário logado (nome, avatar, cota de armazenamento) em todo template
- `uploaded_files_store.py` — leitura/escrita do cache local por usuário, com lock de arquivo

`server.py` não é mais necessário. O ponto de entrada padrão do Django é o
`manage.py`. Veja `SISTEMA_DISTRIBUIDO.md` para uma explicação mais
detalhada de como essas peças conversam entre si (fila Redis, worker
Celery, Drive como fonte da verdade, cache local por usuário).

## Como Subir No WSL Do Windows

### 1. Instalar o WSL com Ubuntu

No PowerShell do Windows, execute:

```powershell
wsl --install
```

Se quiser instalar direto o Ubuntu:

```powershell
wsl --install -d Ubuntu
```

Depois reinicie o Windows se for solicitado. Ao abrir o Ubuntu pela primeira vez, crie o usuário e a senha do Linux.

### 2. Abrir o Ubuntu no WSL

Abra o app Ubuntu ou use o Windows Terminal com a distribuição Ubuntu. A partir daqui, os comandos abaixo devem ser executados no Linux do WSL.

### 3. Criar a chave SSH no Linux

Se você ainda não tem uma chave SSH no WSL, gere uma nova:

```bash
ssh-keygen -t ed25519 -C "seu_email@exemplo.com"
```

Pressione `Enter` para aceitar o caminho padrão e, se quiser, use uma senha para proteger a chave.

### 4. Copiar a chave pública para o GitHub

Mostre a chave pública com:

```bash
cat ~/.ssh/id_ed25519.pub
```

Copie o conteúdo inteiro e adicione em:

GitHub > Settings > SSH and GPG keys > New SSH key

Depois teste a conexão:

```bash
ssh -T git@github.com
```

Se tudo estiver certo, o GitHub deve responder com uma mensagem de autenticação.

### 5. Baixar o projeto do GitHub

Entre na pasta onde deseja clonar e execute:

```bash
git clone git@github.com:MuriloAleixo/siteBuscaAgil.git
cd siteBuscaAgil
```

Se o projeto já estiver aberto dentro do WSL, basta entrar na pasta do repositório.

## Criar Ambiente E Instalar Bibliotecas

Recomenda-se criar um ambiente virtual Python no WSL:

```bash
python3 -m venv venv
source venv/bin/activate
```

Depois instale as dependências:

```bash
pip install -r requirements.txt
```

Se o sistema reclamar de dependências de leitura de `.doc`, instale também o pacote de sistema:

```bash
sudo apt-get install antiword
```

## Configurar Variáveis De Ambiente

Copie o arquivo de exemplo e preencha com sua chave:

```bash
cp .env.example .env
```

Edite o `.env` e defina:

```text
GEMINI_API_KEY=sua_chave_aqui
```

Gere uma chave gratuita em https://aistudio.google.com/apikey. Sem essa chave o
site continua funcional, apenas sem a classificação automática de arquivos
(veja `DOCUMENTACAO.md`).

Opcionalmente, também é possível sobrescrever a conexão do Celery/Redis
definindo no `.env`:

```text
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/0
```

Se não forem definidas, esses são os valores padrão já usados pelo projeto.

## Configurar Login E Drive Com O Google

O login do BuscaÁgil é feito **exclusivamente com conta Google** — não existe
usuário/senha local. No mesmo consentimento, o Google já pede autorização
pro BuscaÁgil acessar uma pasta própria (`buscaagil_upload`) no Drive do
usuário: é lá que os arquivos enviados e o catálogo (`uploaded_files.json`)
de cada usuário ficam guardados. Local (`media/`, `data/users/`) é só um
pouso temporário/cache — veja `SISTEMA_DISTRIBUIDO.md` para o desenho
completo.

Pra isso funcionar, você precisa criar um **Client ID OAuth** no Google
Cloud Console:

### 1. Criar um projeto no Google Cloud Console

Acesse https://console.cloud.google.com/, crie um projeto novo (ou use um
existente) e selecione-o no seletor do topo da página.

### 2. Ativar a API do Google Drive

No menu, vá em **APIs e serviços > Biblioteca**, procure por **Google Drive
API** e clique em **Ativar**.

### 3. Configurar a tela de consentimento OAuth

Em **APIs e serviços > Tela de consentimento OAuth**:

- Tipo de usuário: **Externo** (ou **Interno**, se for Google Workspace).
- Preencha nome do app, e-mail de suporte e e-mail de contato do
  desenvolvedor.
- Em **Escopos**, adicione:
  - `.../auth/userinfo.email`
  - `.../auth/userinfo.profile`
  - `https://www.googleapis.com/auth/drive.file` (acesso só aos arquivos
    que o próprio BuscaÁgil cria — não ao Drive inteiro do usuário)
- Enquanto o app estiver em modo **Teste**, adicione as contas Google que
  vão logar (incluindo a sua) em **Usuários de teste**.

### 4. Criar as credenciais (Client ID OAuth)

Em **APIs e serviços > Credenciais > Criar credenciais > ID do cliente
OAuth**:

- Tipo de aplicativo: **Aplicativo da Web**.
- **Origens JavaScript autorizadas**: `http://localhost:8000`
- **URIs de redirecionamento autorizados**:
  `http://localhost:8000/accounts/google/login/callback/`

Ao salvar, o Google mostra o **Client ID** e o **Client Secret**.

### 5. Colar as credenciais no `.env`

```text
GOOGLE_OAUTH_CLIENT_ID=algo.apps.googleusercontent.com
GOOGLE_OAUTH_CLIENT_SECRET=sua_client_secret
```

### 6. Rodar as migrações

O login com Google usa tabelas do Django (`django-allauth`) que ainda não
existiam antes — rode (ou re-rode) as migrações depois de configurar isso:

```bash
python manage.py migrate
```

## Instalar E Rodar O Redis

O upload de arquivos usa o Celery para processar a classificação em segundo
plano, e o Celery precisa de um broker Redis rodando. Instale e inicie o
Redis no WSL:

```bash
sudo apt-get install -y redis-server
sudo service redis-server start
```

Verifique se está no ar:

```bash
redis-cli ping
```

Deve responder `PONG`. Como o WSL não usa `systemd` por padrão, o Redis
precisa ser iniciado manualmente com `sudo service redis-server start` toda
vez que o WSL for reiniciado.

## Rodar As Migrações Do Banco

Com o ambiente virtual ativo:

```bash
python manage.py migrate
```

## Rodar O Worker Do Celery

Em um terminal separado (com o ambiente virtual ativo e o Redis já rodando),
suba o worker que processa o upload em segundo plano:

```bash
celery -A busca_agil worker --loglevel=info
```

Deixe esse terminal aberto enquanto for testar uploads.

## Rodar O Projeto

Em outro terminal, com o ambiente virtual ativo, inicie o Django:

```bash
python manage.py runserver
```

Depois abra no navegador:

```text
http://127.0.0.1:8000/
```

## Resumo Para Rodar No Dia A Dia

Depois que o ambiente já estiver configurado uma vez, o fluxo do dia a dia é:

```bash
sudo service redis-server start        # 1. Redis
source venv/bin/activate               # 2. ambiente virtual
celery -A busca_agil worker --loglevel=info   # 3. worker (terminal separado)
python manage.py runserver             # 4. servidor Django (outro terminal)
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
3. **Atualize as credenciais OAuth do Google** (seção acima) com a URI de
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

## Observações Importantes

- Use o terminal do Ubuntu no WSL para todos os comandos Python, Git e pip.
- Os arquivos enviados pela tela de upload ficam em `media/`.
- Os scripts auxiliares de categorização estão em `scripts/`.
- Se você mudar o código e o servidor estiver rodando, o Django recarrega automaticamente na maioria dos casos.
- Se o upload retornar erro 500 com `redis.exceptions.ConnectionError`, o
  Redis não está rodando — repita `sudo service redis-server start`.
- Se o upload for aceito mas o arquivo ficar travado com status
  `"processing"` para sempre (nunca vira `"done"` nem `"error"`), o worker
  do Celery não está rodando. A tarefa fica enfileirada no Redis esperando
  um worker consumi-la. Abra um terminal e rode
  `celery -A busca_agil worker --loglevel=info` (passo 3 do resumo acima).
- Sem `GOOGLE_OAUTH_CLIENT_ID`/`GOOGLE_OAUTH_CLIENT_SECRET` configurados, o
  botão "Continuar com Google" redireciona pro Google e volta com erro —
  configure as credenciais (seção "Configurar Login E Drive Com O Google").
- Se o login funcionar mas cair na tela "Não foi possível conectar ao seu
  Google Drive" (`auth.html`), o token do Google não tem o escopo do Drive
  (geralmente porque o consentimento foi negado ou o app ainda está em modo
  Teste sem a conta autorizada como usuário de teste). Use o botão de
  "Tentar de novo" na própria tela, que força o Google a pedir consentimento
  de novo (`prompt=consent`).
- Os arquivos enviados agora vão pro Google Drive do usuário (pasta
  `buscaagil_upload`), não ficam permanentemente em `media/` — esse
  diretório só guarda uma cópia temporária enquanto o worker Celery
  classifica e sobe o arquivo. Da mesma forma, `data/users/<id>.json` é só
  um cache local do catálogo; a fonte da verdade é o `uploaded_files.json`
  dentro da pasta do usuário no Drive.
- `static/js/auth.js` é quem fala com o login real (Google/allauth);
  `static/js/file-utils.js` tem utilitários de arquivo que ainda não têm
  backend real (`detectFileType`, exclusão simulada de arquivo);
  `static/js/catalog-client.js` busca o catálogo real em `/files`. O antigo
  `data/uploaded_files.json` (catálogo global, pré-login) foi removido —
  cada usuário tem o seu em `data/users/<id>.json`.
