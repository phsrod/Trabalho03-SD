"""Rotas HTTP de áudio: upload, histórico, reprodução, metadados e exclusão."""

import logging
from datetime import date, datetime
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import MAX_UPLOAD_SIZE_BYTES, STORAGE_PATH, UPLOAD_CHUNK_SIZE
from ..dependencies import get_db
from ..models.audio import Audio
from ..schemas.audio import (
    DEFAULT_BITRATE,
    DEFAULT_LOUDNESS_TARGET,
    DEFAULT_SPEED_FACTOR,
    DEFAULT_TARGET_FORMAT,
    PROCESSING_TYPE_CATALOG,
    AudioResponse,
    MessageResponse,
    ProcessingType,
    ProcessingTypeInfo,
    StoredFile,
)
from ..services import audio_service, storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audios", tags=["Áudios"])


# --------------------------------------------------------------------------- #
# Funções auxiliares
# --------------------------------------------------------------------------- #
def _get_audio_or_404(db: Session, audio_id: UUID, allow_deleted: bool = False) -> Audio:
    audio = db.get(Audio, audio_id)

    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Áudio não encontrado.")

    if audio.is_deleted and not allow_deleted:
        raise HTTPException(
            status.HTTP_410_GONE,
            "Este áudio está na lixeira. Use POST /trash/{id}/restore para restaurá-lo.",
        )

    return audio


def _serve_file(
    path: str | Path,
    media_type: str,
    filename: str,
    disposition: str = "inline",
) -> FileResponse:
    if not Path(path).is_file():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Arquivo não encontrado no servidor."
        )

    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
    )


def _relative_storage_path(path: Path) -> str:
    """Caminho relativo à raiz do storage (usado no meta.json)."""
    try:
        return Path(path).relative_to(STORAGE_PATH).as_posix()
    except ValueError:
        return Path(path).name


async def _save_upload(upload: UploadFile, destination: Path) -> int:
    """Grava o upload em blocos, respeitando o tamanho máximo permitido."""
    total_bytes = 0

    with open(destination, "wb") as output:
        while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
            total_bytes += len(chunk)

            if total_bytes > MAX_UPLOAD_SIZE_BYTES:
                limit_mb = MAX_UPLOAD_SIZE_BYTES // (1024 * 1024)
                raise HTTPException(
                    status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    f"O arquivo excede o limite de {limit_mb} MB.",
                )

            output.write(chunk)

    if total_bytes == 0:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "O arquivo enviado está vazio."
        )

    return total_bytes


