"""
scripts/local_ai/busca_analyzer_local.py

Equivalente local (Ollama, CPU) ao scripts/analisador_busca.py — mesma
assinatura, mesmo shape de retorno (reaproveita a pydantic `AnaliseBusca`
já definida lá).

Modelo e timeout PRÓPRIOS, diferentes de categorizer_local.py/video_local.py
de propósito: busca dispara uma chamada a CADA consulta digitada (bem mais
volume que classificar upload, que é só uma vez por arquivo) — aqui o que
importa é responder rápido, não a mesma precisão pesada usada pra ler um
documento inteiro. `analisador_busca.py` (Gemini) já segue esse princípio
(usa o Flash-Lite, não o Flash "cheio"); isto replica a mesma ideia do lado
local, que antes reaproveitava sem querer o LOCAL_AI_TEXT_MODEL (o mesmo
7b usado pra classificar arquivo/vídeo) com o mesmo timeout de 300s da
classificação — cada busca podia travar a tela por minutos se o Ollama
estivesse ocupado com uma classificação em paralelo.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List, Optional

from scripts.analisador_busca import AnaliseBusca
from scripts.local_ai.ollama_client import gerar_texto

logger = logging.getLogger(__name__)

# Menor que o LOCAL_AI_TEXT_MODEL (7b) usado pra classificar arquivo: a
# tarefa aqui é simples (mapear uma consulta curta pra categorias/tags que
# já existem), não precisa do mesmo modelo usado pra ler um documento
# inteiro — e precisa ser rápido, já que roda a cada busca.
SEARCH_MODEL = os.environ.get("LOCAL_AI_SEARCH_MODEL", "qwen2.5:3b-instruct")

# Bem mais curto que o OLLAMA_TIMEOUT padrão (300s, calibrado pra vídeo) —
# se o Ollama não responder rápido (ocupado com uma classificação, por
# exemplo), é melhor falhar rápido e cair pro Gemini/fuzzy local (ver
# api/app.py::smart_search) do que travar a tela de busca por minutos.
SEARCH_TIMEOUT = float(os.environ.get("LOCAL_AI_SEARCH_TIMEOUT", "10"))


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

        bruto = gerar_texto(SEARCH_MODEL, prompt, timeout=SEARCH_TIMEOUT)
        try:
            return AnaliseBusca.model_validate_json(bruto)
        except (json.JSONDecodeError, ValueError):
            logger.warning("JSON inválido do modelo local na busca, tentando de novo com prompt reforçado")
            bruto = gerar_texto(
                SEARCH_MODEL,
                prompt + "\n\nResponda SOMENTE o JSON, sem nenhum texto antes ou depois.",
                timeout=SEARCH_TIMEOUT,
            )
            return AnaliseBusca.model_validate_json(bruto)
