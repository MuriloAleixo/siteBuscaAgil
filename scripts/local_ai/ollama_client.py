"""
scripts/local_ai/ollama_client.py

Cliente HTTP fino para o Ollama (container local, ver docker-compose.yml),
usado por categorizer_local.py, video_local.py e busca_analyzer_local.py.
Não usa a lib `ollama` (evita mais uma dependência) — só `requests`, que já
é dependência do projeto.
"""

from __future__ import annotations

import base64
import os

import requests

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
# 120s bastava pro qwen2.5:3b-instruct, mas o 7b-instruct (padrão desde a
# troca por precisão) pode passar disso em CPU classificando transcrição
# longa de vídeo/áudio — sem isso, um vídeo de poucos minutos já estourava
# o timeout e caía pro Gemini, que não suporta vídeo/áudio (classificação
# falhava nos dois lados). Roda em background no worker, então esperar mais
# não trava nada pro usuário.
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "300"))


class OllamaError(RuntimeError):
    """Ollama indisponível, ou respondeu com erro."""


def _generate(
    model: str,
    prompt: str,
    images: list[str] | None = None,
    json_format: bool = True,
    timeout: float | None = None,
) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False}
    if json_format:
        payload["format"] = "json"
    if images:
        payload["images"] = images

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=timeout if timeout is not None else OLLAMA_TIMEOUT
        )
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Falha ao chamar o Ollama ({model}): {exc}") from exc

    return resp.json()["response"]


def gerar_texto(model: str, prompt: str, json_format: bool = True, timeout: float | None = None) -> str:
    """Chama o modelo de texto (ex.: LOCAL_AI_TEXT_MODEL) com um prompt puro.

    timeout: sobrescreve o OLLAMA_TIMEOUT padrão (300s, calibrado pra
    classificar documento/vídeo) — usado pela busca (ver
    busca_analyzer_local.py), que dispara uma chamada a CADA consulta
    digitada e precisa falhar rápido (cai pro Gemini/fuzzy local, ver
    api/app.py::smart_search) em vez de travar a requisição por minutos se
    o Ollama estiver ocupado com uma classificação em paralelo.
    """
    return _generate(model, prompt, json_format=json_format, timeout=timeout)


def gerar_com_imagem(model: str, prompt: str, image_bytes: bytes, json_format: bool = False) -> str:
    """Chama o modelo de visão (ex.: LOCAL_AI_VISION_MODEL) com uma imagem em bytes.

    json_format=False por padrão: modelos de visão pequenos (ex.: moondream)
    não seguem schema JSON com confiança — o uso normal é pedir uma legenda em
    texto livre e classificar essa legenda depois com o modelo de texto.
    """
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    return _generate(model, prompt, images=[image_b64], json_format=json_format)
