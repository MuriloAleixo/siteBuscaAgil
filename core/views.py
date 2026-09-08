from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.core.files.storage import FileSystemStorage
from django.http import HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods

from core import google_drive, uploaded_files_store
from core.models import DriveProfile
from core.tasks import classify_and_catalog_task, classify_link_task, sync_catalog_to_drive
from core.text_match import FUZZY_THRESHOLD, fuzzy_score, normalize
from scripts.analisador_busca import BuscaAnalyzer
from scripts.local_ai.busca_analyzer_local import LocalBuscaAnalyzer
from scripts.local_ai.router import local_ai_habilitada
from scripts.processar_upload import CATEGORIAS_POSSIVEIS

logger = logging.getLogger(__name__)


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


def _render_page(request, template_name: str):
    # Nenhum template usa {% csrf_token %} (não há herança de template —
    # cada HTML é standalone), então sem isso o cookie "csrftoken" nunca é
    # setado e o frontend não teria como mandar o header X-CSRFToken nos
    # endpoints que alteram dado (ver getCsrfToken() em catalog-client.js).
    # get_token() força o cookie a ser setado nesta resposta, em todas as
    # páginas de uma vez, sem precisar decorar cada view individualmente.
    get_token(request)
    return render(request, template_name)


def index(request):
    return _render_page(request, "index.html")


@login_required
def dashboard(request):
    return _render_page(request, "dashboard.html")


@login_required
def search(request):
    return _render_page(request, "search.html")


@login_required
def processing_queue(request):
    return _render_page(request, "processing.html")


@login_required
def upload_page(request):
    return _render_page(request, "upload.html")


@login_required
def profile(request):
    return _render_page(request, "profile.html")


def auth(request):
    """Tela de erro/retry: só é exibida quando o login com Google funcionou
    mas a sincronização inicial com o Drive falhou (ver post_login_sync)."""
    return _render_page(request, "auth.html")


@login_required
def file_view(request):
    return _render_page(request, "file-view.html")


@login_required
def post_login_sync(request):
    """
    Roda logo depois do allauth autenticar o usuário via Google
    (settings.LOGIN_REDIRECT_URL aponta pra cá) e ANTES de qualquer página
    carregar: garante que a pasta "buscaagil_upload" existe no Drive do
    usuário, baixa o uploaded_files.json de lá (se existir) pro cache local,
    e atualiza a cota de armazenamento exibida no perfil.

    Se o Drive falhar aqui (token sem escopo, API fora do ar etc.), manda o
    usuário pra auth.html em vez do dashboard, com um botão pra tentar de
    novo / reconceder acesso.
    """
    try:
        service = google_drive.get_drive_service(request.user)
        folder_id = google_drive.ensure_app_folder(service)
        files, catalog_file_id = google_drive.download_catalog(service, folder_id)

        # Primeiro acesso: a pasta acabou de ser criada e ainda não tem
        # uploaded_files.json dentro. Cria já vazio, em vez de esperar o
        # primeiro upload — assim pasta + catálogo sempre existem juntos.
        if catalog_file_id is None:
            catalog_file_id = google_drive.upload_catalog(service, folder_id, files, None)

        used, total = google_drive.get_storage_quota(service)

        DriveProfile.objects.update_or_create(
            user=request.user,
            defaults={
                "folder_id": folder_id,
                "catalog_file_id": catalog_file_id or "",
                "storage_used_bytes": used,
                "storage_total_bytes": total,
            },
        )
        uploaded_files_store.write_all(request.user.id, files)
    except Exception as exc:  # noqa: BLE001 - qualquer falha de Drive vira retry, não 500
        logger.warning("Falha ao sincronizar Drive no login do usuário %s: %s", request.user.id, exc)
        return redirect("auth")

    return redirect("dashboard")


