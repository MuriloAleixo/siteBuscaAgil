"""
worker/tasks.py

Tarefas assíncronas do Celery (era core/tasks.py, em Django): classificar
o arquivo/link via IA (local primeiro, Gemini como rede de segurança, ver
scripts/processar_upload.py) e subir o resultado pro Google Drive do
usuário. Roda num processo `worker` separado do `api`, consumindo a fila no
Redis — o upload HTTP não fica esperando a classificação terminar.

Categoria é ABERTA (não uma lista fixa de negócio): a cada classificação,
este módulo lê as categorias que o usuário já tem no catálogo e passa como
referência pro classificador (ver scripts/processar_upload.py) — assim o
vocabulário de categorias cresce organicamente, mas tende a se reaproveitar
em vez de fragmentar ("financeiro" x "finanças" x "financeiro pessoal").
Como reforço extra além do prompt, `_snap_to_known_category` corrige no
código qualquer quase-duplicata que o modelo ainda assim devolver.

Sem Django: onde antes era `DriveProfile.objects.get(user_id=...)`, agora é
`api.stores.read_profile(user_id)` — mesmo JSON por usuário que o `api`
também lê/escreve (ver api/stores.py).
"""

from __future__ import annotations

import logging
import mimetypes
import os
import tempfile
from pathlib import Path

from rapidfuzz import fuzz

from api import google_drive, processing_log, stores
from api.text_match import normalize
from scripts.processar_upload import processar_upload
from worker.celery_app import app as celery_app

logger = logging.getLogger(__name__)

# Acima disso, uma categoria devolvida pelo modelo é considerada "a mesma"
# de uma categoria já existente no catálogo (typo, acento, plural, etc.) —
# reaproveita a grafia já usada em vez de deixar o catálogo acumular
# categorias quase-idênticas. Calibrado testando pares que deveriam colar
# ("juridico"/"jurídico"=87.5, "sistema operacional"/"sistemas
# operacionais"=90.0, "contrato"/"contratos"=94.1) contra pares que NÃO
# deveriam ("sistemas automotivos"/"sistemas operacionais"=63.4) — 85 dá
# margem confortável dos dois lados.
_CATEGORY_SNAP_THRESHOLD = 85.0


def _category_similarity(a: str, b: str) -> float:
    """Comparação PRA JUNTAR categorias — não confundir com
    api.text_match.fuzzy_score, que usa partial_ratio (pensado pra busca:
    "query aparece dentro de um candidate maior", ex. "fatura" bate em
    "fatura de março"). Usado aqui, esse mesmo algoritmo colava categorias
    sem nenhuma relação: "sistema" pontuava 100/100 contra "sistemas
    operacionais" só por ser quase um prefixo exato dela — bug real visto
    em produção (vídeo sobre cinto de segurança e PDF de lista de
    exercícios, ambos virando "sistemas operacionais" sem nenhuma relação
    com o conteúdo). token_sort_ratio compara a string INTEIRA, não
    substring, e não confunde os dois casos."""
    return fuzz.token_sort_ratio(normalize(a), normalize(b))


def sync_catalog_to_drive(service, user_id: str) -> None:
    """Reflete o catálogo local (já atualizado) de volta pro
    uploaded_files.json dentro da pasta do usuário no Drive."""
    profile = stores.read_profile(user_id)
    files = stores.read_all(user_id)
    catalog_file_id = google_drive.upload_catalog(service, profile["folder_id"], files, profile.get("catalog_file_id") or None)
    if catalog_file_id != profile.get("catalog_file_id"):
        stores.write_profile(user_id, catalog_file_id=catalog_file_id)


def _known_categories(user_id: str) -> list[str]:
    files = stores.read_all(user_id)
    return sorted({f["category"] for f in files if f.get("category")})


def _snap_to_known_category(categoria: str | None, categorias_conhecidas: list[str]) -> str | None:
    """Se a categoria devolvida pelo modelo for muito parecida com uma que
    o usuário já usa, troca pela grafia já existente — reforço em código
    pro pedido feito no prompt (ver categorizer_gemini.py/categorizer_local.py),
    que um modelo pode ocasionalmente não seguir à risca."""
    if not categoria or not categorias_conhecidas:
        return categoria
    melhor = max(categorias_conhecidas, key=lambda c: _category_similarity(categoria, c))
    if _category_similarity(categoria, melhor) >= _CATEGORY_SNAP_THRESHOLD:
        return melhor
    return categoria


