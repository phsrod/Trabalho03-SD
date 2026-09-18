# Pipeline de recebimento de um áudio enviado pelo cliente.

import logging
from collections.abc import AsyncIterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ..config import MAX_UPLOAD_SIZE_BYTES
from ..models.audio import Audio
from ..processing import ProcessingType
from . import audio_service, storage_service

logger = logging.getLogger(__name__)


class UploadError(Exception):
    """Erro de validação do arquivo enviado (vira HTTP 400 na rota)."""


class UnsupportedFormatError(UploadError):
    """Extensão de arquivo não suportada."""


class EmptyFileError(UploadError):
    """Arquivo enviado sem nenhum byte."""


class FileTooLargeError(UploadError):
    """Arquivo acima do limite configurado (vira HTTP 413 na rota)."""


@dataclass
class StoredAudio:
    """Tudo que foi produzido no pipeline e precisa virar ``meta.json`` ou linha no banco."""

    audio_id: UUID
    original_name: str
    extension: str
    mime_type: str
    processing_type: ProcessingType
    applied_params: dict
    created_at: datetime
    checksum: str
    directory: Path
    original_path: Path
    processed_path: Path
    size_bytes: int
    original_metadata: dict
    processed_metadata: dict
    original_waveform_created: bool
    processed_waveform_created: bool

    def to_metadata_document(self) -> dict:
        """Conteúdo do ``meta.json`` (checksum, parâmetros usados e metadados dos arquivos)."""
        return {
            "id": str(self.audio_id),
            "original_name": self.original_name,
            "original_ext": self.extension,
            "mime_type": self.mime_type,
            "processing_type": self.processing_type.value,
            "processing_params": self.applied_params,
            "created_at": self.created_at.isoformat(timespec="seconds"),
            "checksum_sha256": self.checksum,
            "storage": {
                "directory": storage_service.storage_relative_path(self.directory),
                "original": storage_service.storage_relative_path(self.original_path),
                "processed": storage_service.storage_relative_path(self.processed_path),
                "waveform_original": (
                    storage_service.WAVEFORM_ORIGINAL_FILE_NAME
                    if self.original_waveform_created
                    else None
                ),
                "waveform_processed": (
                    storage_service.WAVEFORM_PROCESSED_FILE_NAME
                    if self.processed_waveform_created
                    else None
                ),
                "metadata": storage_service.METADATA_FILE_NAME,
            },
            "original": {
                "file": storage_service.storage_relative_path(self.original_path),
                "size_bytes": self.size_bytes,
                **self.original_metadata,
            },
            "processed": {
                "file": storage_service.storage_relative_path(self.processed_path),
                "size_bytes": storage_service.file_size(self.processed_path),
                **self.processed_metadata,
            },
        }

    def to_model(self) -> Audio:
        """Linha da tabela ``audios`` (metadados do arquivo original)."""
        return Audio(
            id=self.audio_id,
            original_name=self.original_name,
            original_ext=self.extension,
            mime_type=self.mime_type,
            size_bytes=self.size_bytes,
            duration_sec=self.original_metadata["duration_sec"],
            sample_rate=self.original_metadata["sample_rate"],
            channels=self.original_metadata["channels"],
            bitrate=self.original_metadata["bitrate"],
            processing_type=self.processing_type.value,
            processing_params=self.applied_params,
            checksum=self.checksum,
            created_at=self.created_at,
            path_original=storage_service.storage_relative_path(self.original_path),
            path_processed=storage_service.storage_relative_path(self.processed_path),
        )


def validate_extension(filename: str | None) -> tuple[str, str]:
    """Valida a extensão do arquivo e devolve ``(nome_seguro, extensão)``."""
    original_name = storage_service.safe_filename(filename)
    extension = Path(original_name).suffix.lower().lstrip(".")

    if not extension:
        raise UnsupportedFormatError("O arquivo enviado não possui extensão (esperado algo como musica.mp3).")

    if extension not in audio_service.AUDIO_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Formato '.{extension}' não suportado. Aceitos: {', '.join(audio_service.AUDIO_EXTENSIONS)}."
        )

    return original_name, extension