# --------------------------------------------------------------------------- #
# Upload
# --------------------------------------------------------------------------- #
@router.post(
    "/upload",
    response_model=AudioResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Envia um áudio e aplica o processamento escolhido",
)
async def upload_audio(
    file: UploadFile = File(
        ...,
        description=(
            "Arquivo de áudio: wav, mp3, ogg, oga, flac, m4a, aac, opus, wma, "
            "aiff, aif ou webm."
        ),
    ),
    processing_type: ProcessingType = Form(
        ProcessingType.original,
        description="Processamento a aplicar no áudio.",
    ),
    speed_factor: float = Form(
        DEFAULT_SPEED_FACTOR,
        description="Velocidade de reprodução (0.5 a 2.0). Usado quando processing_type=speed.",
    ),
    bitrate: str = Form(
        DEFAULT_BITRATE,
        description="Taxa de bits alvo, no formato <kbps>k (ex.: 64k). Usado quando processing_type=bitrate.",
    ),
    target_format: str = Form(
        DEFAULT_TARGET_FORMAT,
        description="Formato de saída (wav, mp3, ogg, flac, m4a, opus). Usado quando processing_type=format.",
    ),
    loudness_target: float = Form(
        DEFAULT_LOUDNESS_TARGET,
        description="Alvo de loudness em LUFS (-40 a 0). Usado quando processing_type=volume.",
    ),
    db: Session = Depends(get_db),
):
    """Recebe o áudio, gera um UUID, processa com FFmpeg e registra tudo no banco.

    O fluxo é: valida a extensão -> grava ``original/audio.<ext>`` -> lê os
    metadados com o FFprobe -> gera ``processed/audio.<ext>`` -> gera
    ``waveform.png`` -> grava ``meta.json`` -> insere a linha em ``audios``.

    Em qualquer falha a pasta do UUID é apagada, evitando lixo no storage.
    """
    original_name = storage_service.safe_filename(file.filename)
    extension = Path(original_name).suffix.lower().lstrip(".")

    if not extension:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "O arquivo enviado não possui extensão (esperado algo como musica.mp3).",
        )

    if extension not in audio_service.AUDIO_EXTENSIONS:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Formato '.{extension}' não suportado. Aceitos: "
            f"{', '.join(audio_service.AUDIO_EXTENSIONS)}.",
        )

    try:
        applied_params = audio_service.validate_processing_parameters(
            processing_type,
            {
                "speed_factor": speed_factor,
                "bitrate": bitrate,
                "target_format": target_format,
                "loudness_target": loudness_target,
            },
        )
    except audio_service.InvalidParameterError as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    audio_id = uuid4()
    reference_date = date.today()
    created_at = datetime.now()
    directory = storage_service.create_audio_directory(audio_id, reference_date)
    original_path = storage_service.audio_file_path(
        directory, storage_service.ORIGINAL_DIR_NAME, extension
    )

    # 1) Salva o arquivo enviado.
    try:
        size_bytes = await _save_upload(file, original_path)
    except HTTPException:
        storage_service.remove_directory(directory)
        raise

    # 2) Confere se o arquivo tem mesmo uma faixa de áudio válida.
    try:
        original_metadata = await run_in_threadpool(
            audio_service.probe_audio, original_path
        )
    except audio_service.AudioProcessingError as error:
        storage_service.remove_directory(directory)
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error

    mime_type = audio_service.guess_mime_type(extension)

    # 3) Processa, lê os metadados do resultado, gera waveform, meta.json e o registro.
    try:
        processed_ext = audio_service.resolve_processed_extension(
            processing_type, extension, applied_params
        )
        processed_path = storage_service.audio_file_path(
            directory, storage_service.PROCESSED_DIR_NAME, processed_ext
        )

        applied_params = await run_in_threadpool(
            audio_service.process_audio,
            original_path,
            processed_path,
            processing_type,
            applied_params,
            original_metadata["sample_rate"],
        )

        processed_metadata = await run_in_threadpool(
            audio_service.probe_audio, processed_path
        )

        checksum = await run_in_threadpool(storage_service.sha256_file, original_path)

        waveform_path = directory / storage_service.WAVEFORM_FILE_NAME
        waveform_created = True

        try:
            await run_in_threadpool(
                audio_service.create_waveform, processed_path, waveform_path
            )
        except audio_service.AudioProcessingError as error:
            waveform_created = False
            logger.warning(
                "Não foi possível gerar a waveform de %s: %s", audio_id, error
            )

        metadata_document = {
            "id": str(audio_id),
            "original_name": original_name,
            "original_ext": extension,
            "mime_type": mime_type,
            "processing_type": processing_type.value,
            "processing_params": applied_params,
            "created_at": created_at.isoformat(timespec="seconds"),
            "checksum_sha256": checksum,
            "storage": {
                "directory": _relative_storage_path(directory),
                "original": _relative_storage_path(original_path),
                "processed": _relative_storage_path(processed_path),
                "waveform": (
                    storage_service.WAVEFORM_FILE_NAME if waveform_created else None
                ),
                "metadata": storage_service.METADATA_FILE_NAME,
            },
            "original": {
                "file": _relative_storage_path(original_path),
                "size_bytes": size_bytes,
                **original_metadata,
            },
            "processed": {
                "file": _relative_storage_path(processed_path),
                "size_bytes": storage_service.file_size(processed_path),
                **processed_metadata,
            },
        }

        storage_service.write_metadata_file(directory, metadata_document)

        audio = Audio(
            id=audio_id,
            original_name=original_name,
            original_ext=extension,
            mime_type=mime_type,
            size_bytes=size_bytes,
            duration_sec=original_metadata["duration_sec"],
            sample_rate=original_metadata["sample_rate"],
            channels=original_metadata["channels"],
            bitrate=original_metadata["bitrate"],
            processing_type=processing_type.value,
            processing_params=applied_params,
            checksum=checksum,
            created_at=created_at,
            path_original=str(original_path),
            path_processed=str(processed_path),
        )

        db.add(audio)
        db.commit()
        db.refresh(audio)

    except audio_service.AudioProcessingError as error:
        db.rollback()
        storage_service.remove_directory(directory)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Falha no processamento: {error}"
        ) from error
    except Exception as error:
        db.rollback()
        storage_service.remove_directory(directory)
        logger.exception("Erro inesperado ao processar o áudio %s", audio_id)

        if isinstance(error, HTTPException):
            raise

        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Erro inesperado ao processar o áudio no servidor.",
        ) from error

    logger.info(
        "Áudio %s armazenado em %s (processamento: %s)",
        audio_id,
        directory,
        processing_type.value,
    )

    return AudioResponse.from_model(audio)


