from __future__ import annotations

import json
import logging
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

from core import uploaded_files_store
from core.tasks import classify_and_catalog_task, classify_link_task
from scripts.analisador_busca import BuscaAnalyzer
from scripts.processar_upload import CATEGORIAS_POSSIVEIS

logger = logging.getLogger(__name__)

_read_uploaded_files_json = uploaded_files_store.read_all
_write_uploaded_files_json = uploaded_files_store.write_all


EXTENSION_TYPE_MAP = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".webp": "image", ".svg": "image",
    ".pdf": "pdf",
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video", ".webm": "video", ".wmv": "video",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio",
    ".xlsx": "sheet", ".xls": "sheet", ".csv": "sheet",
    ".doc": "doc", ".docx": "doc", ".txt": "doc", ".py": "doc",
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
    for uploaded_file in uploaded_files:
        saved_name = storage.save(uploaded_file.name, uploaded_file)
        public_url = storage.url(saved_name)
        content_type = getattr(uploaded_file, "content_type", "application/octet-stream")

        # A classificação via Gemini roda num worker Celery separado (fila
        # Redis) — a request não espera por ela, a entry entra com
        # status="processing" e é atualizada de forma assíncrona depois.
        async_result = classify_and_catalog_task.delay(saved_name, storage.path(saved_name), public_url)

        uploaded_files_store.insert_entry(
            {
                "id": saved_name,
                "name": uploaded_file.name,
                "type": _categorize_file(saved_name, content_type),
                "content_type": content_type,
                "size": uploaded_file.size,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                "url": public_url,
                "status": "processing",
                "category": None,
                "tags": [],
                "description": "",
                "task_id": async_result.id,
            }
        )

        saved_files.append(
            {
                "original_name": uploaded_file.name,
                "saved_name": saved_name,
                "relative_path": f"media/{saved_name}",
                "public_url": public_url,
                "size_bytes": uploaded_file.size,
                "content_type": content_type,
                "status": "processing",
                "task_id": async_result.id,
            }
        )

    return JsonResponse({"success": True, "files": saved_files})


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

    entry_id = f"link_{uuid.uuid4().hex[:8]}"
    async_result = classify_link_task.delay(entry_id, url)

    entry = {
        "id": entry_id,
        "name": name,
        "type": "link",
        "content_type": "text/url",
        "size": 0,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "url": url,
        "status": "processing",
        "category": None,
        "tags": [],
        "description": "",
        "task_id": async_result.id,
    }

    uploaded_files_store.insert_entry(entry)

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


@require_http_methods(["GET"])
def file_status(request, file_id: str):
    """
    Consulta o status de classificação assíncrona de um arquivo/link
    (status: "processing" | "done" | "error"). O front-end usa isso pra dar
    polling depois do upload, já que a classificação via Gemini roda num
    worker Celery separado, fora da request de upload.
    """
    entry = uploaded_files_store.get_entry(file_id)
    if entry is None:
        return JsonResponse({"success": False, "error": "Arquivo não encontrado."}, status=404)

    response = JsonResponse(
        {
            "success": True,
            "id": entry["id"],
            "status": entry.get("status", "done"),
            "category": entry.get("category"),
            "tags": entry.get("tags", []),
            "description": entry.get("description", ""),
            "task_id": entry.get("task_id"),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


def _file_matches(entry: dict, categories: list[str], tags: list[str], query_lower: str) -> bool:
    file_category = (entry.get("category") or "").lower()
    file_tags = [t.lower() for t in (entry.get("tags") or [])]

    if categories and file_category in categories:
        return True
    if tags and any(t in file_tags for t in tags):
        return True

    # Fallback: substring simples no nome/descrição/categoria/tags. Garante
    # que a busca nunca fica pior que a antiga por causa de falha/ausência
    # da análise via Gemini (sem GEMINI_API_KEY, erro de rede etc.).
    haystack = " ".join(
        [entry.get("name", ""), entry.get("description", ""), file_category, " ".join(file_tags)]
    ).lower()
    return query_lower in haystack


@require_http_methods(["GET"])
def smart_search(request):
    """
    Busca assistida por IA: envia o texto do campo de busca para o Gemini,
    que devolve as categorias/tags candidatas mais prováveis, e usa isso
    para filtrar data/uploaded_files.json por categoria e/ou tags.
    """
    query = (request.GET.get("q") or "").strip()
    all_files = _read_uploaded_files_json()

    if not query:
        response = JsonResponse({"success": True, "query": "", "categories": [], "tags": [], "files": all_files})
        response["Cache-Control"] = "no-store"
        return response

    known_tags = sorted({tag for f in all_files for tag in (f.get("tags") or [])})

    categories: list[str] = []
    tags: list[str] = []
    try:
        analyzer = BuscaAnalyzer()
        analise = analyzer.analisar(query, CATEGORIAS_POSSIVEIS, known_tags)
        categories = [c.strip().lower() for c in analise.categorias if c.strip()]
        tags = [t.strip().lower() for t in analise.tags if t.strip()]
    except Exception as exc:  # noqa: BLE001 - busca assistida é best-effort
        logger.warning("Não foi possível analisar a busca '%s' via Gemini: %s", query, exc)

    query_lower = query.lower()
    matched = [f for f in all_files if _file_matches(f, categories, tags, query_lower)]

    response = JsonResponse(
        {"success": True, "query": query, "categories": categories, "tags": tags, "files": matched}
    )
    response["Cache-Control"] = "no-store"
    return response
