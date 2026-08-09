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
- uploads salvos em `media/`

`server.py` não é mais necessário. O ponto de entrada padrão do Django é o `manage.py`.

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
python3 -m venv .venv
source .venv/bin/activate
```

Depois instale as dependências:

```bash
pip install -r requirements.txt
```

Se o sistema reclamar de dependências de leitura de `.doc`, instale também o pacote de sistema:

```bash
sudo apt-get install antiword
```

## Rodar O Projeto

Com o ambiente virtual ativo, inicie o Django:

```bash
python manage.py runserver
```

Depois abra no navegador:

```text
http://127.0.0.1:8000/
```

## Observações Importantes

- Use o terminal do Ubuntu no WSL para todos os comandos Python, Git e pip.
- Os arquivos enviados pela tela de upload ficam em `media/`.
- Os scripts auxiliares de categorização estão em `scripts/`.
- Se você mudar o código e o servidor estiver rodando, o Django recarrega automaticamente na maioria dos casos.
