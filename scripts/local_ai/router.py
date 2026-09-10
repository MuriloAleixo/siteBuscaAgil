"""
scripts/local_ai/router.py

Ponto de entrada único da IA local: decide, pela extensão/tipo de conteúdo,
qual "tratativa" especializada (texto, imagem/PDF, vídeo/áudio) usar, e
devolve o mesmo shape de dict que scripts/processar_upload.py já espera.

Recebe `categorias_conhecidas` por parâmetro (em vez de importar algo de
scripts.processar_upload) para não criar import circular, já que
processar_upload.py é quem chama este módulo. Categoria é aberta — essas
são só as categorias já usadas no catálogo do usuário, não uma lista fixa.
"""

from __future__ import annotations

import os
from typing import List

from scripts.extrator_conteudo import eh_link, preparar_conteudo
from scripts.local_ai.categorizer_local import LocalCategorizer
from scripts.local_ai.video_local import classificar_video_ou_audio, eh_video_ou_audio


def local_ai_habilitada() -> bool:
    return os.environ.get("LOCAL_AI_ENABLED", "true").strip().lower() in ("1", "true", "yes", "on")


def classificar_local(origem: str, categorias_conhecidas: List[str]) -> dict:
    if not eh_link(origem) and eh_video_ou_audio(origem):
        classificacao = classificar_video_ou_audio(origem, categorias_conhecidas)
    else:
        conteudo = preparar_conteudo(origem)
        classificacao = LocalCategorizer().classificar(conteudo, categorias_conhecidas)

    return {
        "categoria_principal": classificacao.categoria_principal,
        "confianca": classificacao.confianca,
        "tags": classificacao.tags,
        "descricao": classificacao.descricao,
    }
