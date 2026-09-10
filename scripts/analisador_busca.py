"""
analisador_busca.py

Usa a API do Gemini para interpretar o texto digitado no campo de busca e
sugerir quais categorias/tags do catálogo provavelmente correspondem à
intenção do usuário. O backend (api/app.py::smart_search) usa essa saída
pra filtrar/ranquear o catálogo do usuário por 'category'/'tags' em vez de
só um "contains" no nome do arquivo.

`candidate_categories` não é uma lista fixa de negócio — é o conjunto de
categorias que JÁ existem no catálogo real do usuário (categoria é aberta,
criada dinamicamente na classificação, ver scripts/processar_upload.py),
passado como referência pra não sugerir uma categoria que o usuário nunca
usou.

Uso programático:
    from scripts.analisador_busca import BuscaAnalyzer

    analyzer = BuscaAnalyzer()
    analise = analyzer.analisar("nota fiscal de marco", known_categories, known_tags)
    # analise.categorias -> ["nota fiscal"]
    # analise.tags       -> ["nota fiscal", "marco", "março", "fiscal"]
"""

import os
from typing import List, Optional

from google import genai
from pydantic import BaseModel, Field


# Fica no Flash-Lite (diferente de categorizer_gemini.py, que usa o Flash
# "cheio") de propósito: busca dispara uma chamada a CADA consulta digitada
# (bem mais volume que classificar upload, que é só uma vez por arquivo) —
# aqui o que importa é ficar dentro da cota gratuita e responder rápido; a
# tarefa (mapear uma consulta curta pra categorias/tags já existentes) é
# simples o bastante pro Lite dar conta.
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class AnaliseBusca(BaseModel):
    categorias: List[str] = Field(
        description=(
            "Subconjunto das categorias candidatas que claramente correspondem à intenção "
            "de busca do usuário, copiadas exatamente como foram passadas. Vazio se nenhuma "
            "categoria candidata tiver relação clara com a busca — não force uma categoria."
        )
    )
    tags: List[str] = Field(
        description=(
            "Palavras-chave em minúsculas para buscar nas tags dos arquivos: inclua a "
            "própria consulta, termos relevantes que ela contém e sinônimos/variações "
            "plausíveis (singular/plural, abreviações, termos relacionados)."
        )
    )


class BuscaAnalyzer:
    def __init__(self, api_key: str = None, model_name: str = DEFAULT_MODEL):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Defina a variável de ambiente GEMINI_API_KEY com uma chave gratuita "
                "criada em https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def analisar(
        self,
        query: str,
        candidate_categories: List[str],
        known_tags: Optional[List[str]] = None,
    ) -> AnaliseBusca:
        tags_hint = (
            f"\n\nTags já existentes no catálogo (use como referência, mas não se limite "
            f"a elas): {', '.join(known_tags)}"
            if known_tags
            else ""
        )
        instrucao = (
            "Um usuário digitou o texto abaixo em um campo de busca de arquivos. Interprete "
            "a intenção da busca e responda:\n\n"
            "1. 'categorias': quais das categorias candidatas abaixo provavelmente descrevem "
            "o que ele procura (pode ser nenhuma, uma ou várias — só inclua se fizer sentido "
            "claro, não force uma correspondência fraca).\n\n"
            "2. 'tags': palavras-chave em minúsculas para localizar esse conteúdo nas tags "
            "dos arquivos (inclua a consulta original, termos relevantes que ela contém e "
            "sinônimos/variações plausíveis).\n\n"
            f"Categorias candidatas: {', '.join(candidate_categories)}"
            f"{tags_hint}\n\n"
            f'Busca do usuário: "{query}"'
        )

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=instrucao,
            config={
                "response_mime_type": "application/json",
                "response_schema": AnaliseBusca,
            },
        )

        return response.parsed
