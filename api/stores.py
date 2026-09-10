"""
api/stores.py

Todo o "banco de dados" do BuscaÁgil: nenhum. Cada usuário tem uma pasta
`data/users/<id>/` com dois arquivos JSON:

  catalog.json  espelho do uploaded_files.json que mora de verdade na pasta
                do usuário no Google Drive (fonte da verdade) — evita bater
                no Drive a cada GET /files.
  profile.json  tokens OAuth do Google + IDs da pasta/catálogo no Drive +
                cota de armazenamento — substitui as tabelas
                SocialToken/DriveProfile que existiam quando o projeto usava
                Django+allauth+sqlite.

Os dois processos que mexem nesses arquivos (api respondendo ao polling do
navegador, worker Celery escrevendo o resultado da classificação) usam um
lock por arquivo (`filelock`) pra "ler tudo -> alterar -> reescrever" ser
atômico entre processos.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from filelock import FileLock

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
USERS_DATA_DIR = Path(os.environ.get("BUSCA_AGIL_DATA_DIR", BASE_DIR / "data" / "users"))
_LOCK_TIMEOUT_SECONDS = 10


def _user_dir(user_id: int | str) -> Path:
    return USERS_DATA_DIR / str(user_id)


def _catalog_path(user_id: int | str) -> Path:
    return _user_dir(user_id) / "catalog.json"


def _profile_path(user_id: int | str) -> Path:
    return _user_dir(user_id) / "profile.json"


def _lock_path(path: Path) -> str:
    return str(path) + ".lock"


def _read_json_file(path: Path, default):
    if not path.exists():
        return default
    with open(path, "r", encoding="utf-8") as f:
        raw = f.read().strip()
    if not raw:
        return default
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Arquivo '%s' com JSON inválido, tratando como vazio: %s", path, exc)
        return default


def _write_json_file(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, path)


# ---------------------------------------------------------------------------
# Catálogo de arquivos (era core/uploaded_files_store.py)
# ---------------------------------------------------------------------------

def read_all(user_id: int | str) -> list[dict]:
    path = _catalog_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        return _read_json_file(path, {"files": []}).get("files", [])


def write_all(user_id: int | str, files: list[dict]) -> None:
    """Sobrescreve todo o catálogo local do usuário (usado ao sincronizar
    com o Drive no login)."""
    path = _catalog_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        _write_json_file(path, {"files": files})


def insert_entry(user_id: int | str, entry: dict) -> None:
    """Remove qualquer entry pré-existente com o mesmo id e insere no topo."""
    path = _catalog_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_json_file(path, {"files": []}).get("files", [])
        files = [f for f in files if f["id"] != entry["id"]]
        files.insert(0, entry)
        _write_json_file(path, {"files": files})


def update_entry(user_id: int | str, entry_id: str, **fields) -> dict | None:
    """Atualiza campos de uma entry existente (usado pelo worker Celery ao
    terminar a classificação/upload assíncronos). Retorna a entry
    atualizada, ou None se o id não existir."""
    path = _catalog_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        files = _read_json_file(path, {"files": []}).get("files", [])
        entry = next((f for f in files if f["id"] == entry_id), None)
        if entry is None:
            return None
        entry.update(fields)
        _write_json_file(path, {"files": files})
        return entry


def get_entry(user_id: int | str, entry_id: str) -> dict | None:
    files = read_all(user_id)
    return next((f for f in files if f["id"] == entry_id), None)


# ---------------------------------------------------------------------------
# Perfil do usuário: tokens OAuth do Google + estado no Drive (era
# core/models.py::DriveProfile + allauth.SocialToken)
# ---------------------------------------------------------------------------

def read_profile(user_id: int | str) -> dict:
    path = _profile_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        return _read_json_file(path, {})


def write_profile(user_id: int | str, **fields) -> dict:
    """Mescla `fields` no profile.json existente (não sobrescreve tudo) —
    usado tanto no login (grava tokens + folder_id) quanto quando o worker
    atualiza só o catalog_file_id depois de sincronizar."""
    path = _profile_path(user_id)
    with FileLock(_lock_path(path), timeout=_LOCK_TIMEOUT_SECONDS):
        profile = _read_json_file(path, {})
        profile.update(fields)
        _write_json_file(path, profile)
        return profile
