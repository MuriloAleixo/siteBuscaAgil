# siteBuscaAgil
Site para buscar suas anotações e arquivos de maneira simples e fácil.

## Estrutura Django

O projeto agora segue o padrão Django com:

- `manage.py` na raiz
- pacote de projeto em `busca_agil/`
- app principal em `core/`
- utilitários em `scripts/`
- templates em `templates/`
- assets em `static/`
- páginas HTML servidas como templates
- upload salvo em `media/`

`server.py` não é mais necessário; o ponto de entrada padrão do Django é o `manage.py`.

## Como rodar

Instale as dependências:

```bash
pip install -r requirements.txt
```

Depois inicie o servidor de desenvolvimento:

```bash
py -3 manage.py runserver
```

Abra `http://127.0.0.1:8000/`.
