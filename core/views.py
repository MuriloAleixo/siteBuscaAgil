from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from scripts.file_catalog import FileCatalog
from scripts.processar_upload import processar_upload

logger = logging.getLogger(__name__)

CATALOG_PATH = str(Path(settings.BASE_DIR) / "catalog.json")

# JSON que guarda a lista de arquivos exibida no dashboard/busca. A consulta
# (list_uploaded_files) só lê esse arquivo — nada de varrer o disco a cada
# request. Cada novo upload é acrescentado aqui também.
UPLOADED_FILES_JSON_PATH = Path(settings.BASE_DIR) / "data" / "uploaded_files.json"


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


EXTENSION_TYPE_MAP = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".webp": "image", ".svg": "image",
    ".pdf": "pdf",
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video", ".webm": "video", ".wmv": "video",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio",
    ".xlsx": "sheet", ".xls": "sheet", ".csv": "sheet",
    ".doc": "doc", ".docx": "doc", ".txt": "doc",
    ".zip": "archive", ".rar": "archive", ".tar": "archive", ".gz": "archive", ".7z": "archive",
}


def _categorize_file(name: str, content_type: str | None) -> str:
    suffix = Path(name).suffix.lower()
    if suffix in EXTENSION_TYPE_MAP:
        return EXTENSION_TYPE_MAP[suffix]
    if content_type:
        if content_type.startswith("image/"):
            return "image"
        if content_type.startswith("video/"):
            return "video"
        if content_type.startswith("audio/"):
            return "audio"
        if content_type == "application/pdf":
            return "pdf"
    return "archive"


ALLOWED_PAGES = {
    "index": "index.html",
    "dashboard": "dashboard.html",
    "search": "search.html",
    "upload_page": "upload.html",
    "profile": "profile.html",
    "auth": "auth.html",
    "file_view": "file-view.html",
}


def _render_page(request, template_name: str):
    return render(request, template_name)


def index(request):
    return _render_page(request, "index.html")


def dashboard(request):
    return _render_page(request, "dashboard.html")


def search(request):
    return _render_page(request, "search.html")


def upload_page(request):
    return _render_page(request, "upload.html")


def profile(request):
    return _render_page(request, "profile.html")


def auth(request):
    return _render_page(request, "auth.html")


def file_view(request):
    return _render_page(request, "file-view.html")


@csrf_exempt
@require_http_methods(["POST"])
def upload_files(request):
    uploaded_files = request.FILES.getlist("files") or list(request.FILES.values())
    if not uploaded_files:
        return JsonResponse({"success": False, "error": "Nenhum arquivo foi recebido."}, status=400)

    Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)
    storage = FileSystemStorage(location=str(settings.MEDIA_ROOT), base_url=settings.MEDIA_URL)

    saved_files = []
    registered_files = _read_uploaded_files_json()
    for uploaded_file in uploaded_files:
        saved_name = storage.save(uploaded_file.name, uploaded_file)
        public_url = storage.url(saved_name)
        content_type = getattr(uploaded_file, "content_type", "application/octet-stream")
        classification = _classify_and_catalog(storage.path(saved_name), public_url)

        registered_files = [f for f in registered_files if f["id"] != saved_name]
        registered_files.insert(
            0,
            {
                "id": saved_name,
                "name": uploaded_file.name,
                "type": _categorize_file(saved_name, content_type),
                "content_type": content_type,
                "size": uploaded_file.size,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "url": public_url,
                "category": classification.get("categoria_principal") if classification else None,
                "tags": classification.get("tags", []) if classification else [],
                "description": classification.get("descricao", "") if classification else "",
            },
        )

        saved_files.append(
            {
                "original_name": uploaded_file.name,
                "saved_name": saved_name,
                "relative_path": f"media/{saved_name}",
                "public_url": public_url,
                "size_bytes": uploaded_file.size,
                "content_type": content_type,
                "classification": classification,
            }
        )

    _write_uploaded_files_json(registered_files)

    return JsonResponse({"success": True, "files": saved_files})


