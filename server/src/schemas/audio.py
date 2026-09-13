"""Contratos (schemas) da API e catálogo de processamentos disponíveis."""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional
from uuid import UUID

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from ..models.audio import Audio


class ProcessingType(str, Enum):
    """Processamentos aceitos pelo endpoint de upload."""

    original = "original"
    volume = "volume"
    mono = "mono"
    speed = "speed"
    bitrate = "bitrate"
    format = "format"


# Valores padrão usados quando o cliente não envia os parâmetros opcionais.
DEFAULT_SPEED_FACTOR = 1.5
DEFAULT_BITRATE = "64k"
DEFAULT_TARGET_FORMAT = "wav"
DEFAULT_LOUDNESS_TARGET = -16.0

SPEED_FACTOR_MIN = 0.5
SPEED_FACTOR_MAX = 2.0
LOUDNESS_TARGET_MIN = -40.0
LOUDNESS_TARGET_MAX = 0.0

TARGET_FORMATS = ("wav", "mp3", "ogg", "flac", "m4a", "opus")


class ProcessingTypeInfo(BaseModel):
    """Descrição de um processamento, usada pelo cliente para montar o menu."""

    key: ProcessingType
    label: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


PROCESSING_TYPE_CATALOG: dict[ProcessingType, ProcessingTypeInfo] = {
    ProcessingType.original: ProcessingTypeInfo(
        key=ProcessingType.original,
        label="Sem processamento",
        description="Mantém o áudio original e grava uma cópia idêntica como arquivo processado.",
        parameters={},
    ),
    ProcessingType.volume: ProcessingTypeInfo(
        key=ProcessingType.volume,
        label="Normalização de volume",
        description="Normaliza o volume usando o filtro loudnorm (padrão EBU R128).",
        parameters={"loudness_target": DEFAULT_LOUDNESS_TARGET},
    ),
    ProcessingType.mono: ProcessingTypeInfo(
        key=ProcessingType.mono,
        label="Conversão para mono",
        description="Converte o áudio para um único canal.",
        parameters={},
    ),
    ProcessingType.speed: ProcessingTypeInfo(
        key=ProcessingType.speed,
        label="Alteração de velocidade",
        description="Altera a velocidade de reprodução sem mudar o tom (filtro atempo).",
        parameters={"speed_factor": DEFAULT_SPEED_FACTOR},
    ),
    ProcessingType.bitrate: ProcessingTypeInfo(
        key=ProcessingType.bitrate,
        label="Redução da taxa de bits",
        description="Recomprime o áudio com uma taxa de bits menor (em formatos com perda).",
        parameters={"bitrate": DEFAULT_BITRATE},
    ),
    ProcessingType.format: ProcessingTypeInfo(
        key=ProcessingType.format,
        label="Conversão de formato",
        description="Converte o áudio para outro formato/container.",
        parameters={"target_format": DEFAULT_TARGET_FORMAT},
    ),
}


class AudioResponse(BaseModel):
    """Metadados de um áudio + URLs prontas para uso pelo cliente."""

    id: UUID

    # Campos da tabela ``audios`` (referentes ao arquivo ORIGINAL enviado pelo cliente).
    original_name: str
    original_ext: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = None
    duration_sec: Optional[float] = None
    sample_rate: Optional[int] = None
    channels: Optional[int] = None
    bitrate: Optional[int] = None
    processing_type: str
    processing_params: Optional[dict[str, Any]] = None
    checksum: Optional[str] = None
    created_at: Optional[datetime] = None
    deleted_at: Optional[datetime] = None
    is_deleted: bool = False
    path_original: str
    path_processed: str

    # Informações do arquivo processado.
    processed_ext: Optional[str] = None
    processed_size_bytes: Optional[int] = None

    # URLs relativas: o cliente deve concatenar com a base_url do servidor.
    original_url: str
    processed_url: str
    waveform_url: str
    metadata_url: str

    @classmethod
    def from_model(cls, audio: "Audio") -> "AudioResponse":
        try:
            processed_size: Optional[int] = Path(audio.path_processed).stat().st_size
        except OSError:
            processed_size = None

        audio_id = audio.id

        return cls(
            id=audio_id,
            original_name=audio.original_name,
            original_ext=audio.original_ext,
            mime_type=audio.mime_type,
            size_bytes=audio.size_bytes,
            duration_sec=audio.duration_sec,
            sample_rate=audio.sample_rate,
            channels=audio.channels,
            bitrate=audio.bitrate,
            processing_type=audio.processing_type,
            processing_params=audio.processing_params,
            checksum=audio.checksum,
            created_at=audio.created_at,
            deleted_at=audio.deleted_at,
            is_deleted=audio.is_deleted,
            path_original=audio.path_original,
            path_processed=audio.path_processed,
            processed_ext=audio.processed_ext or None,
            processed_size_bytes=processed_size,
            original_url=f"/audios/{audio_id}/original",
            processed_url=f"/audios/{audio_id}/processed",
            waveform_url=f"/audios/{audio_id}/waveform",
            metadata_url=f"/audios/{audio_id}/meta",
        )


class StoredFile(BaseModel):
    """Arquivo físico dentro da pasta de um áudio."""

    name: str
    relative_path: str
    size_bytes: int


class TrashItem(BaseModel):
    """Item presente na lixeira."""

    id: UUID
    directory: str
    size_bytes: int
    files: list[str]
    deleted_at: Optional[datetime] = None
    audio: Optional[AudioResponse] = None


class MessageResponse(BaseModel):
    message: str
    id: Optional[UUID] = None


class TrashOperationResponse(BaseModel):
    message: str
    removed_directories: int = 0
    removed_records: int = 0


class HealthResponse(BaseModel):
    status: str
    database: str
    storage_path: str
    trash_path: str
