from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from filelock import FileLock

logger = logging.getLogger(__name__)

# JSON que guarda a lista de arquivos exibida no dashboard/busca. Lido tanto
# pelo processo web (views) quanto pelos workers Celery (tasks) — o lock
# evita que uma escrita concorrente de um corrompa/pise na do outro.
UPLOADED_FILES_JSON_PATH = Path(settings.BASE_DIR) / "data" / "uploaded_files.json"
_LOCK_PATH = str(UPLOADED_FILES_JSON_PATH) + ".lock"
_LOCK_TIMEOUT_SECONDS = 10


def _read_uploaded_files_json() -> list[dict]:
    if not UPLOADED_FILES_JSON_PATH.exists():
        return []
    with open(UPLOADED_FILES_JSON_PATH, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    try:
        return json.loads(raw).get("files", [])
    except json.JSONDecodeError as exc:
        logger.warning("data/uploaded_files.json inválido, tratando como vazio: %s", exc)
        return []


def _write_uploaded_files_json(files: list[dict]) -> None:
    UPLOADED_FILES_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = UPLOADED_FILES_JSON_PATH.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"files": files}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, UPLOADED_FILES_JSON_PATH)


def read_all() -> list[dict]:
    with FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT_SECONDS):
        return _read_uploaded_files_json()


def write_all(files: list[dict]) -> None:
    with FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT_SECONDS):
        _write_uploaded_files_json(files)


def insert_entry(entry: dict) -> None:
    """Remove qualquer entry pré-existente com o mesmo id e insere no topo."""
    with FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_uploaded_files_json()
        files = [f for f in files if f["id"] != entry["id"]]
        files.insert(0, entry)
        _write_uploaded_files_json(files)


def update_entry(entry_id: str, **fields) -> dict | None:
    """Atualiza campos de uma entry existente (usado pelos workers Celery ao
    terminar a classificação assíncrona). Retorna a entry atualizada, ou
    None se o id não existir."""
    with FileLock(_LOCK_PATH, timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_uploaded_files_json()
        entry = next((f for f in files if f["id"] == entry_id), None)
        if entry is None:
            return None
        entry.update(fields)
        _write_uploaded_files_json(files)
        return entry


def get_entry(entry_id: str) -> dict | None:
    files = read_all()
    return next((f for f in files if f["id"] == entry_id), None)
