from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods


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
        saved_files.append(
            {
                "original_name": uploaded_file.name,
                "saved_name": saved_name,
                "relative_path": f"media/{saved_name}",
                "public_url": storage.url(saved_name),
                "size_bytes": uploaded_file.size,
                "content_type": getattr(uploaded_file, "content_type", "application/octet-stream"),
            }
        )

    return JsonResponse({"success": True, "files": saved_files})
