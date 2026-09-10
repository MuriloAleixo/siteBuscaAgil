"""
api/text_match.py

Critério único de correspondência de texto usado pela busca — tanto pelo
filtro final no backend (api/app.py::_file_relevance) quanto (via a
mesma lógica portada em JS) pelo fallback local do frontend
(static/js/catalog-client.js). Antes disso, cada lado tinha um critério
diferente (ver histórico de `_file_matches` e `searchFiles`), o que fazia a
busca "sumir" um arquivo dependendo de qual caminho respondia.

Duas responsabilidades:
  1. normalize(): remove acento/caixa, pra "março"/"marco"/"MARÇO" comparem
     iguais.
  2. fuzzy_score(): tolera erro de digitação (rapidfuzz), no lugar do antigo
     `in` (substring exata) que não perdoava nada.
"""

from __future__ import annotations

import unicodedata

from rapidfuzz import fuzz

# Abaixo disso, uma correspondência aproximada não conta como match — evita
# falso positivo (ex.: "nota" batendo forte demais em "conta" por acaso).
# Calibrado testando com buscas com erro de digitação/acento contra nomes e
# descrições reais do formato do catálogo; ajustável se gerar ruído.
FUZZY_THRESHOLD = 80.0

# Usado só pelo tier "solto" da busca (fuzzy sobre nome+descrição+categoria+
# tags concatenados, quando nada mais bateu) — mais rígido que o
# FUZZY_THRESHOLD geral porque esse tier não tem nenhuma âncora (categoria/
# tag específica): sem um piso mais alto aqui, uma query curta batia raso em
# quase qualquer arquivo e a busca virava ruído (falso positivo).
FALLBACK_FUZZY_THRESHOLD = 85.0


def normalize(text: str | None) -> str:
    decomposed = unicodedata.normalize("NFKD", text or "")
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return without_accents.lower().strip()


def fuzzy_score(query: str | None, candidate: str | None) -> float:
    """0-100: o quanto `query` aparece (mesmo com erro de digitação) dentro
    de `candidate`. Usa partial_ratio pra não penalizar candidate ser mais
    longo que a query (ex.: query="fatura", candidate="fatura de março")."""
    query_norm = normalize(query)
    candidate_norm = normalize(candidate)
    if not query_norm or not candidate_norm:
        return 0.0
    return fuzz.partial_ratio(query_norm, candidate_norm)
