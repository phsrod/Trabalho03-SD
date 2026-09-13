"""Regras de domínio dos processamentos de áudio.

Módulo propositalmente **sem dependências** de FastAPI, SQLAlchemy ou do sistema
de arquivos: é importado pelos serviços, pelos schemas da API e pelas rotas, o que
evita que a camada de serviço dependa dos contratos da API (e vice-versa) e mantém
os limites de validação em um único lugar.
"""

import re
from enum import StrEnum
from typing import Any


class ProcessingType(StrEnum):
    """Processamentos aceitos pelo upload."""

    original = "original"
    volume = "volume"
    mono = "mono"
    speed = "speed"
    bitrate = "bitrate"
    format = "format"


class TargetFormat(StrEnum):
    """Formatos de saída aceitos no processamento ``format``."""

    wav = "wav"
    mp3 = "mp3"
    ogg = "ogg"
    flac = "flac"
    m4a = "m4a"
    opus = "opus"


# Parâmetros padrão e limites (usados tanto pela API quanto pelos serviços).
DEFAULT_SPEED_FACTOR = 1.5
SPEED_FACTOR_MIN = 0.5
SPEED_FACTOR_MAX = 2.0

DEFAULT_BITRATE = "64k"
BITRATE_PATTERN = r"^\d{2,4}k$"
BITRATE_REGEX = re.compile(BITRATE_PATTERN)

DEFAULT_LOUDNESS_TARGET = -16.0
LOUDNESS_TARGET_MIN = -40.0
LOUDNESS_TARGET_MAX = 0.0

DEFAULT_TARGET_FORMAT = TargetFormat.wav

PROCESSING_TYPES: tuple[ProcessingType, ...] = (
    ProcessingType.original,
    ProcessingType.volume,
    ProcessingType.mono,
    ProcessingType.speed,
    ProcessingType.bitrate,
    ProcessingType.format,
)

TARGET_FORMATS: tuple[str, ...] = tuple(formato.value for formato in TargetFormat)

# Rótulo, descrição e parâmetros aceitos por cada processamento.
# É a fonte de verdade do endpoint GET /audios/processing-types.
PROCESSING_CATALOG: dict[ProcessingType, dict[str, Any]] = {
    ProcessingType.original: {
        "label": "Sem processamento",
        "description": ("Mantém o áudio original e grava uma cópia idêntica como arquivo processado."),
        "parameters": {},
    },
    ProcessingType.volume: {
        "label": "Normalização de volume",
        "description": "Normaliza o volume usando o filtro loudnorm (padrão EBU R128).",
        "parameters": {"loudness_target": DEFAULT_LOUDNESS_TARGET},
    },
    ProcessingType.mono: {
        "label": "Conversão para mono",
        "description": "Converte o áudio para um único canal.",
        "parameters": {},
    },
    ProcessingType.speed: {
        "label": "Alteração de velocidade",
        "description": "Altera a velocidade de reprodução sem mudar o tom (filtro atempo).",
        "parameters": {"speed_factor": DEFAULT_SPEED_FACTOR},
    },
    ProcessingType.bitrate: {
        "label": "Redução da taxa de bits",
        "description": "Recomprime o áudio com uma taxa de bits menor (em formatos com perda).",
        "parameters": {"bitrate": DEFAULT_BITRATE},
    },
    ProcessingType.format: {
        "label": "Conversão de formato",
        "description": "Converte o áudio para outro formato/container.",
        "parameters": {"target_format": DEFAULT_TARGET_FORMAT.value},
    },
}
