#Contratos (schemas) da API.

from datetime import datetime
from typing import TYPE_CHECKING, Any
from uuid import UUID

from pydantic import BaseModel, Field

from ..processing import PROCESSING_CATALOG, PROCESSING_TYPES, ProcessingType

if TYPE_CHECKING:
    from ..models.audio import Audio


class ProcessingTypeInfo(BaseModel):
    key: ProcessingType
    label: str
    description: str
    parameters: dict[str, Any] = Field(default_factory=dict)


def build_processing_catalog() -> list[ProcessingTypeInfo]:
    return [ProcessingTypeInfo(key=processing_type, **PROCESSING_CATALOG[processing_type]) for processing_type in PROCESSING_TYPES]


class AudioResponse(BaseModel):

    id: UUID
    original_name: str
    original_ext: str
    mime_type: str | None = None
    size_bytes: int | None = None
    duration_sec: float | None = None
    sample_rate: int | None = None
    channels: int | None = None
    bitrate: int | None = None
    processing_type: str
    processing_params: dict[str, Any] | None = None
    checksum: str | None = None
    created_at: datetime | None = None
    deleted_at: datetime | None = None
    is_deleted: bool = False
    path_original: str
    path_processed: str
    processed_ext: str | None = None
    processed_size_bytes: int | None = None
    original_url: str
    processed_url: str
    waveform_url: str
    waveform_original_url: str
    metadata_url: str

    @classmethod
    def from_model(
        cls,
        audio: "Audio",
        processed_size_bytes: int | None = None,
    ) -> "AudioResponse":
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
            processed_size_bytes=processed_size_bytes,
            original_url=f"/audios/{audio_id}/original",
            processed_url=f"/audios/{audio_id}/processed",
            waveform_url=f"/audios/{audio_id}/waveform",
            waveform_original_url=f"/audios/{audio_id}/waveform/original",
            metadata_url=f"/audios/{audio_id}/meta",
        )


class StoredFile(BaseModel):
    name: str
    relative_path: str
    size_bytes: int


class TrashItem(BaseModel):
    id: UUID
    directory: str
    size_bytes: int
    files: list[str]
    deleted_at: datetime | None = None
    audio: AudioResponse | None = None


class MessageResponse(BaseModel):
    message: str
    id: UUID | None = None


class TrashOperationResponse(BaseModel):
    message: str
    removed_directories: int = 0
    removed_records: int = 0


class HealthResponse(BaseModel):
    status: str
    database: str
    storage_path: str
    trash_path: str