async def _write_stream(chunks: AsyncIterable[bytes], destination: Path) -> int:
    """Grava o upload em blocos, respeitando o limite de tamanho, e devolve o total."""
    total_bytes = 0

    with open(destination, "wb") as output:
        async for chunk in chunks:
            total_bytes += len(chunk)

            if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                limit_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
                raise FileTooLargeError(f"O arquivo excede o limite de {limit_mb} MB.")

            output.write(chunk)

    if total_bytes == 0:
        raise EmptyFileError("O arquivo enviado está vazio.")

    return total_bytes


async def _create_waveform(input_path: Path, output_path: Path, audio_id: UUID) -> bool:
    """Gera a waveform sem derrubar o upload se o FFmpeg falhar só nessa etapa."""
    try:
        await run_in_threadpool(audio_service.create_waveform, input_path, output_path)
    except audio_service.AudioProcessingError as error:
        logger.warning(
            "Não foi possível gerar a waveform de %s (%s): %s",
            audio_id,
            output_path.name,
            error,
        )
        return False

    return True


def _cleanup(db: Session, directory: Path) -> None:
    """Desfaz o que já foi feito: descarta a transação e apaga a pasta do áudio."""
    db.rollback()
    storage_service.remove_directory(directory)


async def receive_and_process(
    db: Session,
    *,
    filename: str | None,
    chunks: AsyncIterable[bytes],
    processing_type: ProcessingType | str,
    parameters: dict | None = None,
) -> Audio:
    
    original_name, extension = validate_extension(filename)
    applied_params = audio_service.validate_processing_parameters(processing_type, parameters)
    normalized_type = audio_service.normalize_processing_type(processing_type)

    audio_id = uuid4()
    reference_date = date.today()
    created_at = datetime.now()
    directory = storage_service.create_audio_directory(audio_id, reference_date)
    original_path = storage_service.audio_file_path(directory, storage_service.ORIGINAL_DIR_NAME, extension)

    try:
        size_bytes = await _write_stream(chunks, original_path)

        # Um arquivo que não é áudio (ou está corrompido) é erro do cliente, não do servidor.
        try:
            original_metadata = await run_in_threadpool(audio_service.probe_audio, original_path)
        except audio_service.AudioProcessingError as error:
            raise UnsupportedFormatError(
                f"O arquivo enviado não parece ser um áudio válido: {error}"
            ) from error

        processed_ext = audio_service.resolve_processed_extension(normalized_type, extension, applied_params)
        processed_path = storage_service.audio_file_path(
            directory, storage_service.PROCESSED_DIR_NAME, processed_ext
        )

        applied_params = await run_in_threadpool(
            audio_service.process_audio,
            original_path,
            processed_path,
            normalized_type,
            applied_params,
            original_metadata["sample_rate"],
        )

        processed_metadata = await run_in_threadpool(audio_service.probe_audio, processed_path)
        checksum = await run_in_threadpool(storage_service.sha256_file, original_path)
        # Uma waveform para cada player do cliente: a do arquivo enviado e a do resultado.
        original_waveform_created = await _create_waveform(
            original_path,
            storage_service.waveform_file_path(directory, "original"),
            audio_id,
        )
        processed_waveform_created = await _create_waveform(
            processed_path,
            storage_service.waveform_file_path(directory, "processed"),
            audio_id,
        )

        stored = StoredAudio(
            audio_id=audio_id,
            original_name=original_name,
            extension=extension,
            mime_type=audio_service.guess_mime_type(extension),
            processing_type=normalized_type,
            applied_params=applied_params,
            created_at=created_at,
            checksum=checksum,
            directory=directory,
            original_path=original_path,
            processed_path=processed_path,
            size_bytes=size_bytes,
            original_metadata=original_metadata,
            processed_metadata=processed_metadata,
            original_waveform_created=original_waveform_created,
            processed_waveform_created=processed_waveform_created,
        )

        storage_service.write_metadata_file(directory, stored.to_metadata_document())

        audio = stored.to_model()
        db.add(audio)
        db.commit()
        db.refresh(audio)
    except (UploadError, audio_service.AudioProcessingError, OSError):
        _cleanup(db, directory)
        raise
    except Exception:
        _cleanup(db, directory)
        logger.exception("Erro inesperado ao processar o áudio %s", audio_id)
        raise

    logger.info(
        "Áudio %s armazenado em %s (processamento: %s)",
        audio_id,
        directory,
        normalized_type.value,
    )

    return audio
