"""
api/auth.py

Login com Google, sem django-allauth: fluxo OAuth2 "authorization code"
manual (google-auth-oauthlib), pedindo de uma vez só o escopo de perfil
(nome/e-mail/foto) e de Drive (drive.file) — como antes, uma única tela de
consentimento do Google cobre login + autorização do Drive.

Não existe usuário/senha do BuscaÁgil nem tabela de usuários: o "id" de
cada usuário é o `sub` (subject) que o próprio Google devolve — estável,
único por conta Google — usado como nome da pasta em data/users/<id>/
(ver api/stores.py). A sessão do navegador é um cookie assinado nativo do
Flask (`flask.session`, chave = FLASK_SECRET_KEY): nenhum estado de sessão
fica guardado no servidor.
"""

from __future__ import annotations

import functools
import logging
import os
from datetime import datetime, timezone

import requests
from flask import Blueprint, jsonify, redirect, request, session
from google_auth_oauthlib.flow import Flow

from api import google_drive, stores

logger = logging.getLogger(__name__)

auth_bp = Blueprint("auth", __name__)

# openid+userinfo: nome/e-mail/foto pro perfil. drive.file: só os arquivos
# que o próprio BuscaÁgil cria no Drive do usuário (não o Drive inteiro) —
# princípio do menor privilégio numa integração OAuth.
SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile",
    "https://www.googleapis.com/auth/drive.file",
]

USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


def _redirect_uri() -> str:
    return os.environ.get("GOOGLE_OAUTH_REDIRECT_URI", "http://localhost/auth/callback")


def _new_flow(state: str | None = None) -> Flow:
    client_config = {
        "web": {
            "client_id": os.environ.get("GOOGLE_OAUTH_CLIENT_ID", ""),
            "client_secret": os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET", ""),
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": [_redirect_uri()],
        }
    }
    return Flow.from_client_config(client_config, scopes=SCOPES, state=state, redirect_uri=_redirect_uri())


@auth_bp.get("/auth/login")
def login():
    flow = _new_flow()
    # access_type=offline + prompt=consent garantem que o Google sempre
    # devolva um refresh_token, necessário pro worker Celery conseguir
    # subir arquivos pro Drive fora do ciclo de vida do login.
    authorization_url, state = flow.authorization_url(
        access_type="offline", prompt="consent", include_granted_scopes="true"
    )
    session["oauth_state"] = state
    return redirect(authorization_url)


@auth_bp.get("/auth/callback")
def callback():
    state = session.get("oauth_state")
    if not state or request.args.get("state") != state:
        logger.warning("Callback OAuth com state ausente/inválido")
        return redirect("/auth.html")

    try:
        flow = _new_flow(state=state)
        flow.fetch_token(authorization_response=request.url)
        creds = flow.credentials

        userinfo = requests.get(
            USERINFO_URL, headers={"Authorization": f"Bearer {creds.token}"}, timeout=10
        ).json()
        user_id = userinfo["sub"]

        joined_at = stores.read_profile(user_id).get("joined_at")
        if not joined_at:
            joined_at = datetime.now(tz=timezone.utc).date().isoformat()

        stores.write_profile(
            user_id,
            name=userinfo.get("name") or userinfo.get("email"),
            email=userinfo.get("email"),
            avatar=userinfo.get("picture", ""),
            joined_at=joined_at,
            oauth={
                "access_token": creds.token,
                "refresh_token": creds.refresh_token,
                "expires_at": creds.expiry.isoformat() if creds.expiry else None,
            },
        )

        # Garante a pasta "buscaagil_upload" no Drive do usuário, baixa o
        # uploaded_files.json de lá (se já existir, ex.: primeiro login vindo
        # de outro dispositivo) e espelha localmente — mesma lógica que
        # antes rodava em core/views.py::post_login_sync.
        service = google_drive.get_drive_service(user_id)
        folder_id = google_drive.ensure_app_folder(service)
        files, catalog_file_id = google_drive.download_catalog(service, folder_id)
        if catalog_file_id is None:
            catalog_file_id = google_drive.upload_catalog(service, folder_id, files, None)
        used, total = google_drive.get_storage_quota(service)

        stores.write_profile(
            user_id,
            folder_id=folder_id,
            catalog_file_id=catalog_file_id or "",
            storage_used_bytes=used,
            storage_total_bytes=total,
        )
        stores.write_all(user_id, files)
    except Exception as exc:  # noqa: BLE001 - qualquer falha de OAuth/Drive vira retry, não 500
        logger.warning("Falha ao autenticar/sincronizar Drive: %s", exc)
        return redirect("/auth.html")

    session.pop("oauth_state", None)
    session["user_id"] = user_id
    return redirect("/dashboard.html")


@auth_bp.get("/auth/logout")
def logout():
    session.clear()
    return redirect("/index.html")


@auth_bp.get("/me")
def me():
    user_id = session.get("user_id")
    if not user_id:
        return jsonify(None), 401

    profile = stores.read_profile(user_id)
    used = profile.get("storage_used_bytes")
    total = profile.get("storage_total_bytes")
    return jsonify(
        {
            "id": user_id,
            "name": profile.get("name") or profile.get("email"),
            "email": profile.get("email"),
            "avatar": profile.get("avatar", ""),
            "plan": "Google Drive",
            "joinedAt": profile.get("joined_at"),
            "storageUsed": round(used / (1024 ** 3), 2) if used else 0,
            # 15 GB é o padrão de contas Google pessoais gratuitas; fica como
            # fallback quando a API não devolve um limite (contas Workspace
            # ilimitadas, por exemplo).
            "storageTotal": round(total / (1024 ** 3), 2) if total else 15,
        }
    )


def login_required(view):
    """Substitui @login_required do Django: sem sessão válida, devolve 401
    JSON em vez de redirecionar — quem decide pra onde ir é o frontend
    (ver static/js/auth.js::requireAuth)."""

    @functools.wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("user_id"):
            return jsonify({"success": False, "error": "Não autenticado."}), 401
        return view(*args, **kwargs)

    return wrapped


def current_user_id() -> str:
    return session["user_id"]