# --------------------------------------------------------------------------- #
# Catálogo e histórico
# --------------------------------------------------------------------------- #
@router.get(
    "/processing-types",
    response_model=list[ProcessingTypeInfo],
    summary="Lista os processamentos disponíveis",
)
def list_processing_types():
    """Retorna os tipos de processamento aceitos no upload, com rótulo, descrição
    e parâmetros padrão. Use isso para montar o combo box do cliente."""
    return list(PROCESSING_TYPE_CATALOG.values())


@router.get(
    "/",
    response_model=list[AudioResponse],
    summary="Lista o histórico de áudios",
)
def list_audios(
    processing_type: ProcessingType | None = Query(
        None, description="Filtra por tipo de processamento."
    ),
    search: str | None = Query(
        None, description="Filtra pelo nome original do arquivo (busca parcial)."
    ),
    include_deleted: bool = Query(
        False, description="Inclui os áudios que estão na lixeira."
    ),
    skip: int = Query(0, ge=0, description="Quantos registros pular (paginação)."),
    limit: int = Query(100, ge=1, le=500, description="Tamanho máximo da página."),
    db: Session = Depends(get_db),
):
    """Retorna os áudios armazenados, do mais recente para o mais antigo."""
    query = db.query(Audio)

    if not include_deleted:
        query = query.filter(Audio.deleted_at.is_(None))

    if processing_type is not None:
        query = query.filter(Audio.processing_type == processing_type.value)

    if search:
        query = query.filter(Audio.original_name.ilike(f"%{search}%"))

    audios = (
        query.order_by(Audio.created_at.desc(), Audio.original_name)
        .offset(skip)
        .limit(limit)
        .all()
    )

    return [AudioResponse.from_model(audio) for audio in audios]


