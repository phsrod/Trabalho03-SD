# Inspeção e processamento de áudio usando FFmpeg/FFprobe.

import json
import logging
import re
import shutil
import subprocess
from pathlib import Path

from ..processing import (
    BITRATE_REGEX,
    DEFAULT_BITRATE,
    DEFAULT_LOUDNESS_TARGET,
    DEFAULT_SPEED_FACTOR,
    DEFAULT_TARGET_FORMAT,
    LOUDNESS_TARGET_MAX,
    LOUDNESS_TARGET_MIN,
    SPEED_FACTOR_MAX,
    SPEED_FACTOR_MIN,
    TARGET_FORMATS,
    ProcessingType,
    TargetFormat,
)

logger = logging.getLogger(__name__)

# Extensões aceitas no upload.
AUDIO_EXTENSIONS: tuple[str, ...] = (
    "wav",
    "mp3",
    "ogg",
    "oga",
    "flac",
    "m4a",
    "aac",
    "opus",
    "wma",
    "aiff",
    "aif",
    "webm",
)

# Formatos com perda: neles a taxa de bits faz sentido.
LOSSY_EXTENSIONS: frozenset[str] = frozenset({"mp3", "ogg", "oga", "m4a", "aac", "opus", "wma"})

MIME_TYPES: dict[str, str] = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "ogg": "audio/ogg",
    "oga": "audio/ogg",
    "flac": "audio/flac",
    "m4a": "audio/mp4",
    "mp4": "audio/mp4",
    "aac": "audio/aac",
    "opus": "audio/opus",
    "wma": "audio/x-ms-wma",
    "aiff": "audio/aiff",
    "aif": "audio/aiff",
    "webm": "audio/webm",
    "png": "image/png",
    "json": "application/json",
}

DEFAULT_WAVEFORM_SIZE = "1200x400"


class AudioProcessingError(RuntimeError):
    """Falha ao executar FFmpeg/FFprobe ou arquivo sem faixa de áudio."""


class InvalidParameterError(ValueError):
    """Parâmetro de processamento inválido enviado pelo cliente."""


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def guess_mime_type(extension: str) -> str:
    return MIME_TYPES.get(extension.lower().lstrip("."), "application/octet-stream")


def normalize_processing_type(processing_type: ProcessingType | str) -> ProcessingType:
    if isinstance(processing_type, ProcessingType):
        return processing_type

    try:
        return ProcessingType(str(processing_type).lower())
    except ValueError as error:
        raise InvalidParameterError(
            f"Processamento '{processing_type}' não existe. "
            f"Opções: {', '.join(item.value for item in ProcessingType)}."
        ) from error


def _as_float(value: object, default: float) -> float:
    try:
        return float(value) 
    except (TypeError, ValueError):
        return default


def _as_int(value: object, default: int = 0) -> int:
    try:
        return int(float(value))  
    except (TypeError, ValueError):
        return default


def _run(command: list[str]) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as error:
        raise AudioProcessingError(
            f"'{command[0]}' não foi encontrado no servidor. "
            "Instale o FFmpeg (o container já inclui o pacote)."
        ) from error
    except subprocess.CalledProcessError as error:
        stderr = (error.stderr or "").strip()
        last_line = stderr.splitlines()[-1] if stderr else "erro desconhecido"
        logger.error("Falha no comando %s: %s", " ".join(command), stderr)

        raise AudioProcessingError(f"FFmpeg falhou: {last_line}") from error


# --------------------------------------------------------------------------- #
# Parâmetros
# --------------------------------------------------------------------------- #
def validate_processing_parameters(processing_type: ProcessingType | str, parameters: dict | None) -> dict:
    processing_type = normalize_processing_type(processing_type)
    raw = dict(parameters or {})

    if processing_type == ProcessingType.volume:
        target = _as_float(raw.get("loudness_target"), DEFAULT_LOUDNESS_TARGET)

        if not LOUDNESS_TARGET_MIN <= target <= LOUDNESS_TARGET_MAX:
            raise InvalidParameterError(
                f"loudness_target deve estar entre {LOUDNESS_TARGET_MIN} e {LOUDNESS_TARGET_MAX} LUFS."
            )

        return {"loudness_target": round(target, 2)}

    if processing_type == ProcessingType.speed:
        factor = _as_float(raw.get("speed_factor"), DEFAULT_SPEED_FACTOR)

        if not SPEED_FACTOR_MIN <= factor <= SPEED_FACTOR_MAX:
            raise InvalidParameterError(f"speed_factor deve estar entre {SPEED_FACTOR_MIN} e {SPEED_FACTOR_MAX} " "(limite do filtro atempo).")

        return {"speed_factor": round(factor, 3)}

    if processing_type == ProcessingType.bitrate:
        bitrate = str(raw.get("bitrate") or DEFAULT_BITRATE).strip().lower()

        if not re.fullmatch(BITRATE_REGEX, bitrate):
            raise InvalidParameterError("bitrate deve seguir o formato <kbps>k, por exemplo 64k ou 128k.")

        return {"bitrate": bitrate}

    if processing_type == ProcessingType.format:
        target_format = _target_format_value(raw.get("target_format"))

        if target_format not in TARGET_FORMATS:
            raise InvalidParameterError(f"target_format deve ser um destes: {', '.join(TARGET_FORMATS)}.")

        return {"target_format": target_format}

    return {}


