"""
api/app.py

Rotas HTTP do BuscaÁgil (era core/views.py + core/urls.py, em Django). Só a
API: as páginas HTML/CSS/JS são estáticas e servidas pelo container
`frontend` (nginx), que faz proxy_pass das rotas abaixo pra este serviço.

Sem ORM, sem sessão em banco: usuário = `session["user_id"]` (cookie
assinado, ver api/auth.py); catálogo e perfil = JSON em disco (ver
api/stores.py); fila = Celery/Redis (ver worker/).
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlparse

import redis as redis_lib
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.utils import secure_filename

from api import google_drive, processing_log, stores
from api.auth import auth_bp, current_user_id, login_required
from api.csrf import init_csrf
from api.text_match import FALLBACK_FUZZY_THRESHOLD, FUZZY_THRESHOLD, fuzzy_score, normalize
from scripts.analisador_busca import BuscaAnalyzer
from scripts.local_ai.busca_analyzer_local import LocalBuscaAnalyzer
from scripts.local_ai.router import local_ai_habilitada
from worker.celery_app import app as celery_app
from worker.tasks import classify_and_catalog_task, classify_link_task, reclassify_task, sync_catalog_to_drive

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent.parent
MEDIA_ROOT = Path(os.environ.get("BUSCA_AGIL_MEDIA_DIR", BASE_DIR / "media"))

EXTENSION_TYPE_MAP = {
    ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image", ".webp": "image", ".svg": "image",
    ".pdf": "pdf",
    ".mp4": "video", ".mov": "video", ".avi": "video", ".mkv": "video", ".webm": "video", ".wmv": "video",
    ".mp3": "audio", ".wav": "audio", ".ogg": "audio", ".m4a": "audio",
    ".xlsx": "sheet", ".xls": "sheet", ".csv": "sheet",
    ".doc": "doc", ".docx": "doc", ".txt": "doc", ".py": "doc", ".pptx": "doc", ".ppt": "doc",
    ".zip": "archive", ".rar": "archive", ".tar": "archive", ".gz": "archive", ".7z": "archive",
}


def create_app() -> Flask:
    app = Flask(__name__)

    secret_key = os.environ.get("FLASK_SECRET_KEY") or "busca-agil-insecure-dev-key"
    debug = os.environ.get("FLASK_DEBUG", "true").strip().lower() in ("1", "true", "yes", "on")
    if not debug and secret_key == "busca-agil-insecure-dev-key":
        raise RuntimeError(
            "FLASK_DEBUG=false mas FLASK_SECRET_KEY não foi definida — gere uma chave "
            "segura (ex.: `python -c \"import secrets; print(secrets.token_urlsafe(50))\"`) "
            "e defina FLASK_SECRET_KEY no .env antes de rodar em produção."
        )
    app.secret_key = secret_key
    app.config.update(SESSION_COOKIE_SAMESITE="Lax", SESSION_COOKIE_SECURE=not debug)

    init_csrf(app)
    app.register_blueprint(auth_bp)

    redis_client = redis_lib.Redis.from_url(
        os.environ.get("CELERY_BROKER_URL", "redis://redis:6379/0")
    )

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

    def _save_upload(file_storage) -> tuple[str, str]:
        """Salva em media/ (pouso TEMPORÁRIO: o worker sobe pro Drive do
        usuário e apaga o local em seguida, ver worker/tasks.py). Nome único
        pra não colidir com uploads simultâneos de arquivos com mesmo nome."""
        original_name = file_storage.filename or "arquivo"
        safe_name = secure_filename(original_name) or "arquivo"
        saved_name = f"{uuid.uuid4().hex}_{safe_name}"
        MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
        dest = MEDIA_ROOT / saved_name
        file_storage.save(dest)
        return saved_name, str(dest)

    @app.get("/media/<path:filename>")
    @login_required
    def media_file(filename: str):
        return send_from_directory(MEDIA_ROOT, filename)

    @app.post("/upload")
    @login_required
    def upload_files():
        user_id = current_user_id()
        uploaded_files = request.files.getlist("files")
        if not uploaded_files:
            return jsonify({"success": False, "error": "Nenhum arquivo foi recebido."}), 400

        saved_files = []
        for uploaded_file in uploaded_files:
            saved_name, saved_path = _save_upload(uploaded_file)
            content_type = uploaded_file.content_type or "application/octet-stream"
            temp_public_url = f"/media/{saved_name}"

            # O arquivo é salvo em media/ só como pouso TEMPORÁRIO: o worker
            # classifica, sobe pro Drive do usuário e apaga o local (ver
            # worker/tasks.py). A entry entra com status="processing" e some
            # do polling quando vira "done" (url passa a ser o link do
            # Drive) ou "error" (arquivo local é mantido pra não perder o
            # dado).
            try:
                async_result = classify_and_catalog_task.delay(
                    user_id, saved_name, saved_path, uploaded_file.filename
                )
                entry_status = "processing"
                task_id = async_result.id
            except Exception as exc:  # noqa: BLE001
                # Broker (Redis) fora do ar não pode fazer o arquivo já salvo
                # em media/ sumir sem deixar rastro — sem isso, a entry nunca
                # era criada e o arquivo ficava órfão, invisível em qualquer
                # tela.
                logger.warning("Não foi possível enfileirar a classificação de '%s': %s", uploaded_file.filename, exc)
                entry_status = "error"
                task_id = None

            now_iso = datetime.now(tz=timezone.utc).isoformat()
            stores.insert_entry(
                user_id,
                {
                    "id": saved_name,
                    "name": uploaded_file.filename,
                    "type": _categorize_file(saved_name, content_type),
                    "content_type": content_type,
                    "size": os.path.getsize(saved_path),
                    "created_at": now_iso,
                    # Quando a tentativa de processamento ATUAL começou —
                    # igual a created_at na primeira vez, mas reprocess_file/
                    # restart_file atualizam isso sozinhos, pra tela de
                    # Histórico mostrar "há Xs/min" contado a partir da
                    # tentativa em andamento, não do upload original (ver
                    # static/js/processing.js::renderHistoryItem).
                    "processing_started_at": now_iso,
                    "url": temp_public_url,
                    "status": entry_status,
                    "category": None,
                    "tags": [],
                    "description": "",
                    "confidence": None,
                    "classification_source": None,
                    "task_id": task_id,
                },
            )

            saved_files.append(
                {
                    "original_name": uploaded_file.filename,
                    "saved_name": saved_name,
                    "public_url": temp_public_url,
                    "size_bytes": os.path.getsize(saved_path),
                    "content_type": content_type,
                    "status": entry_status,
                    "task_id": task_id,
                }
            )

        return jsonify({"success": True, "files": saved_files})

    @app.post("/add-link")
    @login_required
    def add_link():
        """Cadastra um link (URL) no mesmo catálogo dos arquivos, com type='link'."""
        user_id = current_user_id()
        payload = request.get_json(silent=True) or {}

        url = (payload.get("url") or "").strip()
        name = (payload.get("name") or "").strip()

        if not url:
            return jsonify({"success": False, "error": "Informe uma URL."}), 400

        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return jsonify({"success": False, "error": "URL inválida. Use http:// ou https://"}), 400

        if not name:
            name = (parsed.netloc + parsed.path).rstrip("/")

        entry_id = f"link_{uuid.uuid4().hex[:8]}"
        try:
            async_result = classify_link_task.delay(user_id, entry_id, url)
            entry_status = "processing"
            task_id = async_result.id
        except Exception as exc:  # noqa: BLE001 - broker fora do ar não pode fazer o link
            # cadastrado sumir sem deixar rastro (sem isso, a entry nunca era criada).
            logger.warning("Não foi possível enfileirar a classificação do link '%s': %s", url, exc)
            entry_status = "error"
            task_id = None

        link_now_iso = datetime.now(tz=timezone.utc).isoformat()
        entry = {
            "id": entry_id,
            "name": name,
            "type": "link",
            "content_type": "text/url",
            "size": 0,
            "created_at": link_now_iso,
            "processing_started_at": link_now_iso,
            "url": url,
            "status": entry_status,
            "category": None,
            "tags": [],
            "description": "",
            "confidence": None,
            "classification_source": None,
            "task_id": task_id,
        }

        stores.insert_entry(user_id, entry)
        return jsonify({"success": True, "file": entry})

    @app.post("/files/<file_id>/update")
    @login_required
    def update_file_metadata(file_id: str):
        """Permite classificar/taguear manualmente um arquivo quando a
        classificação automática não estiver disponível ou tiver falhado."""
        user_id = current_user_id()
        payload = request.get_json(silent=True)
        if payload is None:
            return jsonify({"success": False, "error": "JSON inválido."}), 400

        registered_files = stores.read_all(user_id)
        entry = next((f for f in registered_files if f["id"] == file_id), None)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        if "category" in payload:
            category = (payload.get("category") or "").strip().lower()
            entry["category"] = category or None
            # Categoria escolhida à mão pelo usuário: a confiança da
            # classificação automática (se houver) não faz mais sentido —
            # sem isso, a badge de "baixa confiança" continuaria aparecendo
            # mesmo depois do usuário confirmar/corrigir a categoria.
            entry["confidence"] = None
            entry["classification_source"] = "manual"

        if "tags" in payload:
            tags = payload.get("tags")
            if not isinstance(tags, list):
                return jsonify({"success": False, "error": "'tags' deve ser uma lista."}), 400
            entry["tags"] = [t.strip().lower() for t in tags if isinstance(t, str) and t.strip()]

        if "description" in payload:
            entry["description"] = (payload.get("description") or "").strip()

        stores.write_all(user_id, registered_files)
        return jsonify({"success": True, "file": entry})

    @app.post("/files/<file_id>/reprocess")
    @login_required
    def reprocess_file(file_id: str):
        """Reclassifica um item já existente no catálogo sem reenviar o
        arquivo do zero — baixa de novo do Drive (arquivo) ou usa a URL
        direto (link), ver worker/tasks.py::_run_reclassification. Útil
        quando a classificação original falhou por instabilidade passageira
        da IA local/Gemini (ver GET /processing-log pro motivo)."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        # Marca "processing" ANTES de enfileirar: se a tarefa rodar rápido
        # (arquivo pequeno), o worker pode terminar e gravar "done" antes
        # desta função continuar — fazendo nessa ordem, o pior caso é só
        # gravar "processing" de novo em cima de um estado que já mudou,
        # nunca o contrário (voltar "done"/"error" pra "processing" por cima
        # do resultado real). processing_started_at reinicia a contagem de
        # tempo mostrada na tela de Histórico (senão continuaria mostrando
        # "há 3 dias" — o upload original — em vez de "há 2s", que é quando
        # esta tentativa de fato começou).
        stores.update_entry(
            user_id, file_id, status="processing", processing_started_at=datetime.now(tz=timezone.utc).isoformat()
        )
        try:
            async_result = reclassify_task.delay(user_id, file_id)
        except Exception as exc:  # noqa: BLE001 - broker fora do ar não pode virar 500
            logger.warning("Não foi possível enfileirar reprocessamento de '%s': %s", file_id, exc)
            stores.update_entry(user_id, file_id, status="error")
            return jsonify({"success": False, "error": "Fila de processamento indisponível no momento."}), 503

        stores.update_entry(user_id, file_id, task_id=async_result.id)
        return jsonify({"success": True, "id": file_id, "status": "processing", "task_id": async_result.id})

    def _revoke_task(task_id: str | None) -> None:
        """Mata a tarefa Celery em andamento (se houver). `terminate=True`
        manda SIGTERM pro processo do worker que está executando ela —
        único jeito de interromper de verdade uma classificação no meio
        (é uma chamada síncrona/bloqueante pro Ollama/Gemini/ffmpeg, sem
        checkpoint no meio pra "pausar e retomar"). Best-effort: o Celery só
        manda o sinal pelo broker, não confirma na hora que o worker já
        morreu — por isso `cancel_file`/`restart_file` também marcam o
        catálogo direto, em vez de esperar o worker reagir sozinho."""
        if not task_id:
            return
        try:
            celery_app.control.revoke(task_id, terminate=True, signal="SIGTERM")
        except Exception as exc:  # noqa: BLE001 - best-effort
            logger.warning("Não foi possível revogar a tarefa '%s': %s", task_id, exc)

    @app.post("/files/<file_id>/cancel")
    @login_required
    def cancel_file(file_id: str):
        """Cancela uma classificação em andamento. Ver _revoke_task sobre a
        janela de corrida: se o worker terminar bem na hora em que o sinal
        chega, o resultado dele pode sobrescrever este "error" logo depois
        — raro, e sem jeito de evitar sem redesenhar o worker pra checar um
        estado compartilhado a cada etapa."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404
        if entry.get("status") != "processing":
            return jsonify({"success": False, "error": "Este item não está em processamento."}), 409

        task_id = entry.get("task_id")
        _revoke_task(task_id)
        stores.update_entry(user_id, file_id, status="error")
        processing_log.log_event(user_id, file_id, "task", "error", "Cancelado pelo usuário", task_id=task_id)
        return jsonify({"success": True, "id": file_id, "status": "error"})

    @app.post("/files/<file_id>/restart")
    @login_required
    def restart_file(file_id: str):
        """Reinicia a classificação de um item — cancela a tarefa atual (se
        ainda estiver rodando) e dispara uma nova, escolhendo a tarefa certa
        conforme o que já foi feito: link classifica direto pela URL; arquivo
        já enviado ao Drive reclassifica sem reenviar (reclassify_task, como
        POST /files/<id>/reprocess); arquivo cujo upload original nem
        terminou ainda usa o arquivo local em media/ (só existe se o
        cancelamento/erro aconteceu antes do upload confirmar)."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        _revoke_task(entry.get("task_id"))
        # processing_started_at reinicia a contagem de tempo na tela de
        # Histórico — mesmo motivo do reprocess_file acima.
        stores.update_entry(
            user_id, file_id, status="processing", processing_started_at=datetime.now(tz=timezone.utc).isoformat()
        )

        try:
            if entry.get("type") == "link":
                async_result = classify_link_task.delay(user_id, file_id, entry["url"])
            elif entry.get("drive_file_id"):
                async_result = reclassify_task.delay(user_id, file_id)
            else:
                saved_path = MEDIA_ROOT / file_id
                if not saved_path.exists():
                    stores.update_entry(user_id, file_id, status="error")
                    return jsonify({
                        "success": False,
                        "error": "O arquivo original não está mais disponível pra reiniciar — envie de novo.",
                    }), 409
                async_result = classify_and_catalog_task.delay(user_id, file_id, str(saved_path), entry["name"])
        except Exception as exc:  # noqa: BLE001 - broker fora do ar não pode virar 500
            logger.warning("Não foi possível reiniciar o processamento de '%s': %s", file_id, exc)
            stores.update_entry(user_id, file_id, status="error")
            return jsonify({"success": False, "error": "Fila de processamento indisponível no momento."}), 503

        stores.update_entry(user_id, file_id, task_id=async_result.id)
        return jsonify({"success": True, "id": file_id, "status": "processing", "task_id": async_result.id})

    @app.get("/files")
    @login_required
    def list_uploaded_files():
        """Fonte única de verdade no processo api: lê o cache local
        (data/users/<id>/catalog.json), espelho do uploaded_files.json na
        pasta do usuário no Drive."""
        user_id = current_user_id()
        response = jsonify({"success": True, "files": stores.read_all(user_id)})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/files/<file_id>/status")
    @login_required
    def file_status(file_id: str):
        """Status de classificação/upload assíncrono (processing/done/error)
        — usado pro polling do frontend depois de um upload/link."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        response = jsonify(
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
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/files/<file_id>/download")
    @login_required
    def download_file(file_id: str):
        """Baixa o conteúdo real do arquivo do Drive do usuário, como anexo,
        em vez de mandar pro visualizador do Drive."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        drive_file_id = entry.get("drive_file_id")
        if entry.get("type") == "link" or not drive_file_id:
            return jsonify({"success": False, "error": "Este item não possui um arquivo para baixar."}), 400

        try:
            service = google_drive.get_drive_service(user_id)
            content, drive_name, mimetype = google_drive.download_file(service, drive_file_id)
        except google_drive.DriveNotConnectedError as exc:
            return jsonify({"success": False, "error": str(exc)}), 401
        except Exception as exc:  # noqa: BLE001 - qualquer falha do Drive vira erro amigável, não 500
            logger.warning("Falha ao baixar '%s' do Drive: %s", file_id, exc)
            return jsonify({"success": False, "error": "Não foi possível baixar o arquivo do Drive."}), 502

        filename = entry.get("name") or drive_name
        ascii_fallback = filename.encode("ascii", "ignore").decode("ascii") or "arquivo"
        response = app.response_class(content, mimetype=mimetype)
        response.headers["Content-Length"] = str(len(content))
        response.headers["Content-Disposition"] = (
            f'attachment; filename="{ascii_fallback}"; filename*=UTF-8\'\'{quote(filename)}'
        )
        return response

    @app.post("/files/<file_id>/delete")
    @login_required
    def delete_file(file_id: str):
        """Remove o arquivo do Drive do usuário (se houver) e do catálogo
        local, sincronizando o uploaded_files.json de volta pro Drive."""
        user_id = current_user_id()
        entry = stores.get_entry(user_id, file_id)
        if entry is None:
            return jsonify({"success": False, "error": "Arquivo não encontrado."}), 404

        drive_file_id = entry.get("drive_file_id")
        service = None
        if drive_file_id:
            try:
                service = google_drive.get_drive_service(user_id)
                google_drive.delete_file(service, drive_file_id)
            except google_drive.DriveNotConnectedError as exc:
                return jsonify({"success": False, "error": str(exc)}), 401
            except Exception as exc:  # noqa: BLE001 - qualquer falha do Drive vira erro amigável, não 500
                logger.warning("Falha ao remover '%s' do Drive: %s", file_id, exc)
                return jsonify({"success": False, "error": "Não foi possível remover o arquivo do Drive."}), 502
        else:
            # Nunca chegou a subir pro Drive (ex.: falhou ao enfileirar a
            # classificação) — o arquivo real, se ainda existir, está só em
            # media/ como pouso temporário. Sem isso, ele ficava órfão pra
            # sempre, mesmo depois de "excluído" aqui.
            local_path = MEDIA_ROOT / file_id
            try:
                local_path.unlink()
            except FileNotFoundError:
                pass
            except OSError as exc:
                logger.warning("Não foi possível remover o arquivo local '%s': %s", local_path, exc)

        registered_files = [f for f in stores.read_all(user_id) if f["id"] != file_id]
        stores.write_all(user_id, registered_files)

        try:
            service = service or google_drive.get_drive_service(user_id)
            sync_catalog_to_drive(service, user_id)
        except Exception as exc:  # noqa: BLE001 - arquivo já removido; sincronizar é best-effort
            logger.warning("Arquivo removido, mas falhou sincronizar uploaded_files.json: %s", exc)

        return jsonify({"success": True})

    def _file_relevance(entry: dict, categories: list[str], tags: list[str], query: str) -> float:
        """Score de relevância (0-100) do arquivo pra essa busca; 0 = não
        bate. Único critério de match usado pelo backend — a mesma lógica
        (normalizar acento + fuzzy) é portada em
        static/js/catalog-client.js pro fallback local.

        Tiers em ordem de confiança:
          1. categoria/tag exata sugerida pela IA (100/98)
          2. consulta aparece literalmente no nome do arquivo (96) — sinal
             forte demais pra depender só da IA ter sugerido a tag certa;
             continua funcionando mesmo se a análise de busca falhar/for
             fraca (evita falso negativo).
          3. tag sugerida aparece (fuzzy) no nome/descrição
          4. fallback solto: fuzzy sobre nome+descrição+categoria+tags, com
             piso mais alto (FALLBACK_FUZZY_THRESHOLD) pra não deixar
             query curta bater raso em qualquer coisa (evita falso
             positivo).
        """
        norm_categories = [normalize(c) for c in categories]
        norm_tags = [normalize(t) for t in tags]

        file_category = normalize(entry.get("category"))
        file_tags = [normalize(t) for t in (entry.get("tags") or [])]
        name = entry.get("name") or ""
        description = entry.get("description") or ""
        norm_query = normalize(query)
        norm_name = normalize(name)

        if norm_categories and file_category in norm_categories:
            return 100.0
        if norm_tags and any(t in file_tags for t in norm_tags):
            return 98.0
        if norm_query and norm_query in norm_name:
            return 96.0

        tag_hint_scores = [fuzzy_score(t, name) for t in norm_tags] + [fuzzy_score(t, description) for t in norm_tags]

        haystack = " ".join(
            filter(None, [name, description, entry.get("category") or "", " ".join(entry.get("tags") or [])])
        )
        fallback_score = fuzzy_score(query, haystack)
        if fallback_score < FALLBACK_FUZZY_THRESHOLD:
            fallback_score = 0.0

        return max([fallback_score, *tag_hint_scores], default=0.0)

    @app.get("/search-query")
    @login_required
    def smart_search():
        """Busca assistida por IA: manda a consulta pro Gemini/IA local, que
        devolve categorias/tags candidatas, usadas pra filtrar/ranquear o
        catálogo local do usuário (ver _file_relevance)."""
        user_id = current_user_id()
        query = (request.args.get("q") or "").strip()
        all_files = stores.read_all(user_id)

        if not query:
            response = jsonify({"success": True, "query": "", "categories": [], "tags": [], "files": all_files})
            response.headers["Cache-Control"] = "no-store"
            return response

        known_tags = sorted({tag for f in all_files for tag in (f.get("tags") or [])})
        # Categorias não são mais uma lista fixa (ver worker/tasks.py) — são
        # as que o próprio catálogo do usuário já tem, criadas conforme os
        # arquivos foram classificados. Passar as categorias REAIS pra IA de
        # busca evita o falso negativo de tentar bater contra um enum que
        # não tem nada a ver com o que o usuário realmente guardou.
        known_categories = sorted({f["category"] for f in all_files if f.get("category")})

        categories: list[str] = []
        tags: list[str] = []
        analise = None
        if local_ai_habilitada():
            try:
                analise = LocalBuscaAnalyzer().analisar(query, known_categories, known_tags)
            except Exception as exc:  # noqa: BLE001 - IA local é best-effort, cai pro Gemini
                logger.warning("IA local não conseguiu analisar a busca '%s', caindo pro Gemini: %s", query, exc)

        if analise is None:
            try:
                analise = BuscaAnalyzer().analisar(query, known_categories, known_tags)
            except Exception as exc:  # noqa: BLE001 - busca assistida é best-effort
                logger.warning("Não foi possível analisar a busca '%s' via Gemini: %s", query, exc)

        if analise is not None:
            categories = [c.strip().lower() for c in analise.categorias if c.strip()]
            tags = [t.strip().lower() for t in analise.tags if t.strip()]

        scored = [(f, _file_relevance(f, categories, tags, query)) for f in all_files]
        matched = [f for f, score in sorted(scored, key=lambda item: item[1], reverse=True) if score >= FUZZY_THRESHOLD]

        response = jsonify({"success": True, "query": query, "categories": categories, "tags": tags, "files": matched})
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/queue")
    @login_required
    def queue_status():
        """Controle de fila de processamento: quantos itens do catálogo do
        usuário estão em cada status, e quantas mensagens estão esperando no
        broker (Redis) pra serem consumidas por algum worker Celery — os
        dois lados (aplicação e broker) lado a lado, pra deixar visível o
        que é fila de tarefas de verdade (sistema distribuído) e o que é só
        estado de negócio."""
        user_id = current_user_id()
        files = stores.read_all(user_id)
        counts = {"processing": 0, "done": 0, "error": 0}
        for f in files:
            status = f.get("status", "done")
            counts[status] = counts.get(status, 0) + 1

        try:
            pending_in_broker = redis_client.llen("celery")
        except Exception as exc:  # noqa: BLE001 - broker fora do ar não pode derrubar a tela
            logger.warning("Não foi possível consultar o tamanho da fila no Redis: %s", exc)
            pending_in_broker = None

        return jsonify({"success": True, "counts": counts, "pending_in_broker": pending_in_broker})

    @app.get("/processing-log")
    @login_required
    def processing_log_view():
        """Histórico de eventos de processamento (ver api/processing_log.py)
        — o que cada tarefa fez e o motivo real de cada erro, em vez do
        genérico status="error" que o catálogo guarda. Passe `?file_id=` pra
        pegar só a linha do tempo de um arquivo/link específico."""
        user_id = current_user_id()
        entry_id = request.args.get("file_id") or None
        events = processing_log.list_events(user_id, entry_id=entry_id)
        response = jsonify({"success": True, "events": events})
        response.headers["Cache-Control"] = "no-store"
        return response

    return app


app = create_app()
