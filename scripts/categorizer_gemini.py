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
# suficiente pra classificação de texto. Troque para "gemini-3.5-flash" se
# quiser mais qualidade em documentos longos/ambíguos ou imagens complexas.
DEFAULT_MODEL = "gemini-3.5-flash-lite"


class _CategoriaScore(BaseModel):
    categoria: str = Field(description="Uma das categorias candidatas, copiada exatamente como foi passada")
    score: float = Field(description="Confiança de 0.0 a 1.0 de que o documento pertence a essa categoria")


class ClassificacaoArquivo(BaseModel):
    categoria_principal: str = Field(description="A categoria candidata com maior aderência ao conteúdo real do arquivo")
    tags: List[str] = Field(
        description=(
            "3 a 6 palavras-chave específicas extraídas do CONTEÚDO do arquivo "
            "(nomes de pessoas/empresas, temas, produtos, datas, números de contrato/nota, "
            "termos técnicos etc.), em minúsculas, sem repetir os nomes das categorias candidatas. "
            "Servem para melhorar a busca por esse arquivo depois."
        )
    )
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
            "Leia com atenção TODO o conteúdo a seguir antes de responder — a precisão da "
            "classificação importa mais do que a velocidade. Baseie-se apenas no que está "
            "escrito no conteúdo, nunca no nome do arquivo isoladamente.\n\n"
            "Para 'scores', atribua uma nota de 0.0 a 1.0 para CADA uma das categorias "
            "candidatas listadas, refletindo o quanto o conteúdo REALMENTE trata daquele "
            "tema (um documento pode se relacionar com mais de um tema ao mesmo tempo; "
            "seja rigoroso, não infle notas por semelhança superficial).\n\n"
            "Em 'categoria_principal', informe a categoria de maior score. Se nenhuma "
            "categoria tiver relação clara com o conteúdo, use 'outros'.\n\n"
            "Em 'tags', NÃO repita os nomes das categorias candidatas — extraia de 3 a 6 "
            "palavras-chave ou termos específicos que aparecem no próprio conteúdo (nomes "
            "de pessoas/empresas, produtos, datas, números de documento, termos técnicos "
            "relevantes), pensando em o que alguém digitaria para encontrar esse arquivo "
            "numa busca depois.\n\n"
            "Em 'descricao', resuma objetivamente do que se trata o conteúdo, citando os "
            "pontos mais relevantes.\n\n"
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

