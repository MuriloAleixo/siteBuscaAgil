"""
api/processing_log.py

Log persistente (SQLite) do que aconteceu em cada classificação assíncrona
(worker/tasks.py) — complementa o catalog.json (api/stores.py), que só
guarda o ESTADO FINAL de cada arquivo (status/categoria/tags). Aqui fica o
HISTÓRICO: cada etapa que rodou, quando, e com que resultado — inclusive o
motivo real de um erro (antes só existia em `docker compose logs worker`,
invisível na tela de processamento).

Por que SQLite e não mais um JSON em data/users/<id>/ (como stores.py): o
catalog.json é reescrito inteiro a cada update — ok pra "estado atual", com
poucos arquivos por usuário. O log cresce por append (um evento por etapa)
e é consultado por usuário/data, exatamente o caso que um índice SQL resolve
bem sem reescrever nada. Ainda assim não é um container novo: mora em
data/processing.db, no mesmo volume que já é compartilhado (bind mount
`.:/app`) entre os serviços `api` e `worker` (ver docker-compose.yml).
"""

from __future__ import annotations

import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("BUSCA_AGIL_PROCESSING_DB", BASE_DIR / "data" / "processing.db"))

# api e worker são processos (containers) separados escrevendo no mesmo
# arquivo ao mesmo tempo — WAL permite leitura concorrente com escrita, e o
# busy_timeout faz uma escrita simultânea esperar a outra terminar em vez de
# falhar na hora com "database is locked".
_BUSY_TIMEOUT_MS = 5000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS processing_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    entry_id TEXT NOT NULL,
    task_id TEXT,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_processing_events_user_created
    ON processing_events(user_id, created_at);
CREATE INDEX IF NOT EXISTS idx_processing_events_entry
    ON processing_events(entry_id);
"""


@contextmanager
def _connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=_BUSY_TIMEOUT_MS / 1000)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS}")
        conn.executescript(_SCHEMA)
        conn.row_factory = sqlite3.Row
        yield conn
        conn.commit()
    finally:
        conn.close()


def log_event(
    user_id: int | str,
    entry_id: str,
    step: str,
    status: str,
    message: str = "",
    task_id: str | None = None,
) -> None:
    """Registra uma etapa do processamento de um arquivo/link.

    step: identifica a etapa ("classify", "upload_drive", "catalog_sync"...).
    status: "started" | "done" | "error".
    message: livre — motivo do erro, ou um resumo do resultado (ex.: a
        categoria escolhida), pra aparecer na tela sem precisar dos logs do
        container.

    Best-effort: uma falha ao gravar o log nunca pode derrubar o
    processamento de verdade que ela está tentando registrar.
    """
    try:
        with _connect() as conn:
            conn.execute(
                "INSERT INTO processing_events "
                "(user_id, entry_id, task_id, step, status, message, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    str(user_id),
                    entry_id,
                    task_id,
                    step,
                    status,
                    message,
                    datetime.now(tz=timezone.utc).isoformat(),
                ),
            )
    except Exception:  # noqa: BLE001 - log é acessório, não pode propagar
        logger.warning("Não foi possível gravar evento de log ('%s'/'%s')", entry_id, step, exc_info=True)


def list_events(user_id: int | str, entry_id: str | None = None, limit: int = 200) -> list[dict]:
    """Eventos mais recentes primeiro. Passe `entry_id` pra pegar só a
    linha do tempo de um arquivo/link; sem ele, é o log geral do usuário
    (usado na tela de Fila de Processamento)."""
    query = "SELECT * FROM processing_events WHERE user_id = ?"
    params: list = [str(user_id)]
    if entry_id:
        query += " AND entry_id = ?"
        params.append(entry_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)

    with _connect() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]
