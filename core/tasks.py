from __future__ import annotations

import logging
from pathlib import Path

from celery import shared_task
from django.conf import settings

from core import uploaded_files_store
from scripts.file_catalog import FileCatalog
from scripts.processar_upload import processar_upload

logger = logging.getLogger(__name__)

CATALOG_PATH = str(Path(settings.BASE_DIR) / "catalog.json")


def _run_classification(origem: str, public_url: str | None, entry_id: str) -> None:
    """
    Roda no worker Celery, fora do processo web. É best-effort: formatos não
    suportados ou falta de GEMINI_API_KEY não devem quebrar a task, só
    deixam a entry marcada como "error" (o arquivo já foi salvo e já está
    visível pro usuário com status "processing"/"error").
    """
    try:
        resultado = processar_upload(origem, catalog_path=CATALOG_PATH)
    except Exception as exc:  # noqa: BLE001 - classificação é best-effort
        logger.warning("Não foi possível classificar '%s': %s", origem, exc)
        uploaded_files_store.update_entry(entry_id, status="error")
        return

    if public_url:
        try:
            catalog = FileCatalog(CATALOG_PATH)
            catalog.update_cloud_path(resultado["file_id"], public_url)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Não foi possível vincular a URL pública no catálogo: %s", exc)

    uploaded_files_store.update_entry(
        entry_id,
        status="done",
        category=resultado.get("categoria_principal"),
        tags=resultado.get("tags", []),
        description=resultado.get("descricao", ""),
    )


@shared_task(bind=True)
def classify_and_catalog_task(self, entry_id: str, saved_path: str, public_url: str) -> None:
    _run_classification(saved_path, public_url, entry_id)


@shared_task(bind=True)
def classify_link_task(self, entry_id: str, url: str) -> None:
    _run_classification(url, None, entry_id)
