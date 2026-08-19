# Sistema de Categorização Automática de Arquivos (Gemini) — Documentação de Integração

Os scripts auxiliares agora vivem em `scripts/`, enquanto o Django fica em `manage.py`, `busca_agil/` e `core/`.

## Fluxo

```text
Cliente envia arquivo no site (POST /upload)
         │
         ▼
core/views.py salva o arquivo TEMPORARIAMENTE em media/ e enfileira
a tarefa no Celery (core/tasks.classify_and_catalog_task) — a resposta
HTTP não espera o resto acontecer, ver SISTEMA_DISTRIBUIDO.md
         │
         ▼  (worker Celery, fora do processo web)
scripts/extrator_conteudo.py  → lê o arquivo ou link e prepara o conteúdo
         │
         ▼
scripts/categorizer_gemini.py → envia o conteúdo pro Gemini e recebe a classificação
         │
         ▼
scripts/file_catalog.py       → salva a classificação no catalog.json local (scores best-effort)
         │
         ▼
core/google_drive.py          → sobe o arquivo real pra pasta "buscaagil_upload"
                                  no Google Drive do usuário logado
         │
         ▼
core/uploaded_files_store.py  → grava categoria/tags/link do Drive no
                                  catálogo do usuário (data/users/<id>.json)
                                  e o arquivo local temporário é apagado
```

Note que existem **dois catálogos JSON diferentes** com propósitos
diferentes, e é fácil confundir os dois:

- `catalog.json` (raiz do projeto) — usado só internamente por
  `scripts/file_catalog.py`/`processar_upload.py` pra guardar os *scores*
  de classificação do Gemini. Não é servido pro front-end e não é
  versionado no git (é estado gerado em runtime).
- `data/users/<id>.json` — o catálogo que o front-end de fato lê
  (`GET /files`), um por usuário, espelhado no `uploaded_files.json` dentro
  da pasta `buscaagil_upload` de cada um no Google Drive. Veja
  `SISTEMA_DISTRIBUIDO.md` para o desenho completo.

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

`core/views.py` + `core/tasks.py` (worker Celery) chamam o pipeline em duas
frentes — upload de arquivo e cadastro de link — as duas exigem login com
Google (`@login_required`), porque o destino final é o Drive do próprio
usuário:

- **`POST /upload`** (`upload_files`): salva o arquivo temporariamente em
  `media/` via `FileSystemStorage` e enfileira
  `classify_and_catalog_task.delay(user_id, entry_id, caminho_local,
  nome_original)` — a resposta HTTP volta na hora com
  `status: "processing"`, sem esperar o resto. O worker Celery
  (`core/tasks._run_file_upload`) roda `processar_upload(...)`
  (best-effort — best-effort de verdade: mesmo se a classificação falhar, o
  arquivo ainda sobe pro Drive), sobe o arquivo pro Drive via
  `core/google_drive.upload_file`, apaga o arquivo local, e grava
  categoria/tags/link do Drive no catálogo do usuário
  (`core/uploaded_files_store.update_entry`).

  A classificação (não o upload em si) é **best-effort**: se faltar
  `GEMINI_API_KEY`, se o formato não for suportado por
  `extrator_conteudo.py`, ou se a API do Gemini falhar, o arquivo sobe pro
  Drive normalmente — só não grava categoria/tags (fica com
  `"category": null` na resposta).

- **`GET /files`** (`list_uploaded_files`): lê o catálogo local do usuário
  logado (`data/users/<user_id>.json`, um cache do que está no Drive dele —
  ver `SISTEMA_DISTRIBUIDO.md`). O front-end
  (`static/js/catalog-client.js` → `loadUploadedFiles()`) consome esse endpoint e
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
