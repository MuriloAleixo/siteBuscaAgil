"""
scripts/local_ai/video_local.py

Vídeo e áudio não são suportados em NENHUM lugar do projeto hoje
(scripts/extrator_conteudo.py levanta "Formato não suportado" pra .mp4/.mp3
etc.) — esta é uma capacidade nova, só disponível via IA local.

Vídeo: extrai 3 frames representativos com ffmpeg (binário de sistema, ver
README) e legenda cada um com o modelo de visão; a trilha de áudio é
transcrita com faster-whisper. Áudio puro: só a transcrição. O texto
resultante (transcrição + legendas das cenas) é classificado reaproveitando
o mesmo classificador de texto usado pra documentos.

Extensões cobertas = mesmas já usadas como categoria de UI em
core/views.py (EXTENSION_TYPE_MAP).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

from scripts.categorizer_gemini import ClassificacaoArquivo
from scripts.local_ai.categorizer_local import _classificar_texto, _legendar_imagem

logger = logging.getLogger(__name__)

WHISPER_MODEL_SIZE = os.environ.get("LOCAL_AI_WHISPER_MODEL", "tiny")

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".wmv"}
AUDIO_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}

NUM_FRAMES = 3


def eh_video_ou_audio(caminho: str) -> bool:
    ext = Path(caminho).suffix.lower()
    return ext in VIDEO_EXTENSIONS or ext in AUDIO_EXTENSIONS


def _duracao_segundos(caminho: str) -> float | None:
    try:
        saida = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", caminho],
            capture_output=True, text=True, check=True, timeout=30,
        )
        return float(saida.stdout.strip())
    except (subprocess.CalledProcessError, ValueError, FileNotFoundError, subprocess.TimeoutExpired):
        return None


def _extrair_frames(caminho: str, destino_dir: str) -> List[str]:
    duracao = _duracao_segundos(caminho)
    if duracao and duracao > 1:
        timestamps = [duracao * fracao for fracao in (0.25, 0.5, 0.75)][:NUM_FRAMES]
    else:
        timestamps = [0.0]

    caminhos_frames = []
    for i, ts in enumerate(timestamps):
        destino = os.path.join(destino_dir, f"frame_{i}.jpg")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-ss", str(ts), "-i", caminho, "-frames:v", "1", "-q:v", "2", destino],
                capture_output=True, check=True, timeout=60,
            )
            if os.path.exists(destino):
                caminhos_frames.append(destino)
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as exc:
            logger.warning("Falha ao extrair frame de '%s' em %ss: %s", caminho, ts, exc)

    return caminhos_frames


def _transcrever_audio(caminho: str) -> str:
    from faster_whisper import WhisperModel

    modelo = WhisperModel(WHISPER_MODEL_SIZE, device="cpu", compute_type="int8")
    segmentos, _info = modelo.transcribe(caminho, language="pt")
    return " ".join(s.text.strip() for s in segmentos).strip()


def classificar_video_ou_audio(caminho: str, candidate_labels: List[str]) -> ClassificacaoArquivo:
    ext = Path(caminho).suffix.lower()

    try:
        transcricao = _transcrever_audio(caminho)
    except Exception as exc:  # noqa: BLE001 - transcrição é best-effort dentro do best-effort local
        logger.warning("Falha ao transcrever áudio de '%s': %s", caminho, exc)
        transcricao = ""

    legendas_cenas = ""
    if ext in VIDEO_EXTENSIONS:
        with tempfile.TemporaryDirectory() as tmp_dir:
            frames = _extrair_frames(caminho, tmp_dir)
            descricoes = []
            for i, frame in enumerate(frames):
                try:
                    descricoes.append(f"Cena {i + 1}: {_legendar_imagem(frame)}")
                except Exception as exc:  # noqa: BLE001
                    logger.warning("Falha ao legendar frame de '%s': %s", caminho, exc)
            legendas_cenas = "\n".join(descricoes)

    texto = "\n\n".join(
        parte for parte in (
            f"Transcrição do áudio: {transcricao}" if transcricao else "",
            legendas_cenas,
        ) if parte
    )

    if not texto.strip():
        raise ValueError(f"Não foi possível extrair conteúdo de '{caminho}' (sem áudio nem frames)")

    return _classificar_texto(texto, candidate_labels)
