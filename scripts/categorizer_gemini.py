"""
categorizer_gemini.py

Categorização de conteúdo usando a API do Gemini (Google), na nuvem.
Aceita tanto texto puro quanto arquivos nativos (imagem/PDF) — o que vier
de extrator_conteudo.preparar_conteudo().

Usa "structured output" (resposta forçada em JSON) pra já receber
categoria, tags, descrição e scores, sem parsing manual de texto livre.

Setup:
    pip install google-genai --break-system-packages

    1. Crie uma chave grátis em https://aistudio.google.com/apikey
    2. export GEMINI_API_KEY="sua_chave_aqui"
"""

import os
from typing import List

from google import genai
from pydantic import BaseModel, Field


# Flash-Lite é o mais barato/rápido e tem o limite gratuito mais folgado —
# suficiente pra classificação de texto. Troque para "gemini-2.5-flash" se
# quiser mais qualidade em documentos longos/ambíguos ou imagens complexas.
DEFAULT_MODEL = "gemini-2.5-flash-lite"


class _CategoriaScore(BaseModel):
    categoria: str = Field(description="Uma das categorias candidatas, copiada exatamente como foi passada")
    score: float = Field(description="Confiança de 0.0 a 1.0 de que o documento pertence a essa categoria")


class ClassificacaoArquivo(BaseModel):
    categoria_principal: str = Field(description="A categoria candidata com maior aderência ao conteúdo")
    tags: List[str] = Field(description="Subconjunto das categorias candidatas que também se aplicam ao conteúdo")
    descricao: str = Field(description="Resumo objetivo do conteúdo do arquivo, 1 a 2 frases")
    scores: List[_CategoriaScore] = Field(description="Score de 0.0 a 1.0 para CADA categoria candidata")


class GeminiCategorizer:
    def __init__(self, api_key: str = None, model_name: str = DEFAULT_MODEL):
        api_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "Defina a variável de ambiente GEMINI_API_KEY com uma chave gratuita "
                "criada em https://aistudio.google.com/apikey"
            )
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def classificar(self, conteudo: dict, candidate_labels: List[str]) -> ClassificacaoArquivo:
        """
        conteudo: dict retornado por extrator_conteudo.preparar_conteudo()
                  ({"tipo": "texto", ...} ou {"tipo": "arquivo", ...})
        candidate_labels: lista de categorias/temas possíveis do seu negócio
        """
        instrucao = (
            "Analise o conteúdo a seguir e classifique-o. Para 'scores', atribua "
            "uma nota de 0.0 a 1.0 para CADA uma das categorias candidatas listadas, "
            "indicando o quanto o conteúdo se relaciona com aquele tema (um documento "
            "pode se relacionar com mais de um tema ao mesmo tempo). Em 'categoria_principal', "
            "informe a categoria de maior aderência. Em 'tags', liste as categorias "
            "candidatas com score >= 0.5. Em 'descricao', resuma objetivamente do que "
            "se trata o conteúdo.\n\n"
            f"Categorias candidatas: {', '.join(candidate_labels)}"
        )

        if conteudo["tipo"] == "texto":
            texto = conteudo["conteudo"][:12000]  # limite de segurança pro prompt
            contents = f"{instrucao}\n\nConteúdo:\n{texto}"

        elif conteudo["tipo"] == "arquivo":
            arquivo_gemini = self.client.files.upload(file=conteudo["caminho"])
            contents = [instrucao, arquivo_gemini]

        else:
            raise ValueError(f"tipo de conteúdo desconhecido: {conteudo['tipo']}")

        response = self.client.models.generate_content(
            model=self.model_name,
            contents=contents,
            config={
                "response_mime_type": "application/json",
                "response_schema": ClassificacaoArquivo,
            },
        )

        return response.parsed