# --------------------------------------------------------------------------- #
# Detalhe
# --------------------------------------------------------------------------- #
@router.get(
    "/{audio_id}",
    response_model=AudioResponse,
    summary="Consulta os metadados de um áudio",
)
def get_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Retorna a linha da tabela ``audios`` referente ao UUID informado."""
    return AudioResponse.from_model(_get_audio_or_404(db, audio_id))


@router.get(
    "/{audio_id}/files",
    response_model=list[StoredFile],
    summary="Lista os arquivos físicos de um áudio",
)
def list_audio_files(audio_id: UUID, db: Session = Depends(get_db)):
    """Mostra a organização em disco: ``original/``, ``processed/``, ``meta.json`` e
    ``waveform.png``."""
    audio = _get_audio_or_404(db, audio_id)
    return storage_service.list_files(audio.directory)


@router.get(
    "/{audio_id}/meta",
    summary="Retorna o conteúdo do meta.json",
)
def get_audio_metadata_file(audio_id: UUID, db: Session = Depends(get_db)):
    """Lê o ``meta.json`` gravado na pasta do áudio (checksum, parâmetros usados e
    tamanhos dos arquivos)."""
    audio = _get_audio_or_404(db, audio_id)

    try:
        return storage_service.read_metadata_file(audio.directory)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error


# --------------------------------------------------------------------------- #
# Reprodução
# --------------------------------------------------------------------------- #
@router.get(
    "/{audio_id}/original",
    summary="Reproduz o áudio original",
    response_class=FileResponse,
)
def get_original_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Devolve o arquivo original. Suporta requisições HTTP Range, o que permite
    avançar/retroceder a reprodução no player do cliente."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        audio.path_original,
        audio_service.guess_mime_type(audio.original_ext),
        f"original.{audio.original_ext}",
    )


@router.get(
    "/{audio_id}/processed",
    summary="Reproduz o áudio processado",
    response_class=FileResponse,
)
def get_processed_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Devolve o arquivo processado (com o formato resultante do processamento)."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        audio.path_processed,
        audio_service.guess_mime_type(audio.processed_ext),
        f"processed.{audio.processed_ext}",
    )


@router.get(
    "/{audio_id}/waveform",
    summary="Retorna a imagem da forma de onda",
    response_class=FileResponse,
)
def get_waveform(audio_id: UUID, db: Session = Depends(get_db)):
    """Devolve o ``waveform.png`` gerado automaticamente no upload."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        audio.directory / storage_service.WAVEFORM_FILE_NAME,
        "image/png",
        f"waveform-{audio.id}.png",
    )


# --------------------------------------------------------------------------- #
# Download
# --------------------------------------------------------------------------- #
@router.get(
    "/{audio_id}/download/original",
    summary="Baixa o áudio original",
    response_class=FileResponse,
)
def download_original_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Igual a ``/original``, mas força o download com o nome original do arquivo."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        audio.path_original,
        audio_service.guess_mime_type(audio.original_ext),
        audio.original_name,
        disposition="attachment",
    )


@router.get(
    "/{audio_id}/download/processed",
    summary="Baixa o áudio processado",
    response_class=FileResponse,
)
def download_processed_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Igual a ``/processed``, mas força o download do arquivo."""
    audio = _get_audio_or_404(db, audio_id)
    processed_name = f"{Path(audio.original_name).stem}_processed.{audio.processed_ext}"

    return _serve_file(
        audio.path_processed,
        audio_service.guess_mime_type(audio.processed_ext),
        processed_name,
        disposition="attachment",
    )


# --------------------------------------------------------------------------- #
# Exclusão (move para a lixeira)
# --------------------------------------------------------------------------- #
@router.delete(
    "/{audio_id}",
    response_model=MessageResponse,
    summary="Move um áudio para a lixeira",
)
def delete_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Não apaga nada de verdade: move a pasta do UUID para ``trash/`` e marca
    ``deleted_at`` no banco. Use ``POST /trash/{id}/restore`` para desfazer."""
    # Aqui a checagem de "já está na lixeira" é feita pelo próprio
    # _get_audio_or_404, que responde 410 Gone com o caminho de volta.
    audio = _get_audio_or_404(db, audio_id)

    if not audio.directory.is_dir():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "A pasta deste áudio não existe no servidor (nada para mover).",
        )

    storage_service.move_to_trash(audio.directory, audio.id)
    audio.deleted_at = datetime.now()
    db.commit()

    logger.info("Áudio %s movido para a lixeira.", audio_id)

    return MessageResponse(
        message="Áudio movido para a lixeira. Use POST /trash/{id}/restore para restaurar.",
        id=audio.id,
    )