@login_required
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
        temp_public_url = storage.url(saved_name)
        content_type = getattr(uploaded_file, "content_type", "application/octet-stream")

        # O arquivo é salvo em media/ só como pouso TEMPORÁRIO: o worker
        # Celery classifica via Gemini, sobe pro Drive do usuário e apaga o
        # local (ver core/tasks.py). A entry entra com status="processing" e
        # some do polling quando vira "done" (url passa a ser o link do
        # Drive) ou "error" (arquivo local é mantido pra não perder o dado).
        try:
            async_result = classify_and_catalog_task.delay(
                request.user.id, saved_name, storage.path(saved_name), uploaded_file.name
            )
            entry_status = "processing"
            task_id = async_result.id
        except Exception as exc:  # noqa: BLE001
            # Broker (Redis) fora do ar não pode fazer o arquivo já salvo em
            # media/ sumir sem deixar rastro — sem isso, a entry nunca era
            # criada e o arquivo ficava órfão, invisível em qualquer tela.
            logger.warning("Não foi possível enfileirar a classificação de '%s': %s", uploaded_file.name, exc)
            entry_status = "error"
            task_id = None

        uploaded_files_store.insert_entry(
            request.user.id,
            {
                "id": saved_name,
                "name": uploaded_file.name,
                "type": _categorize_file(saved_name, content_type),
                "content_type": content_type,
                "size": uploaded_file.size,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
                # Aponta pro arquivo local temporário até o worker terminar
                # o upload pro Drive — o polling em /files/<id>/status troca
                # esse valor pelo link do Drive quando status vira "done".
                "url": temp_public_url,
                "status": entry_status,
                "category": None,
                "tags": [],
                "description": "",
                "scores": {},
                "confidence": None,
                "classification_source": None,
                "task_id": task_id,
            },
        )

        saved_files.append(
            {
                "original_name": uploaded_file.name,
                "saved_name": saved_name,
                "public_url": temp_public_url,
                "size_bytes": uploaded_file.size,
                "content_type": content_type,
                "status": entry_status,
                "task_id": task_id,
            }
        )

    return JsonResponse({"success": True, "files": saved_files})


@login_required
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
    try:
        async_result = classify_link_task.delay(request.user.id, entry_id, url)
        entry_status = "processing"
        task_id = async_result.id
    except Exception as exc:  # noqa: BLE001 - broker fora do ar não pode fazer o link cadastrado
        # sumir sem deixar rastro (sem isso, a entry nunca era criada).
        logger.warning("Não foi possível enfileirar a classificação do link '%s': %s", url, exc)
        entry_status = "error"
        task_id = None

    entry = {
        "id": entry_id,
        "name": name,
        "type": "link",
        "content_type": "text/url",
        "size": 0,
        "created_at": datetime.now(tz=timezone.utc).isoformat(),
        "url": url,
        "status": entry_status,
        "category": None,
        "tags": [],
        "description": "",
        "scores": {},
        "confidence": None,
        "classification_source": None,
        "task_id": task_id,
    }

    uploaded_files_store.insert_entry(request.user.id, entry)

    return JsonResponse({"success": True, "file": entry})


@login_required
@require_http_methods(["POST"])
def update_file_metadata(request, file_id: str):
    """Permite classificar/taguear manualmente um arquivo quando a
    classificação automática via Gemini não estiver disponível ou tiver
    falhado (sem GEMINI_API_KEY, formato não suportado, erro de rede etc.)."""
    try:
        payload = json.loads(request.body or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"success": False, "error": "JSON inválido."}, status=400)

    registered_files = uploaded_files_store.read_all(request.user.id)
    entry = next((f for f in registered_files if f["id"] == file_id), None)
    if entry is None:
        return JsonResponse({"success": False, "error": "Arquivo não encontrado."}, status=404)

    if "category" in payload:
        category = (payload.get("category") or "").strip().lower()
        entry["category"] = category or None
        # Categoria escolhida à mão pelo usuário: os scores da classificação
        # automática (se houver) não fazem mais sentido pra essa entry — sem
        # isso, a badge de "baixa confiança" continuaria aparecendo mesmo
        # depois do usuário confirmar/corrigir a categoria.
        entry["scores"] = {}
        entry["confidence"] = None
        entry["classification_source"] = "manual"

    if "tags" in payload:
        tags = payload.get("tags")
        if not isinstance(tags, list):
            return JsonResponse({"success": False, "error": "'tags' deve ser uma lista."}, status=400)
        entry["tags"] = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()]

    if "description" in payload:
        entry["description"] = (payload.get("description") or "").strip()

    uploaded_files_store.write_all(request.user.id, registered_files)
    return JsonResponse({"success": True, "file": entry})


