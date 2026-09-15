"""
categorizer_gemini.py

Categorização de conteúdo usando a API do Gemini (Google), na nuvem.
Aceita tanto texto puro quanto arquivos nativos (imagem/PDF) — o que vier
de extrator_conteudo.preparar_conteudo().

Usa "structured output" (resposta forçada em JSON) pra já receber
categoria, tags, descrição e confiança, sem parsing manual de texto livre.

Categoria é ABERTA, não uma lista fixa: o modelo cria a categoria que melhor
descreve o conteúdo, reaproveitando uma categoria já usada no catálogo do
usuário quando fizer sentido (evita "financeiro" e "finanças" coexistindo
como categorias diferentes por acaso) — ver `categorias_conhecidas`.

Setup:
    pip install google-genai --break-system-packages

    1. Crie uma chave grátis em https://aistudio.google.com/apikey
    2. export GEMINI_API_KEY="sua_chave_aqui"
"""

import logging
import os
import time
from typing import List

from google import genai
from google.genai import errors as genai_errors
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# Backoff entre tentativas quando o Gemini responde 5xx (sobrecarga
# momentânea do lado deles, não erro da nossa chamada) — 2 tentativas extras
# costuma bastar pra um pico passageiro passar, sem prender o worker por
# muito tempo numa tarefa que já é best-effort.
_MAX_TENTATIVAS = 3
_BACKOFF_SEGUNDOS = (3, 8)


# "gemini-3.5-flash" (sem "-lite"): mais preciso que o Flash-Lite pra
# extrair categoria/tags/descrição corretas, e ainda cabe na cota gratuita
# do Gemini (rate limit menor que o Lite, mas sem custo). Troque pra
# "gemini-3.5-flash-lite" se a cota gratuita for um problema real de volume.
DEFAULT_MODEL = "gemini-3.5-flash"


class ClassificacaoArquivo(BaseModel):
    categoria_principal: str = Field(
        description=(
            "A categoria/tema que melhor descreve o CONTEÚDO real do arquivo. Reaproveite uma "
            "das 'categorias já usadas' se ela descrever bem o conteúdo (copie exatamente, "
            "mesma grafia/acentuação); só crie uma categoria nova se nenhuma existente servir. "
            "Categoria nova: 1 a 3 palavras, minúsculas, genérica o suficiente pra se repetir em "
            "outros arquivos parecidos (ex.: 'contrato de locação', não 'contrato do joão "
            "silva de março')."
        )
    )
    confianca: float = Field(
        description=(
            "0.0 a 1.0: o quanto o conteúdo REALMENTE pertence à categoria escolhida. Seja "
            "rigoroso — não infle a nota por semelhança superficial. Abaixo de 0.55 o usuário "
            "vê um aviso pra revisar a classificação manualmente."
        )
    )
    tags: List[str] = Field(
        description=(
            "3 a 6 palavras-chave ESPECÍFICAS extraídas do CONTEÚDO do arquivo (nomes de "
            "pessoas/empresas, temas, produtos, datas, números de contrato/nota, termos "
            "técnicos etc.), em minúsculas. NUNCA repita a categoria escolhida nem termos "
            "genéricos como 'documento', 'arquivo', 'informação', 'dados' — servem pra "
            "melhorar a busca por esse arquivo depois, então precisam ser termos que alguém "
            "digitaria pra achar justo ESTE arquivo, não qualquer outro da mesma categoria."
        )
    )
    descricao: str = Field(
        description=(
            "Resumo objetivo e concreto do conteúdo, 1 a 2 frases — cite fatos específicos "
            "(quem, o quê, quando, valores) em vez de frases genéricas como 'documento sobre "
            "assunto X'. Deve ajudar alguém a reconhecer o arquivo certo numa lista de busca."
        )
    )


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

    def classificar(self, conteudo: dict, categorias_conhecidas: List[str]) -> ClassificacaoArquivo:
        """
        conteudo: dict retornado por extrator_conteudo.preparar_conteudo()
                  ({"tipo": "texto", ...} ou {"tipo": "arquivo", ...})
        categorias_conhecidas: categorias que já existem no catálogo do
                  usuário (não é uma lista fechada — só uma referência pra
                  reaproveitar nomenclatura em vez de fragmentar categorias
                  parecidas). Pode vir vazia (primeiro arquivo do usuário).
        """
        categorias_hint = (
            f"Categorias já usadas no catálogo deste usuário (reaproveite uma se fizer sentido, "
            f"copiando exatamente; NÃO é uma lista fechada, crie uma nova se nenhuma servir): "
            f"{', '.join(categorias_conhecidas)}"
            if categorias_conhecidas
            else "Nenhuma categoria foi usada ainda por este usuário — crie a primeira, "
            "curta e genérica o suficiente pra se repetir depois (ex.: 'financeiro', "
            "'contrato', 'nota fiscal', 'relatório técnico', 'marketing' são exemplos de "
            "estilo, não uma lista obrigatória)."
        )

        instrucao = (
            "Leia com atenção TODO o conteúdo a seguir antes de responder — a precisão da "
            "classificação importa mais do que a velocidade. Baseie-se apenas no que está "
            "escrito no conteúdo, nunca no nome do arquivo isoladamente.\n\n"
            f"{categorias_hint}\n\n"
            "Em 'tags', pense em o que alguém digitaria pra encontrar ESTE arquivo específico "
            "numa busca depois — não repita a categoria nem use termos vagos.\n\n"
            "Em 'descricao', resuma objetivamente do que se trata o conteúdo, citando os "
            "pontos mais relevantes (fatos concretos, não generalidades)."
        )

        if conteudo["tipo"] == "texto":
            texto = conteudo["conteudo"][:12000]  # limite de segurança pro prompt
            contents = f"{instrucao}\n\nConteúdo:\n{texto}"

        elif conteudo["tipo"] == "arquivo":
            arquivo_gemini = self.client.files.upload(file=conteudo["caminho"])
            contents = [instrucao, arquivo_gemini]

        else:
            raise ValueError(f"tipo de conteúdo desconhecido: {conteudo['tipo']}")

        for tentativa in range(1, _MAX_TENTATIVAS + 1):
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=contents,
                    config={
                        "response_mime_type": "application/json",
                        "response_schema": ClassificacaoArquivo,
                    },
                )
                return response.parsed
            except genai_errors.ServerError as exc:
                # 5xx = sobrecarga/instabilidade momentânea do lado do
                # Gemini, não um erro da nossa chamada (ex.: 503 "high
                # demand") — vale tentar de novo. 4xx (ClientError, ex.:
                # chave inválida, request malformado) não é retentado: só
                # gastaria tempo repetindo um erro que não vai se resolver
                # sozinho.
                if tentativa == _MAX_TENTATIVAS:
                    raise
                espera = _BACKOFF_SEGUNDOS[min(tentativa - 1, len(_BACKOFF_SEGUNDOS) - 1)]
                logger.warning(
                    "Gemini respondeu erro de servidor (tentativa %d/%d), tentando de novo em %ds: %s",
                    tentativa, _MAX_TENTATIVAS, espera, exc,
                )
                time.sleep(espera)
