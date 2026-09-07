"""
core/google_drive.py

Camada de integração com o Google Drive do usuário logado. Cada usuário
autoriza o BuscaÁgil (escopo `drive.file`, só enxerga o que o próprio app
cria) e todo o conteúdo dele fica dentro de UMA pasta no Drive dele,
chamada `settings.GOOGLE_DRIVE_APP_FOLDER_NAME` ("buscaagil_upload"):

    Drive do usuário
    └── buscaagil_upload/
        ├── uploaded_files.json   ← catálogo pessoal (espelhado localmente)
        ├── contrato.pdf
        ├── planilha.xlsx
        └── ...

O `uploaded_files.json` de dentro dessa pasta é a fonte da verdade; a cópia
local (`core/user_catalog.py`) é só um cache pra não bater no Drive a cada
GET /files.
"""

from __future__ import annotations

import io
import json
import logging

from allauth.socialaccount.models import SocialToken
from django.conf import settings
from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload

logger = logging.getLogger(__name__)

DRIVE_FOLDER_MIME = "application/vnd.google-apps.folder"
CATALOG_FILENAME = "uploaded_files.json"


class DriveNotConnectedError(RuntimeError):
    """O usuário logou, mas não há token do Google Drive salvo pra ele."""


def _credentials_for_user(user) -> Credentials:
    token = SocialToken.objects.filter(account__user=user, account__provider="google").select_related("app").first()
    if token is None:
        raise DriveNotConnectedError("Usuário sem token do Google salvo — refaça o login.")

    # O app Google é configurado via SOCIALACCOUNT_PROVIDERS (settings.py),
    # não como SocialApp no banco — então token.app vem None. client_id/
    # secret têm que vir das settings, não do token.
    google_app = settings.SOCIALACCOUNT_PROVIDERS["google"]["APPS"][0]

    creds = Credentials(
        token=token.token,
        refresh_token=token.token_secret or None,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=google_app["client_id"],
        client_secret=google_app["secret"],
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    if creds.expired and creds.refresh_token:
        try:
            creds.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            raise DriveNotConnectedError(
                "Não foi possível renovar o acesso ao Drive — refaça o login."
            ) from exc
        token.token = creds.token
        if creds.expiry:
            token.expires_at = creds.expiry
        token.save(update_fields=["token", "expires_at"])

    return creds


def get_drive_service(user):
    creds = _credentials_for_user(user)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _find_child(service, name: str, parent_id: str | None, mime_type: str | None = None) -> dict | None:
    query = [f"name = '{name}'", "trashed = false"]
    if parent_id:
        query.append(f"'{parent_id}' in parents")
    else:
        query.append("'root' in parents")
    if mime_type:
        query.append(f"mimeType = '{mime_type}'")

    response = (
        service.files()
        .list(q=" and ".join(query), spaces="drive", fields="files(id, name)", pageSize=1)
        .execute()
    )
    files = response.get("files", [])
    return files[0] if files else None


def ensure_app_folder(service) -> str:
    """Acha (ou cria) a pasta `buscaagil_upload` na raiz do Drive do usuário."""
    folder_name = settings.GOOGLE_DRIVE_APP_FOLDER_NAME
    existing = _find_child(service, folder_name, parent_id=None, mime_type=DRIVE_FOLDER_MIME)
    if existing:
        return existing["id"]

    created = (
        service.files()
        .create(body={"name": folder_name, "mimeType": DRIVE_FOLDER_MIME}, fields="id")
        .execute()
    )
    return created["id"]


def download_catalog(service, folder_id: str) -> tuple[list[dict], str | None]:
    """Baixa o uploaded_files.json de dentro da pasta do app. Retorna
    (lista_de_arquivos, file_id) — file_id é None se o catálogo ainda não
    existir no Drive (primeiro login)."""
    existing = _find_child(service, CATALOG_FILENAME, parent_id=folder_id)
    if existing is None:
        return [], None

    buffer = io.BytesIO()
    request = service.files().get_media(fileId=existing["id"])
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    try:
        data = json.loads(buffer.getvalue().decode("utf-8") or "{}")
    except json.JSONDecodeError:
        logger.warning("uploaded_files.json do Drive inválido, tratando como vazio")
        data = {}

    return data.get("files", []), existing["id"]


def upload_catalog(service, folder_id: str, files: list[dict], catalog_file_id: str | None) -> str:
    """Sobe (cria ou atualiza) o uploaded_files.json na pasta do app.
    Retorna o file_id do catálogo no Drive."""
    payload = json.dumps({"files": files}, ensure_ascii=False, indent=2).encode("utf-8")
    media = MediaIoBaseUpload(io.BytesIO(payload), mimetype="application/json", resumable=False)

    if catalog_file_id:
        updated = service.files().update(fileId=catalog_file_id, media_body=media, fields="id").execute()
        return updated["id"]

    created = (
        service.files()
        .create(
            body={"name": CATALOG_FILENAME, "parents": [folder_id], "mimeType": "application/json"},
            media_body=media,
            fields="id",
        )
        .execute()
    )
    return created["id"]


def upload_file(service, folder_id: str, local_path: str, filename: str, mimetype: str | None) -> dict:
    """Sobe o arquivo real (não o catálogo) pra dentro da pasta do app.
    Retorna {"file_id", "web_view_link"}."""
    media = MediaFileUpload(local_path, mimetype=mimetype or "application/octet-stream", resumable=False)
    created = (
        service.files()
        .create(
            body={"name": filename, "parents": [folder_id]},
            media_body=media,
            fields="id, webViewLink",
        )
        .execute()
    )
    return {"file_id": created["id"], "web_view_link": created.get("webViewLink")}


def download_file(service, file_id: str) -> tuple[bytes, str, str]:
    """Baixa o conteúdo real de um arquivo (não o catálogo) da pasta do app.
    Retorna (conteudo, nome, mimetype)."""
    meta = service.files().get(fileId=file_id, fields="name, mimeType").execute()

    buffer = io.BytesIO()
    request = service.files().get_media(fileId=file_id)
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()

    return (
        buffer.getvalue(),
        meta.get("name", "arquivo"),
        meta.get("mimeType") or "application/octet-stream",
    )


def delete_file(service, file_id: str) -> None:
    try:
        service.files().delete(fileId=file_id).execute()
    except HttpError as exc:
        logger.warning("Não foi possível remover '%s' do Drive: %s", file_id, exc)


def get_storage_quota(service) -> tuple[int | None, int | None]:
    """Retorna (bytes_usados, bytes_total) da conta do usuário no Drive."""
    try:
        about = service.about().get(fields="storageQuota").execute()
    except HttpError as exc:
        logger.warning("Não foi possível ler a cota de armazenamento do Drive: %s", exc)
        return None, None
    quota = about.get("storageQuota", {})
    used = quota.get("usage")
    total = quota.get("limit")  # None quando é ilimitado (ex.: Workspace)
    return (int(used) if used is not None else None, int(total) if total is not None else None)
