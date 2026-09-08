from __future__ import annotations

import logging
import mimetypes
import os

from celery import shared_task
from django.contrib.auth import get_user_model

from core import google_drive, uploaded_files_store
from core.models import DriveProfile
from scripts.processar_upload import processar_upload

logger = logging.getLogger(__name__)


def sync_catalog_to_drive(service, user_id: int) -> None:
    """Reflete o catálogo local (já atualizado) de volta pro
    uploaded_files.json dentro da pasta do usuário no Drive."""
    profile = DriveProfile.objects.get(user_id=user_id)
    files = uploaded_files_store.read_all(user_id)
    catalog_file_id = google_drive.upload_catalog(service, profile.folder_id, files, profile.catalog_file_id or None)
    if catalog_file_id != profile.catalog_file_id:
        profile.catalog_file_id = catalog_file_id
        profile.save(update_fields=["catalog_file_id"])


def _classify_best_effort(origem: str) -> dict | None:
    """Classificação via Gemini é best-effort: formato não suportado, falta
    de GEMINI_API_KEY ou erro de rede não podem impedir o arquivo de ir pro
    Drive — só ficam sem categoria/tags."""
    try:
        return processar_upload(origem)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível classificar '%s': %s", origem, exc)
        return None


def _confidence_from_resultado(resultado: dict | None) -> float | None:
    """Score (0.0-1.0) que o classificador deu pra categoria escolhida como
    principal — usado pro frontend sinalizar classificações duvidosas em vez
    de descartar o score assim que ele chega."""
    if not resultado:
        return None
    scores = resultado.get("scores") or {}
    return scores.get(resultado.get("categoria_principal"))


def _run_file_upload(user_id: int, saved_path: str, entry_id: str, original_name: str) -> None:
    resultado = _classify_best_effort(saved_path)

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        service = google_drive.get_drive_service(user)
        profile = DriveProfile.objects.get(user_id=user_id)
    except (User.DoesNotExist, DriveProfile.DoesNotExist, google_drive.DriveNotConnectedError) as exc:
        logger.warning("Não foi possível subir '%s' pro Drive do usuário %s: %s", original_name, user_id, exc)
        uploaded_files_store.update_entry(user_id, entry_id, status="error")
        return

    mimetype = mimetypes.guess_type(original_name)[0]
    try:
        uploaded = google_drive.upload_file(service, profile.folder_id, saved_path, original_name, mimetype)
    except Exception as exc:  # noqa: BLE001 - erro do Drive não pode derrubar o worker
        logger.warning("Falha ao subir '%s' pro Drive: %s", original_name, exc)
        # Mantém o arquivo local (não deleta) pra não perder o dado enviado.
        uploaded_files_store.update_entry(user_id, entry_id, status="error")
        return

    uploaded_files_store.update_entry(
        user_id,
        entry_id,
        status="done",
        category=(resultado or {}).get("categoria_principal"),
        tags=(resultado or {}).get("tags", []),
        description=(resultado or {}).get("descricao", ""),
        scores=(resultado or {}).get("scores", {}),
        confidence=_confidence_from_resultado(resultado),
        classification_source="ai" if resultado else None,
        url=uploaded["web_view_link"],
        drive_file_id=uploaded["file_id"],
    )

    try:
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - o arquivo já subiu; sincronizar o catálogo é best-effort
        logger.warning("Arquivo no Drive, mas falhou sincronizar uploaded_files.json: %s", exc)

    try:
        os.remove(saved_path)
    except OSError as exc:
        logger.warning("Não foi possível remover o arquivo temporário local '%s': %s", saved_path, exc)


def _run_link_classification(user_id: int, url: str, entry_id: str) -> None:
    """Links não têm arquivo físico pra subir — só a classificação entra no
    catálogo (que ainda assim é sincronizado de volta pro Drive)."""
    resultado = _classify_best_effort(url)
    if resultado is None:
        uploaded_files_store.update_entry(user_id, entry_id, status="error")
        return

    uploaded_files_store.update_entry(
        user_id,
        entry_id,
        status="done",
        category=resultado.get("categoria_principal"),
        tags=resultado.get("tags", []),
        description=resultado.get("descricao", ""),
        scores=resultado.get("scores", {}),
        confidence=_confidence_from_resultado(resultado),
        classification_source="ai",
    )

    User = get_user_model()
    try:
        user = User.objects.get(pk=user_id)
        service = google_drive.get_drive_service(user)
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Não foi possível sincronizar o catálogo com o Drive: %s", exc)


@shared_task(bind=True)
def classify_and_catalog_task(self, user_id: int, entry_id: str, saved_path: str, original_name: str) -> None:
    _run_file_upload(user_id, saved_path, entry_id, original_name)


@shared_task(bind=True)
def classify_link_task(self, user_id: int, entry_id: str, url: str) -> None:
    _run_link_classification(user_id, url, entry_id)
