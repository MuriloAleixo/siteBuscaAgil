"""
scripts/local_ai/busca_analyzer_local.py

Equivalente local (Ollama, CPU) ao scripts/analisador_busca.py — mesma
assinatura, mesmo shape de retorno (reaproveita a pydantic `AnaliseBusca`
já definida lá).
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from scripts.analisador_busca import AnaliseBusca
from scripts.local_ai.ollama_client import gerar_texto

logger = logging.getLogger(__name__)

TEXT_MODEL = os.environ.get("LOCAL_AI_TEXT_MODEL", "qwen2.5:3b-instruct")


def _montar_instrucao(query: str, candidate_categories: List[str], known_tags: Optional[List[str]]) -> str:
    tags_hint = (
        f"\n\nTags já existentes no catálogo (use como referência, mas não se limite a "
        f"elas): {', '.join(known_tags)}"
        if known_tags
        else ""
    )
    schema_exemplo = {"categorias": ["<categoria candidata, se fizer sentido>"], "tags": ["palavra-chave"]}
    return (
        "Um usuário digitou o texto abaixo em um campo de busca de arquivos. Interprete a "
        "intenção da busca e responda APENAS com um JSON válido, exatamente neste formato: "
        f"{json.dumps(schema_exemplo, ensure_ascii=False)}\n\n"
        "Em 'categorias': quais das categorias candidatas abaixo provavelmente descrevem o "
        "que ele procura (pode ser nenhuma, uma ou várias — só inclua se fizer sentido claro, "
        "não force uma correspondência fraca). Copie os nomes exatamente como foram passados.\n\n"
        "Em 'tags': palavras-chave em minúsculas para localizar esse conteúdo nas tags dos "
        "arquivos (inclua a consulta original, termos relevantes que ela contém e "
        "sinônimos/variações plausíveis).\n\n"
        f"Categorias candidatas: {', '.join(candidate_categories)}"
        f"{tags_hint}\n\n"
        f'Busca do usuário: "{query}"'
    )


class LocalBuscaAnalyzer:
    """Equivalente local de BuscaAnalyzer — mesma interface pública."""

    def analisar(
        self,
        query: str,
        candidate_categories: List[str],
        known_tags: Optional[List[str]] = None,
    ) -> AnaliseBusca:
        prompt = _montar_instrucao(query, candidate_categories, known_tags)

        bruto = gerar_texto(TEXT_MODEL, prompt)
        try:
            return AnaliseBusca.model_validate_json(bruto)
        except (json.JSONDecodeError, ValueError):
            logger.warning("JSON inválido do modelo local na busca, tentando de novo com prompt reforçado")
            bruto = gerar_texto(TEXT_MODEL, prompt + "\n\nResponda SOMENTE o JSON, sem nenhum texto antes ou depois.")
            return AnaliseBusca.model_validate_json(bruto)
