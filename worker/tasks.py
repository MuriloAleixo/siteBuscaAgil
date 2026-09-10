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

from api import google_drive, stores
from api.text_match import fuzzy_score
from scripts.processar_upload import processar_upload
from worker.celery_app import app as celery_app

logger = logging.getLogger(__name__)

# Acima disso, uma categoria devolvida pelo modelo é considerada "a mesma"
# de uma categoria já existente no catálogo (typo, acento, plural, etc.) —
# reaproveita a grafia já usada em vez de deixar o catálogo acumular
# categorias quase-idênticas. Mais rígido que o limiar de busca de
# propósito: aqui um "quase igual" errado gruda duas categorias diferentes
# pra sempre, então o risco de errar precisa ser bem menor.
_CATEGORY_SNAP_THRESHOLD = 92.0


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
    melhor = max(categorias_conhecidas, key=lambda c: fuzzy_score(categoria, c))
    if fuzzy_score(categoria, melhor) >= _CATEGORY_SNAP_THRESHOLD:
        return melhor
    return categoria


def _classify_best_effort(origem: str, categorias_conhecidas: list[str]) -> dict | None:
    """Classificação é best-effort: formato não suportado, falta de
    GEMINI_API_KEY ou erro de rede não podem impedir o arquivo de ir pro
    Drive — só ficam sem categoria/tags."""
    try:
        resultado = processar_upload(origem, categorias_conhecidas=categorias_conhecidas)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Não foi possível classificar '%s': %s", origem, exc)
        return None

    resultado["categoria_principal"] = _snap_to_known_category(
        resultado.get("categoria_principal"), categorias_conhecidas
    )
    return resultado


def _run_file_upload(user_id: str, saved_path: str, entry_id: str, original_name: str) -> None:
    resultado = _classify_best_effort(saved_path, _known_categories(user_id))

    try:
        service = google_drive.get_drive_service(user_id)
        profile = stores.read_profile(user_id)
        folder_id = profile["folder_id"]
    except (KeyError, google_drive.DriveNotConnectedError) as exc:
        logger.warning("Não foi possível subir '%s' pro Drive do usuário %s: %s", original_name, user_id, exc)
        stores.update_entry(user_id, entry_id, status="error")
        return

    mimetype = mimetypes.guess_type(original_name)[0]
    try:
        uploaded = google_drive.upload_file(service, folder_id, saved_path, original_name, mimetype)
    except Exception as exc:  # noqa: BLE001 - erro do Drive não pode derrubar o worker
        logger.warning("Falha ao subir '%s' pro Drive: %s", original_name, exc)
        # Mantém o arquivo local (não deleta) pra não perder o dado enviado.
        stores.update_entry(user_id, entry_id, status="error")
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

    try:
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - o arquivo já subiu; sincronizar o catálogo é best-effort
        logger.warning("Arquivo no Drive, mas falhou sincronizar uploaded_files.json: %s", exc)

    try:
        os.remove(saved_path)
    except OSError as exc:
        logger.warning("Não foi possível remover o arquivo temporário local '%s': %s", saved_path, exc)


def _run_link_classification(user_id: str, url: str, entry_id: str) -> None:
    """Links não têm arquivo físico pra subir — só a classificação entra no
    catálogo (que ainda assim é sincronizado de volta pro Drive)."""
    resultado = _classify_best_effort(url, _known_categories(user_id))
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

    try:
        service = google_drive.get_drive_service(user_id)
        sync_catalog_to_drive(service, user_id)
    except Exception as exc:  # noqa: BLE001 - best-effort
        logger.warning("Não foi possível sincronizar o catálogo com o Drive: %s", exc)


@celery_app.task(bind=True)
def classify_and_catalog_task(self, user_id: str, entry_id: str, saved_path: str, original_name: str) -> None:
    _run_file_upload(user_id, saved_path, entry_id, original_name)


@celery_app.task(bind=True)
def classify_link_task(self, user_id: str, entry_id: str, url: str) -> None:
    _run_link_classification(user_id, url, entry_id)
