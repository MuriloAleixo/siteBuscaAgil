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
OLLAMA_TIMEOUT = float(os.environ.get("OLLAMA_TIMEOUT", "120"))


class OllamaError(RuntimeError):
    """Ollama indisponível, ou respondeu com erro."""


def _generate(model: str, prompt: str, images: list[str] | None = None, json_format: bool = True) -> str:
    payload = {"model": model, "prompt": prompt, "stream": False}
    if json_format:
        payload["format"] = "json"
    if images:
        payload["images"] = images

    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload, timeout=OLLAMA_TIMEOUT)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise OllamaError(f"Falha ao chamar o Ollama ({model}): {exc}") from exc

    return resp.json()["response"]


def gerar_texto(model: str, prompt: str, json_format: bool = True) -> str:
    """Chama o modelo de texto (ex.: LOCAL_AI_TEXT_MODEL) com um prompt puro."""
    return _generate(model, prompt, json_format=json_format)


def gerar_com_imagem(model: str, prompt: str, image_bytes: bytes, json_format: bool = False) -> str:
    """Chama o modelo de visão (ex.: LOCAL_AI_VISION_MODEL) com uma imagem em bytes.

    json_format=False por padrão: modelos de visão pequenos (ex.: moondream)
    não seguem schema JSON com confiança — o uso normal é pedir uma legenda em
    texto livre e classificar essa legenda depois com o modelo de texto.
    """
    image_b64 = base64.b64encode(image_bytes).decode("ascii")
    return _generate(model, prompt, images=[image_b64], json_format=json_format)