def _classify_best_effort(
    origem: str, categorias_conhecidas: list[str], user_id: str, entry_id: str, task_id: str | None
) -> dict | None:
    """Classificação é best-effort: formato não suportado, falta de
    GEMINI_API_KEY ou erro de rede não podem impedir o arquivo de ir pro
    Drive — só ficam sem categoria/tags. O resultado (ou o motivo da
    falha) vai pro processing_log pra aparecer na tela de Fila de
    Processamento — sem isso, o único rastro de um erro de classificação
    era `docker compose logs worker`."""
    try:
        resultado = processar_upload(origem, categorias_conhecidas=categorias_conhecidas)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível classificar '%s': %s", origem, exc)
        processing_log.log_event(user_id, entry_id, "classify", "error", str(exc), task_id=task_id)
        return None

    resultado["categoria_principal"] = _snap_to_known_category(
        resultado.get("categoria_principal"), categorias_conhecidas
    )
    processing_log.log_event(
        user_id,
        entry_id,
        "classify",
        "done",
        f"Categoria: {resultado.get('categoria_principal') or 'sem categoria'} "
        f"(confiança {resultado.get('confianca')})",
        task_id=task_id,
    )
    return resultado


def _run_file_upload(user_id: str, saved_path: str, entry_id: str, original_name: str, task_id: str | None) -> None:
    processing_log.log_event(user_id, entry_id, "task", "started", f"Classificando '{original_name}'", task_id=task_id)
    resultado = _classify_best_effort(saved_path, _known_categories(user_id), user_id, entry_id, task_id)

    try:
        service = google_drive.get_drive_service(user_id)
        profile = stores.read_profile(user_id)
        folder_id = profile["folder_id"]
    except (KeyError, google_drive.DriveNotConnectedError) as exc:
        logger.warning("Não foi possível subir '%s' pro Drive do usuário %s: %s", original_name, user_id, exc)
        stores.update_entry(user_id, entry_id, status="error")
        processing_log.log_event(user_id, entry_id, "upload_drive", "error", str(exc), task_id=task_id)
        return

    mimetype = mimetypes.guess_type(original_name)[0]
    try:
        uploaded = google_drive.upload_file(service, folder_id, saved_path, original_name, mimetype)
    except Exception as exc:  # noqa: BLE001 - erro do Drive não pode derrubar o worker
        logger.warning("Falha ao subir '%s' pro Drive: %s", original_name, exc)
        # Mantém o arquivo local (não deleta) pra não perder o dado enviado.
        stores.update_entry(user_id, entry_id, status="error")
        processing_log.log_event(user_id, entry_id, "upload_drive", "error", str(exc), task_id=task_id)
        return

    stores.update_entry(
        user_id,
        entry_id,
        status="done",
        category=(resultado or {}).get("categoria_principal"),
        tags=(resultado or {}).get("tags", []),
        description=(resultado or {}).get("descricao", ""),
        confidence=(resultado or {}).get("confianca"),
        classification_source="ai" if resultado else None,
        url=uploaded["web_view_link"],
        drive_file_id=uploaded["file_id"],
    )
    processing_log.log_event(user_id, entry_id, "task", "done", "Arquivo classificado e enviado ao Drive", task_id=task_id)

    try:
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - o arquivo já subiu; sincronizar o catálogo é best-effort
        logger.warning("Arquivo no Drive, mas falhou sincronizar uploaded_files.json: %s", exc)
        processing_log.log_event(user_id, entry_id, "catalog_sync", "error", str(exc), task_id=task_id)

    try:
        os.remove(saved_path)
    except OSError as exc:
        logger.warning("Não foi possível remover o arquivo temporário local '%s': %s", saved_path, exc)