def _classify_and_catalog(saved_path: str, public_url: str) -> dict | None:
    """
    Classifica o arquivo recém-salvo com o pipeline em scripts/ (extrai
    conteúdo, categoriza via Gemini e grava no catálogo local). É best-effort:
    formatos não suportados ou falta de GEMINI_API_KEY não devem derrubar o
    upload, só deixam o arquivo sem classificação.
    """
    try:
        resultado = processar_upload(saved_path, catalog_path=CATALOG_PATH)
    except Exception as exc:  # noqa: BLE001 - classificação é best-effort
        logger.warning("Não foi possível classificar '%s': %s", saved_path, exc)
        return None

    try:
        catalog = FileCatalog(CATALOG_PATH)
        catalog.update_cloud_path(resultado["file_id"], public_url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível vincular a URL pública no catálogo: %s", exc)

    return resultado


def _classify_and_catalog_link(url: str) -> dict | None:
    """Mesma ideia de _classify_and_catalog, mas para um link (URL) em vez de
    um arquivo salvo em disco. Também best-effort."""
    try:
        return processar_upload(url, catalog_path=CATALOG_PATH)
    except Exception as exc:  # noqa: BLE001 - classificação é best-effort
        logger.warning("Não foi possível classificar o link '%s': %s", url, exc)
        return None


@csrf_exempt
@require_http_methods(["POST"])
def add_link(request):
    """Cadastra um link (URL) no mesmo catálogo dos arquivos, com type='link'."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        payload = request.POST

    url = (payload.get("url") or "").strip()
    name = (payload.get("name") or "").strip()

    if not url:
        return JsonResponse({"success": False, "error": "Informe uma URL."}, status=400)

    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        return JsonResponse({"success": False, "error": "URL inválida. Use http:// ou https://"}, status=400)

    if not name:
        name = (parsed.netloc + parsed.path).rstrip("/")

    classification = _classify_and_catalog_link(url)

    entry = {
        "id": f"link_{uuid.uuid4().hex[:8]}",
        "name": name,
        "type": "link",
        "content_type": "text/url",
        "size": 0,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "url": url,
        "category": classification.get("categoria_principal") if classification else None,
        "tags": classification.get("tags", []) if classification else [],
        "description": classification.get("descricao", "") if classification else "",
    }

    registered_files = _read_uploaded_files_json()
    registered_files.insert(0, entry)
    _write_uploaded_files_json(registered_files)

    return JsonResponse({"success": True, "file": entry})


@csrf_exempt
@require_http_methods(["POST"])
def update_file_metadata(request, file_id: str):
    """Permite classificar/taguear manualmente um arquivo quando a
    classificação automática via Gemini não estiver disponível ou tiver
    falhado (sem GEMINI_API_KEY, formato não suportado, erro de rede etc.)."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    registered_files = _read_uploaded_files_json()
    entry = next((f for f in registered_files if f["id"] == file_id), None)
    if entry is None:
        return JsonResponse({"success": False, "error": "Arquivo não encontrado."}, status=404)

    if "category" in payload:
        category = (payload.get("category") or "").strip().lower()
        entry["category"] = category or None

    if "tags" in payload:
        tags = payload.get("tags")
        if not isinstance(tags, list):
            return JsonResponse({"success": False, "error": "'tags' deve ser uma lista."}, status=400)
        entry["tags"] = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()]

    if "description" in payload:
        entry["description"] = (payload.get("description") or "").strip()

    _write_uploaded_files_json(registered_files)
    return JsonResponse({"success": True, "file": entry})


@require_http_methods(["GET"])
def list_uploaded_files(request):
    """Fonte única de verdade: lê data/uploaded_files.json (sem varrer o disco)."""
    response = JsonResponse({"success": True, "files": _read_uploaded_files_json()})
    response["Cache-Control"] = "no-store"
    return response
