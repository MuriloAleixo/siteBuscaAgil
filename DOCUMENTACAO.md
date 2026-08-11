# Sistema de Categorização Automática de Arquivos (Gemini) — Documentação de Integração

Os scripts auxiliares agora vivem em `scripts/`, enquanto o Django fica em `manage.py`, `busca_agil/` e `core/`.

## Fluxo

```text
Cliente envia arquivo no site
         │
         ▼
scripts/extrator_conteudo.py  → lê o arquivo ou link e prepara o conteúdo
         │
         ▼
scripts/categorizer_gemini.py → envia o conteúdo pro Gemini e recebe a classificação
         │
         ▼
scripts/file_catalog.py       → salva a classificação no catálogo local
         │
         ▼
backend do site sobe o arquivo original pro Google Drive
         │
         ▼
scripts/file_catalog.py       → vincula o link/ID do Drive ao registro salvo
```

O orquestrador é `scripts/processar_upload.py`. Ele pode ser usado com:

```bash
python -m scripts.processar_upload /caminho/do/arquivo.pdf
python -m scripts.processar_upload "https://exemplo.com/pagina"
```

## Resumo dos scripts

### `scripts/file_catalog.py`
Camada de armazenamento do catálogo JSON. Expõe `FileCatalog` com `add_file`, `update_cloud_path`, `search`, `search_text`, `update_tags` e `remove_file`.

### `scripts/extrator_conteudo.py`
Prepara o conteúdo para o Gemini. Suporta texto, arquivos nativos e links. Dependências principais: `pandas`, `openpyxl`, `xlrd`, `python-docx`, `requests`, `beautifulsoup4`.

### `scripts/categorizer_gemini.py`
Conversa com a API do Gemini e devolve um `ClassificacaoArquivo` validado com `pydantic`.

### `scripts/processar_upload.py`
Amarra os três módulos acima. Recebe a origem do arquivo, prepara o conteúdo, classifica, grava no catálogo e devolve o resumo com `file_id`.

## Uso no backend

```python
from scripts.processar_upload import processar_upload
from scripts.file_catalog import FileCatalog

resultado = processar_upload("/tmp/uploads/nome_do_arquivo.pdf")

catalog = FileCatalog("catalog.json")
catalog.update_cloud_path(resultado["file_id"], drive_url)
```

## Integração com o Django (já implementada)

`core/views.py` chama o pipeline automaticamente em duas views:

- **`POST /upload`** (`upload_files`): depois de salvar o arquivo em `media/`
  via `FileSystemStorage`, chama `_classify_and_catalog(...)`, que roda
  `processar_upload(caminho_salvo, catalog_path=CATALOG_PATH)` e depois
  `catalog.update_cloud_path(file_id, public_url)` — como não há upload real
  pro Google Drive nesse projeto, a "cloud_path" registrada é a própria URL
  pública servida pelo Django (`/media/<arquivo>`). O `catalog.json` fica na
  raiz do projeto (`CATALOG_PATH = BASE_DIR / "catalog.json"`).

  A classificação é **best-effort**: se faltar `GEMINI_API_KEY`, se o
  formato não for suportado por `extrator_conteudo.py`, ou se a API do
  Gemini falhar, o upload continua funcionando normalmente — só não grava
  classificação para aquele arquivo (fica com `"classification": null` na
  resposta e sem `category`/`tags` na listagem).

- **`GET /files`** (`list_uploaded_files`): lista os arquivos físicos em
  `media/` e enriquece cada um com `category`, `tags` e `description` lidos
  do `catalog.json` (casando pelo nome do arquivo salvo). O front-end
  (`static/js/mock-data.js` → `loadUploadedFiles()`) consome esse endpoint e
  mescla os arquivos reais nas telas de **dashboard** e **busca**, incluindo
  a categoria do Gemini como tag pesquisável.

Para ativar a classificação automática, defina a variável de ambiente antes
de subir o servidor:

```bash
export GEMINI_API_KEY="sua_chave_aqui"
```

Sem a chave, o site continua funcional — os arquivos aparecem no dashboard e
na busca normalmente, apenas sem categoria/tags automáticas.

## Dependências

```bash
pip install google-genai pandas openpyxl xlrd python-docx requests beautifulsoup4 --break-system-packages
sudo apt-get install antiword   # só para .doc antigos
```

## Formatos suportados

`.txt` `.csv` `.xlsx` `.xls` `.doc` `.docx` `.pdf` `.jpg` `.jpeg` `.png` e links (http/https).
