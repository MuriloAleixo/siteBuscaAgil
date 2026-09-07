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

TEXT_MODEL = os.environ.get("LOCAL_AI_TEXT_MODEL", "qwen2.5:3b-instruct")
VISION_MODEL = os.environ.get("LOCAL_AI_VISION_MODEL", "moondream")

# Abaixo disso, um PDF é tratado como "sem texto nativo" (provavelmente
# escaneado) e cai pro caminho de renderizar página em imagem.
PDF_MIN_CHARS_TEXTO_NATIVO = 200
PDF_MAX_PAGINAS_IMAGEM = 3


def _montar_instrucao_classificacao(texto: str, candidate_labels: List[str]) -> str:
    schema_exemplo = {
        "categoria_principal": "<uma das categorias candidatas>",
        "tags": ["3 a 6 palavras-chave específicas do conteúdo"],
        "descricao": "resumo objetivo em 1 a 2 frases",
        "scores": [{"categoria": "<categoria>", "score": 0.0} for _ in range(1)],
    }
    return (
        "Leia com atenção TODO o conteúdo a seguir antes de responder — a precisão da "
        "classificação importa mais do que a velocidade. Baseie-se apenas no que está "
        "escrito no conteúdo, nunca no nome do arquivo isoladamente.\n\n"
        "Responda APENAS com um JSON válido, exatamente neste formato "
        f"(um item de 'scores' para CADA categoria candidata): {json.dumps(schema_exemplo, ensure_ascii=False)}\n\n"
        "Em 'categoria_principal', informe a categoria de maior score dentre as candidatas. "
        "Se nenhuma categoria tiver relação clara com o conteúdo, use 'outros'.\n\n"
        "Em 'tags', NÃO repita os nomes das categorias candidatas — extraia de 3 a 6 "
        "palavras-chave ou termos específicos que aparecem no próprio conteúdo (nomes de "
        "pessoas/empresas, produtos, datas, números de documento, termos técnicos "
        "relevantes), em minúsculas.\n\n"
        f"Categorias candidatas: {', '.join(candidate_labels)}\n\n"
        f"Conteúdo:\n{texto[:12000]}"
    )


def _classificar_texto(texto: str, candidate_labels: List[str]) -> ClassificacaoArquivo:
    prompt = _montar_instrucao_classificacao(texto, candidate_labels)

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

    def classificar(self, conteudo: dict, candidate_labels: List[str]) -> ClassificacaoArquivo:
        if conteudo["tipo"] == "texto":
            return _classificar_texto(conteudo["conteudo"], candidate_labels)

        if conteudo["tipo"] == "arquivo":
            mime_type = conteudo.get("mime_type") or ""
            caminho = conteudo["caminho"]

            if mime_type.startswith("image/"):
                legenda = _legendar_imagem(caminho)
                return _classificar_texto(legenda, candidate_labels)

            if mime_type == "application/pdf":
                texto = _texto_nativo_pdf(caminho)
                if len(texto.strip()) < PDF_MIN_CHARS_TEXTO_NATIVO:
                    texto = _legendar_pdf_escaneado(caminho)
                return _classificar_texto(texto, candidate_labels)

            raise ValueError(f"IA local não sabe tratar mime_type: {mime_type}")

        raise ValueError(f"tipo de conteúdo desconhecido: {conteudo['tipo']}")