@login_required
@require_http_methods(["GET"])
def list_uploaded_files(request):
    """Fonte única de verdade no processo web: lê o cache local
    (data/users/<id>.json), que é espelho do uploaded_files.json na
    pasta do usuário no Drive."""
    response = JsonResponse({"success": True, "files": uploaded_files_store.read_all(request.user.id)})
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_http_methods(["GET"])
def file_status(request, file_id: str):
    """
    Consulta o status de classificação/upload assíncrono de um arquivo/link
    (status: "processing" | "done" | "error"). O front-end usa isso pra dar
    polling depois do upload, já que a classificação e o envio ao Drive
    rodam num worker Celery separado, fora da request de upload.
    """
    entry = uploaded_files_store.get_entry(request.user.id, file_id)
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
            "url": entry.get("url"),
            "task_id": entry.get("task_id"),
        }
    )
    response["Cache-Control"] = "no-store"
    return response


@login_required
@require_http_methods(["GET"])
def download_file(request, file_id: str):
    """Baixa o conteúdo real do arquivo do Drive do usuário e devolve como
    anexo (Content-Disposition), em vez de mandar o usuário pro visualizador
    do Drive (webViewLink). Links não têm arquivo físico associado."""
    entry = uploaded_files_store.get_entry(request.user.id, file_id)
    if entry is None:
        return JsonResponse({"success": False, "error": "Arquivo não encontrado."}, status=404)

    drive_file_id = entry.get("drive_file_id")
    if entry.get("type") == "link" or not drive_file_id:
        return JsonResponse(
            {"success": False, "error": "Este item não possui um arquivo para baixar."}, status=400
        )

    try:
        service = google_drive.get_drive_service(request.user)
        content, drive_name, mimetype = google_drive.download_file(service, drive_file_id)
    except google_drive.DriveNotConnectedError as exc:
        return JsonResponse({"success": False, "error": str(exc)}, status=401)
    except Exception as exc:  # noqa: BLE001 - qualquer falha do Drive vira erro amigável, não 500
        logger.warning("Falha ao baixar '%s' do Drive: %s", file_id, exc)
        return JsonResponse(
            {"success": False, "error": "Não foi possível baixar o arquivo do Drive."}, status=502
        )

    filename = entry.get("name") or drive_name
    response = HttpResponse(content, content_type=mimetype)
    response["Content-Length"] = str(len(content))
    # filename= (ASCII, fallback) + filename*= (UTF-8, RFC 5987) para nomes com acentos.
    ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "arquivo"
    response["Content-Disposition"] = (
        f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(filename)}'
    )
    return response


@login_required
@require_http_methods(["POST"])
def delete_file(request, file_id: str):
    """Remove o arquivo do Drive do usuário (se houver) e do catálogo local,
    sincronizando o uploaded_files.json de volta pro Drive em seguida."""
    entry = uploaded_files_store.get_entry(request.user.id, file_id)
    if entry is None:
        return JsonResponse({"success": False, "error": "Arquivo não encontrado."}, status=404)

    drive_file_id = entry.get("drive_file_id")
    service = None
    if drive_file_id:
        try:
            service = google_drive.get_drive_service(request.user)
            google_drive.delete_file(service, drive_file_id)
        except google_drive.DriveNotConnectedError as exc:
            return JsonResponse({"success": False, "error": str(exc)}, status=401)
        except Exception as exc:  # noqa: BLE001 - qualquer falha do Drive vira erro amigável, não 500
            logger.warning("Falha ao remover '%s' do Drive: %s", file_id, exc)
            return JsonResponse({"success": False, "error": "Não foi possível remover o arquivo do Drive."}, status=502)
    else:
        # Nunca chegou a subir pro Drive (ex.: falhou ao enfileirar a
        # classificação) — o arquivo real, se ainda existir, está só em
        # media/ como pouso temporário. Sem isso, ele ficava órfão pra
        # sempre, mesmo depois de "excluído" aqui.
        local_path = Path(settings.MEDIA_ROOT) / file_id
        try:
            local_path.unlink()
        except FileNotFoundError:
            pass
        except OSError as exc:
            logger.warning("Não foi possível remover o arquivo local '%s': %s", local_path, exc)

    registered_files = [f for f in uploaded_files_store.read_all(request.user.id) if f["id"] != file_id]
    uploaded_files_store.write_all(request.user.id, registered_files)

    try:
        service = service or google_drive.get_drive_service(request.user)
        sync_catalog_to_drive(service, request.user.id)
    except Exception as exc:  # noqa: BLE001 - arquivo já foi removido; sincronizar o catálogo é best-effort
        logger.warning("Arquivo removido, mas falhou sincronizar uploaded_files.json: %s", exc)

    return JsonResponse({"success": True})