def _target_format_value(value: object) -> str:
    if isinstance(value, TargetFormat):
        return value.value

    if value is None:
        return DEFAULT_TARGET_FORMAT.value

    return str(value).strip().lower().lstrip(".")


def resolve_processed_extension(
    processing_type: ProcessingType | str, original_ext: str, parameters: dict
) -> str:
    processing_type = normalize_processing_type(processing_type)
    original_ext = original_ext.lower()

    if processing_type == ProcessingType.format:
        return parameters["target_format"]

    # Reduzir bitrate só faz sentido em formatos com perda; para WAV/FLAC/AIFF
    # convertemos para MP3 para que a taxa de bits tenha efeito real.
    if processing_type == ProcessingType.bitrate and original_ext not in LOSSY_EXTENSIONS:
        return "mp3"

    return original_ext


# --------------------------------------------------------------------------- #
# FFprobe / FFmpeg
# --------------------------------------------------------------------------- #
def probe_audio(file_path: Path) -> dict:
    result = _run(["ffprobe", "-v", "quiet", "-print_format", "json", "-show_format", "-show_streams", str(file_path),])

    try:
        data = json.loads(result.stdout or "{}")
    except json.JSONDecodeError as error:
        raise AudioProcessingError("Não foi possível ler os metadados do áudio.") from error

    stream = next(
        (item for item in data.get("streams", []) if item.get("codec_type") == "audio"),
        None,
    )

    if stream is None:
        raise AudioProcessingError("O arquivo enviado não contém nenhuma faixa de áudio.")

    file_format = data.get("format", {})

    return {
        "duration_sec": round(_as_float(file_format.get("duration") or stream.get("duration"), 0.0), 3),
        "sample_rate": _as_int(stream.get("sample_rate")),
        "channels": _as_int(stream.get("channels")),
        "bitrate": _as_int(file_format.get("bit_rate") or stream.get("bit_rate")),
        "format_name": file_format.get("format_name", ""),
        "codec_name": stream.get("codec_name", ""),
    }


def build_processing_command(
    input_path: Path,
    output_path: Path,
    processing_type: ProcessingType | str,
    parameters: dict,
    source_sample_rate: int | None = None,
) -> tuple[list[str], dict]:
    processing_type = normalize_processing_type(processing_type)
    base = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path)]

    if processing_type == ProcessingType.volume:
        target = parameters["loudness_target"]
        command = base + ["-filter:a", f"loudnorm=I={target}:TP=-1.5:LRA=11"]

        if source_sample_rate:
            command += ["-ar", str(source_sample_rate)]

        applied = {
            "filter": "loudnorm",
            "target_lufs": target,
            "true_peak_db": -1.5,
            "loudness_range": 11,
        }

        return command + [str(output_path)], applied

    if processing_type == ProcessingType.mono:
        return base + ["-ac", "1", str(output_path)], {"channels": 1}

    if processing_type == ProcessingType.speed:
        factor = parameters["speed_factor"]
        applied = {"filter": "atempo", "speed_factor": factor}

        return base + ["-filter:a", f"atempo={factor}", str(output_path)], applied

    if processing_type == ProcessingType.bitrate:
        bitrate = parameters["bitrate"]

        return base + ["-b:a", bitrate, str(output_path)], {"audio_bitrate": bitrate}

    if processing_type == ProcessingType.format:
        return base + [str(output_path)], {"target_format": parameters["target_format"]}

    raise AudioProcessingError(f"Processamento '{processing_type.value}' não implementado.")


def process_audio(
    input_path: Path,
    output_path: Path,
    processing_type: ProcessingType | str,
    parameters: dict,
    source_sample_rate: int | None = None,
) -> dict:
    processing_type = normalize_processing_type(processing_type)
    input_path = Path(input_path)
    output_path = Path(output_path)

    if processing_type == ProcessingType.original:
        shutil.copy2(input_path, output_path)
        return {"processing": "none", "note": "cópia idêntica ao original"}

    command, applied = build_processing_command(
        input_path, output_path, processing_type, parameters, source_sample_rate
    )
    _run(command)

    if not output_path.exists():
        raise AudioProcessingError("O FFmpeg não gerou o arquivo processado.")

    return applied


def create_waveform(
    input_path: Path,
    output_path: Path,
    size: str = DEFAULT_WAVEFORM_SIZE,
) -> Path:
    _run(["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(input_path), "-filter_complex", f"showwavespic=s={size}:colors=#4f8cffff", "-frames:v", "1", str(output_path),])

    return output_path
