"""
scripts/local_ai/router.py

Ponto de entrada único da IA local: decide, pela extensão/tipo de conteúdo,
qual "tratativa" especializada (texto, imagem/PDF, vídeo/áudio) usar, e
devolve o mesmo shape de dict que scripts/processar_upload.py já espera.

Recebe `candidate_labels` por parâmetro (em vez de importar
scripts.processar_upload.CATEGORIAS_POSSIVEIS) para não criar import
circular, já que processar_upload.py é quem chama este módulo.
"""

from __future__ import annotations

import os
from typing import List

from scripts.extrator_conteudo import eh_link, preparar_conteudo
from scripts.local_ai.categorizer_local import LocalCategorizer
from scripts.local_ai.video_local import classificar_video_ou_audio, eh_video_ou_audio


def local_ai_habilitada() -> bool:
    return os.environ.get("LOCAL_AI_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def classificar_local(origem: str, candidate_labels: List[str]) -> dict:
    if not eh_link(origem) and eh_video_ou_audio(origem):
        classificacao = classificar_video_ou_audio(origem, candidate_labels)
    else:
        conteudo = preparar_conteudo(origem)
        classificacao = LocalCategorizer().classificar(conteudo, candidate_labels)

    scores_dict = {item.categoria: item.score for item in classificacao.scores}

    return {
        "categoria_principal": classificacao.categoria_principal,
        "tags": classificacao.tags,
        "descricao": classificacao.descricao,
        "scores": scores_dict,
    }
