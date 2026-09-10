"""
scripts/local_ai/categorizer_local.py

Equivalente local (Ollama, CPU) ao scripts/categorizer_gemini.py — mesma
assinatura, mesmo shape de retorno (reaproveita a classe pydantic
`ClassificacaoArquivo` já definida lá, sem duplicar schema).

Modelo de visão local (moondream) é pequeno demais pra seguir um schema JSON
de 4 campos com confiança, então imagem/PDF passam por DUAS etapas:
  1. o modelo de visão gera uma legenda em texto livre da imagem/página;
  2. essa legenda é classificada pelo MESMO prompt usado pra texto puro.

Setup: veja a seção "Configurar IA Local (Ollama)" do README.
"""

from __future__ import annotations

import json
import logging
import os
from typing import List

import pypdf

from scripts.categorizer_gemini import ClassificacaoArquivo
from scripts.local_ai.ollama_client import gerar_com_imagem, gerar_texto

logger = logging.getLogger(__name__)

# qwen2.5:7b-instruct: mais preciso que o 3b pra seguir o schema JSON e
# extrair categoria/tags/descrição corretas — mais lento em CPU, mas ainda
# viável (a classificação já roda em background, no worker). Troque pra
# "qwen2.5:3b-instruct" no .env se a máquina não aguentar o 7b.
TEXT_MODEL = os.environ.get("LOCAL_AI_TEXT_MODEL", "qwen2.5:7b-instruct")
VISION_MODEL = os.environ.get("LOCAL_AI_VISION_MODEL", "moondream")

# Abaixo disso, um PDF é tratado como "sem texto nativo" (provavelmente
# escaneado) e cai pro caminho de renderizar página em imagem.
PDF_MIN_CHARS_TEXTO_NATIVO = 200
PDF_MAX_PAGINAS_IMAGEM = 3


def _montar_instrucao_classificacao(texto: str, categorias_conhecidas: List[str]) -> str:
    schema_exemplo = {
        "categoria_principal": "<categoria que melhor descreve o conteúdo>",
        "confianca": 0.0,
        "tags": ["3 a 6 palavras-chave específicas do conteúdo"],
        "descricao": "resumo objetivo em 1 a 2 frases",
    }
    categorias_hint = (
        f"Categorias já usadas no catálogo deste usuário (reaproveite uma se fizer sentido, "
        f"copiando exatamente; NÃO é uma lista fechada, crie uma nova se nenhuma servir): "
        f"{', '.join(categorias_conhecidas)}"
        if categorias_conhecidas
        else "Nenhuma categoria foi usada ainda por este usuário — crie a primeira, curta e "
        "genérica o suficiente pra se repetir depois (ex.: 'financeiro', 'contrato', 'nota "
        "fiscal' são exemplos de estilo, não uma lista obrigatória)."
    )
    return (
        "Leia com atenção TODO o conteúdo a seguir antes de responder — a precisão da "
        "classificação importa mais do que a velocidade. Baseie-se apenas no que está "
        "escrito no conteúdo, nunca no nome do arquivo isoladamente.\n\n"
        "Responda APENAS com um JSON válido, exatamente neste formato: "
        f"{json.dumps(schema_exemplo, ensure_ascii=False)}\n\n"
        f"{categorias_hint}\n\n"
        "Em 'confianca' (0.0 a 1.0), seja rigoroso: o quanto o conteúdo REALMENTE pertence à "
        "categoria escolhida, não infle por semelhança superficial.\n\n"
        "Em 'tags', NÃO repita a categoria escolhida nem use termos genéricos como "
        "'documento'/'arquivo'/'informação' — extraia de 3 a 6 palavras-chave ou termos "
        "específicos que aparecem no próprio conteúdo (nomes de pessoas/empresas, produtos, "
        "datas, números de documento, termos técnicos relevantes), em minúsculas, pensando em "
        "o que alguém digitaria pra achar justo ESTE arquivo.\n\n"
        "Em 'descricao', cite fatos concretos (quem, o quê, quando, valores) em vez de frases "
        "genéricas.\n\n"
        f"Conteúdo:\n{texto[:12000]}"
    )


def _classificar_texto(texto: str, categorias_conhecidas: List[str]) -> ClassificacaoArquivo:
    prompt = _montar_instrucao_classificacao(texto, categorias_conhecidas)

    bruto = gerar_texto(TEXT_MODEL, prompt)
    try:
        return ClassificacaoArquivo.model_validate_json(bruto)
    except (json.JSONDecodeError, ValueError):
        logger.warning("JSON inválido do modelo local, tentando de novo com prompt reforçado")
        bruto = gerar_texto(TEXT_MODEL, prompt + "\n\nResponda SOMENTE o JSON, sem nenhum texto antes ou depois.")
        return ClassificacaoArquivo.model_validate_json(bruto)


def _legendar_imagem(caminho: str) -> str:
    with open(caminho, "rb") as f:
        image_bytes = f.read()
    prompt = (
        "Descreva objetivamente o que aparece nesta imagem/documento: texto visível, "
        "números, nomes, datas, tabelas, do que se trata. Responda em português, em texto "
        "corrido, sem formatação."
    )
    return gerar_com_imagem(VISION_MODEL, prompt, image_bytes)


def _texto_nativo_pdf(caminho: str) -> str:
    reader = pypdf.PdfReader(caminho)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _legendar_pdf_escaneado(caminho: str) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(caminho)
    legendas = []
    for i in range(min(len(pdf), PDF_MAX_PAGINAS_IMAGEM)):
        bitmap = pdf[i].render(scale=2.0)
        pil_image = bitmap.to_pil()
        buffer_path = f"{caminho}.pagina{i}.jpg"
        pil_image.save(buffer_path, format="JPEG")
        try:
            legendas.append(f"Página {i + 1}: {_legendar_imagem(buffer_path)}")
        finally:
            os.remove(buffer_path)
    return "\n\n".join(legendas)


class LocalCategorizer:
    """Equivalente local de GeminiCategorizer — mesma interface pública."""

    def classificar(self, conteudo: dict, categorias_conhecidas: List[str]) -> ClassificacaoArquivo:
        if conteudo["tipo"] == "texto":
            return _classificar_texto(conteudo["conteudo"], categorias_conhecidas)

        if conteudo["tipo"] == "arquivo":
            mime_type = conteudo.get("mime_type") or ""
            caminho = conteudo["caminho"]

            if mime_type.startswith("image/"):
                legenda = _legendar_imagem(caminho)
                return _classificar_texto(legenda, categorias_conhecidas)

            if mime_type == "application/pdf":
                texto = _texto_nativo_pdf(caminho)
                if len(texto.strip()) < PDF_MIN_CHARS_TEXTO_NATIVO:
                    texto = _legendar_pdf_escaneado(caminho)
                return _classificar_texto(texto, categorias_conhecidas)

            raise ValueError(f"IA local não sabe tratar mime_type: {mime_type}")

        raise ValueError(f"tipo de conteúdo desconhecido: {conteudo['tipo']}")