def _run_link_classification(user_id: str, url: str, entry_id: str, task_id: str | None) -> None:
    """Links não têm arquivo físico pra subir — só a classificação entra no
    catálogo (que ainda assim é sincronizado de volta pro Drive)."""
    processing_log.log_event(user_id, entry_id, "task", "started", f"Classificando link '{url}'", task_id=task_id)
    resultado = _classify_best_effort(url, _known_categories(user_id), user_id, entry_id, task_id)
    if resultado is None:
        stores.update_entry(user_id, entry_id, status="error")
        return

    stores.update_entry(
        user_id,
        entry_id,
        status="done",
        category=resultado.get("categoria_principal"),
        tags=resultado.get("tags", []),
        description=resultado.get("descricao", ""),
        confidence=resultado.get("confianca"),
        classification_source="ai",
    )
    processing_log.log_event(user_id, entry_id, "task", "done", "Link classificado", task_id=task_id)

    try:
        service = google_drive.get_drive_service(user_id)
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Não foi possível sincronizar o catálogo com o Drive: %s", exc)
        processing_log.log_event(user_id, entry_id, "catalog_sync", "error", str(exc), task_id=task_id)


def _run_reclassification(user_id: str, entry_id: str, task_id: str | None) -> None:
    """Reclassifica um item que já está no catálogo (upload original já
    concluído, com ou sem categoria) sem reenviar o arquivo do zero — usado
    pelo botão "Reprocessar" na página de detalhes, útil quando a
    classificação original falhou por instabilidade passageira da IA (local
    e/ou Gemini, ver processing_log). Item de link reclassifica direto pela
    URL; item de arquivo baixa de novo do Drive (não duplica o upload)."""
    entry = stores.get_entry(user_id, entry_id)
    if entry is None:
        logger.warning("Reprocessamento pedido pra entry inexistente: %s/%s", user_id, entry_id)
        return

    processing_log.log_event(user_id, entry_id, "task", "started", f"Reprocessando '{entry['name']}'", task_id=task_id)
    stores.update_entry(user_id, entry_id, status="processing")

    tmp_path: str | None = None
    try:
        if entry.get("type") == "link":
            origem = entry["url"]
        else:
            drive_file_id = entry.get("drive_file_id")
            if not drive_file_id:
                raise ValueError("Item sem arquivo associado no Drive — não é possível baixar pra reprocessar.")
            service = google_drive.get_drive_service(user_id)
            content, _drive_name, _mimetype = google_drive.download_file(service, drive_file_id)
            fd, tmp_path = tempfile.mkstemp(suffix=Path(entry["name"]).suffix)
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            origem = tmp_path
    except Exception as exc:  # noqa: BLE001 - baixar do Drive é best-effort, igual ao resto do worker
        logger.warning("Não foi possível baixar '%s' do Drive pra reprocessar: %s", entry["name"], exc)
        stores.update_entry(user_id, entry_id, status="error")
        processing_log.log_event(user_id, entry_id, "reprocess", "error", str(exc), task_id=task_id)
        return

    resultado = _classify_best_effort(origem, _known_categories(user_id), user_id, entry_id, task_id)

    if tmp_path:
        try:
            os.remove(tmp_path)
        except OSError:
            pass

    if resultado is None:
        stores.update_entry(user_id, entry_id, status="error")
        return

    stores.update_entry(
        user_id,
        entry_id,
        status="done",
        category=resultado.get("categoria_principal"),
        tags=resultado.get("tags", []),
        description=resultado.get("descricao", ""),
        confidence=resultado.get("confianca"),
        classification_source="ai",
    )
    processing_log.log_event(user_id, entry_id, "task", "done", "Reclassificado com sucesso", task_id=task_id)

    try:
        service = google_drive.get_drive_service(user_id)
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Reclassificado, mas falhou sincronizar o catálogo com o Drive: %s", exc)
        processing_log.log_event(user_id, entry_id, "catalog_sync", "error", str(exc), task_id=task_id)


@celery_app.task(bind=True)
def classify_and_catalog_task(self, user_id: str, entry_id: str, saved_path: str, original_name: str) -> None:
    _run_file_upload(user_id, saved_path, entry_id, original_name, task_id=self.request.id)


@celery_app.task(bind=True)
def classify_link_task(self, user_id: str, entry_id: str, url: str) -> None:
    _run_link_classification(user_id, url, entry_id, task_id=self.request.id)


@celery_app.task(bind=True)
def reclassify_task(self, user_id: str, entry_id: str) -> None:
    _run_reclassification(user_id, entry_id, task_id=self.request.id)
