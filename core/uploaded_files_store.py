from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from django.conf import settings
from filelock import FileLock

logger = logging.getLogger(__name__)

# Cada usuário tem seu próprio catálogo local, espelhando o
# uploaded_files.json guardado na pasta "buscaagil_upload" dele no Drive
# (ver core/google_drive.py). Isso é só um CACHE local: a fonte da verdade
# é o arquivo no Drive do usuário, baixado em core/views.post_login_sync no
# momento do login. O lock por usuário evita que o processo web (leitura no
# polling) e o worker Celery (escrita ao terminar a classificação) corrompam
# o JSON um do outro.
USERS_DATA_DIR = Path(settings.BASE_DIR) / "data" / "users"
_LOCK_TIMEOUT_SECONDS = 10


def _catalog_path(user_id: int | str) -> Path:
    return USERS_DATA_DIR / f"{user_id}.json"


def _lock_path(user_id: int | str) -> str:
    return str(_catalog_path(user_id)) + ".lock"


def _read_json(user_id: int | str) -> list[dict]:
    path = _catalog_path(user_id)
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return []
    try:
        return json.loads(raw).get("files", [])
    except json.JSONDecodeError as exc:
        logger.warning("Catálogo local do usuário %s inválido, tratando como vazio: %s", user_id, exc)
        return []


def _write_json(user_id: int | str, files: list[dict]) -> None:
    path = _catalog_path(user_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump({"files": files}, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


def read_all(user_id: int | str) -> list[dict]:
    with FileLock(_lock_path(user_id), timeout=_LOCK_TIMEOUT_SECONDS):
        return _read_json(user_id)


def write_all(user_id: int | str, files: list[dict]) -> None:
    """Sobrescreve todo o catálogo local do usuário (usado ao sincronizar
    com o Drive no login)."""
    with FileLock(_lock_path(user_id), timeout=_LOCK_TIMEOUT_SECONDS):
        _write_json(user_id, files)


def insert_entry(user_id: int | str, entry: dict) -> None:
    """Remove qualquer entry pré-existente com o mesmo id e insere no topo."""
    with FileLock(_lock_path(user_id), timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_json(user_id)
        files = [f for f in files if f["id"] != entry["id"]]
        files.insert(0, entry)
        _write_json(user_id, files)


def update_entry(user_id: int | str, entry_id: str, **fields) -> dict | None:
    """Atualiza campos de uma entry existente (usado pelos workers Celery ao
    terminar a classificação/upload assíncronos). Retorna a entry
    atualizada, ou None se o id não existir."""
    with FileLock(_lock_path(user_id), timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_json(user_id)
        entry = next((f for f in files if f["id"] == entry_id), None)
        if entry is None:
            return None
        entry.update(fields)
        _write_json(user_id, files)
        return entry


def get_entry(user_id: int | str, entry_id: str) -> dict | None:
    files = read_all(user_id)
    return next((f for f in files if f["id"] == entry_id), None)