def _file_relevance(entry: dict, categories: list[str], tags: list[str], query: str) -> float:
    """Score de relevância (0-100) do arquivo pra essa busca; 0 = não bate.
    Único critério de match usado pelo backend — a mesma lógica (normalizar
    acento + fuzzy) é portada em static/js/catalog-client.js pro fallback
    local, pra não ter mais dois motores de busca com critérios diferentes.
    """
    norm_categories = [normalize(c) for c in categories]
    norm_tags = [normalize(t) for t in tags]

    file_category = normalize(entry.get("category"))
    file_tags = [normalize(t) for t in (entry.get("tags") or [])]
    name = entry.get("name") or ""
    description = entry.get("description") or ""

    if norm_categories and file_category in norm_categories:
        return 100.0
    if norm_tags and any(t in file_tags for t in norm_tags):
        return 98.0

    # As tags/sinônimos que o Gemini sugeriu (ver analisador_busca.py) também
    # contam se aparecerem (mesmo com erro de digitação) na descrição/nome —
    # muita busca não bate com nenhuma tag literal, mas está claramente
    # descrita no resumo do arquivo (ex.: tag "março" batendo em "fechamento
    # de marco", sem acento).
    tag_hint_scores = [fuzzy_score(t, name) for t in norm_tags] + [fuzzy_score(t, description) for t in norm_tags]

    # Fallback: fuzzy matching (tolera acento e erro de digitação) no
    # nome/descrição/categoria/tags, no lugar do antigo substring exato
    # ("in") — garante que a busca nunca fica pior que a antiga por causa de
    # falha/ausência da análise via Gemini (sem GEMINI_API_KEY, erro de rede
    # etc.), e agora perdoa typo/acento nesse caso também.
    haystack = " ".join(filter(None, [name, description, entry.get("category") or "", " ".join(entry.get("tags") or [])]))
    fallback_score = fuzzy_score(query, haystack)

    return max([fallback_score, *tag_hint_scores], default=0.0)


@login_required
@require_http_methods(["GET"])
def smart_search(request):
    """
    Busca assistida por IA: envia o texto do campo de busca para o Gemini,
    que devolve as categorias/tags candidatas mais prováveis, e usa isso
    para filtrar/ranquear o catálogo local do usuário por categoria, tags e
    também pela descrição gerada na classificação (ver _file_relevance).
    """
    query = (request.GET.get("q") or "").strip()
    all_files = uploaded_files_store.read_all(request.user.id)

    if not query:
        response = JsonResponse({"success": True, "query": "", "categories": [], "tags": [], "files": all_files})
        response["Cache-Control"] = "no-store"
        return response

    known_tags = sorted({tag for f in all_files for tag in (f.get("tags") or [])})

    categories: list[str] = []
    tags: list[str] = []
    analise = None
    if local_ai_habilitada():
        try:
            analise = LocalBuscaAnalyzer().analisar(query, CATEGORIAS_POSSIVEIS, known_tags)
        except Exception as exc:  # noqa: BLE001 - IA local é best-effort, cai pro Gemini
            logger.warning("IA local não conseguiu analisar a busca '%s', caindo pro Gemini: %s", query, exc)

    if analise is None:
        try:
            analise = BuscaAnalyzer().analisar(query, CATEGORIAS_POSSIVEIS, known_tags)
        except Exception as exc:  # noqa: BLE001 - busca assistida é best-effort
            logger.warning("Não foi possível analisar a busca '%s' via Gemini: %s", query, exc)

    if analise is not None:
        categories = [c.strip().lower() for c in analise.categorias if c.strip()]
        tags = [t.strip().lower() for t in analise.tags if t.strip()]

    # Ordena por relevância (categoria/tag exata > tag aproximada na
    # descrição/nome > fuzzy match geral) em vez de devolver na ordem crua
    # do catálogo.
    scored = [(f, _file_relevance(f, categories, tags, query)) for f in all_files]
    matched = [f for f, score in sorted(scored, key=lambda item: item[1], reverse=True) if score >= FUZZY_THRESHOLD]

    response = JsonResponse(
        {"success": True, "query": query, "categories": categories, "tags": tags, "files": matched}
    )
    response["Cache-Control"] = "no-store"
    return response
