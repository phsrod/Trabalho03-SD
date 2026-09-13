"""Rotas HTTP de áudio: upload, histórico, reprodução, metadados e exclusão.

As rotas são finas de propósito: validam o que chega (o FastAPI já aplica as faixas
declaradas no formulário), delegam para os serviços e traduzem as exceções de
domínio em status HTTP. Nenhuma regra de negócio mora aqui.
"""

import logging
from collections.abc import AsyncIterator
from datetime import datetime
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..config import UPLOAD_CHUNK_SIZE
from ..dependencies import get_db
from ..models.audio import Audio
from ..processing import (
    BITRATE_PATTERN,
    DEFAULT_BITRATE,
    DEFAULT_LOUDNESS_TARGET,
    DEFAULT_SPEED_FACTOR,
    DEFAULT_TARGET_FORMAT,
    LOUDNESS_TARGET_MAX,
    LOUDNESS_TARGET_MIN,
    SPEED_FACTOR_MAX,
    SPEED_FACTOR_MIN,
    ProcessingType,
    TargetFormat,
)
from ..schemas.audio import (
    AudioResponse,
    MessageResponse,
    ProcessingTypeInfo,
    StoredFile,
    build_processing_catalog,
)
from ..schemas.serializers import to_audio_response
from ..services import audio_service, storage_service, upload_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/audios", tags=["Áudios"])


# --------------------------------------------------------------------------- #
# Auxiliares
# --------------------------------------------------------------------------- #
async def _iter_upload(upload: UploadFile) -> AsyncIterator[bytes]:
    """Lê o corpo da requisição em blocos (a leitura HTTP fica na camada de rotas)."""
    while chunk := await upload.read(UPLOAD_CHUNK_SIZE):
        yield chunk


def _get_audio_or_404(db: Session, audio_id: UUID) -> Audio:
    """Busca o áudio, respondendo 404 quando não existe e 410 quando está na lixeira."""
    audio = db.get(Audio, audio_id)

    if audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Áudio não encontrado.")

    if audio.is_deleted:
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
    """Devolve um arquivo do disco como resposta HTTP."""
    if not Path(path).is_file():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Arquivo não encontrado no servidor.")

    return FileResponse(
        path,
        media_type=media_type,
        filename=filename,
        content_disposition_type=disposition,
    )


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
    file: Annotated[
        UploadFile,
        File(
            description=(
                "Arquivo de áudio: wav, mp3, ogg, oga, flac, m4a, aac, opus, wma, aiff, aif ou webm."
            )
        ),
    ],
    processing_type: Annotated[
        ProcessingType,
        Form(description="Processamento a aplicar no áudio."),
    ] = ProcessingType.original,
    speed_factor: Annotated[
        float,
        Form(
            ge=SPEED_FACTOR_MIN,
            le=SPEED_FACTOR_MAX,
            description="Velocidade de reprodução. Usado quando processing_type=speed.",
        ),
    ] = DEFAULT_SPEED_FACTOR,
    bitrate: Annotated[
        str,
        Form(
            pattern=BITRATE_PATTERN,
            description="Taxa de bits alvo, ex.: 64k. Usado quando processing_type=bitrate.",
        ),
    ] = DEFAULT_BITRATE,
    target_format: Annotated[
        TargetFormat,
        Form(description="Formato de saída. Usado quando processing_type=format."),
    ] = DEFAULT_TARGET_FORMAT,
    loudness_target: Annotated[
        float,
        Form(
            ge=LOUDNESS_TARGET_MIN,
            le=LOUDNESS_TARGET_MAX,
            description="Alvo de loudness em LUFS. Usado quando processing_type=volume.",
        ),
    ] = DEFAULT_LOUDNESS_TARGET,
    db: Session = Depends(get_db),
):
    """Recebe o áudio, gera um UUID, processa com FFmpeg e registra os metadados.

    Só os parâmetros do processamento escolhido são considerados; os outros são
    ignorados (mas continuam sendo validados quando enviados).
    """
    try:
        audio = await upload_service.receive_and_process(
            db,
            filename=file.filename,
            chunks=_iter_upload(file),
            processing_type=processing_type,
            parameters={
                "speed_factor": speed_factor,
                "bitrate": bitrate,
                "target_format": target_format.value,
                "loudness_target": loudness_target,
            },
        )
    except upload_service.FileTooLargeError as error:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, str(error)) from error
    except (upload_service.UploadError, audio_service.InvalidParameterError) as error:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(error)) from error
    except audio_service.AudioProcessingError as error:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Falha no processamento: {error}"
        ) from error
    except Exception as error:
        logger.exception("Erro inesperado no upload de %s", file.filename)
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Erro inesperado ao processar o áudio no servidor.",
        ) from error

    return to_audio_response(audio)


# --------------------------------------------------------------------------- #
# Catálogo e histórico
# --------------------------------------------------------------------------- #
@router.get(
    "/processing-types",
    response_model=list[ProcessingTypeInfo],
    summary="Lista os processamentos disponíveis",
)
def list_processing_types():
    """Retorna os processamentos aceitos no upload, com rótulo, descrição e
    parâmetros padrão. Use isso para montar o combo box do cliente."""
    return build_processing_catalog()


@router.get(
    "/",
    response_model=list[AudioResponse],
    summary="Lista o histórico de áudios",
)
def list_audios(
    processing_type: Annotated[
        ProcessingType | None,
        Query(description="Filtra por tipo de processamento."),
    ] = None,
    search: Annotated[
        str | None,
        Query(description="Filtra pelo nome original do arquivo (busca parcial)."),
    ] = None,
    include_deleted: Annotated[
        bool,
        Query(description="Inclui os áudios que estão na lixeira."),
    ] = False,
    skip: Annotated[int, Query(ge=0, description="Quantos registros pular (paginação).")] = 0,
    limit: Annotated[int, Query(ge=1, le=500, description="Tamanho máximo da página.")] = 100,
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

    audios = query.order_by(Audio.created_at.desc(), Audio.original_name).offset(skip).limit(limit).all()

    return [to_audio_response(audio) for audio in audios]


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
    return to_audio_response(_get_audio_or_404(db, audio_id))


@router.get(
    "/{audio_id}/files",
    response_model=list[StoredFile],
    summary="Lista os arquivos físicos de um áudio",
)
def list_audio_files(audio_id: UUID, db: Session = Depends(get_db)):
    """Mostra a organização em disco: ``original/``, ``processed/``, ``meta.json`` e
    ``waveform.png``."""
    audio = _get_audio_or_404(db, audio_id)

    return storage_service.list_files(storage_service.audio_directory(audio.path_original))


@router.get(
    "/{audio_id}/meta",
    summary="Retorna o conteúdo do meta.json",
)
def get_audio_metadata_file(audio_id: UUID, db: Session = Depends(get_db)):
    """Lê o ``meta.json`` da pasta do áudio (checksum, parâmetros usados e tamanhos)."""
    audio = _get_audio_or_404(db, audio_id)

    try:
        return storage_service.read_metadata_file(storage_service.audio_directory(audio.path_original))
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
    avançar e retroceder a reprodução no player do cliente."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        storage_service.resolve_path(audio.path_original),
        audio_service.guess_mime_type(audio.original_ext),
        f"original.{audio.original_ext}",
    )


@router.get(
    "/{audio_id}/processed",
    summary="Reproduz o áudio processado",
    response_class=FileResponse,
)
def get_processed_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Devolve o arquivo processado (já no formato resultante do processamento)."""
    audio = _get_audio_or_404(db, audio_id)

    return _serve_file(
        storage_service.resolve_path(audio.path_processed),
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
        storage_service.audio_directory(audio.path_original) / storage_service.WAVEFORM_FILE_NAME,
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
        storage_service.resolve_path(audio.path_original),
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
        storage_service.resolve_path(audio.path_processed),
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
    # Com o áudio já na lixeira, _get_audio_or_404 responde 410 com o caminho de volta.
    audio = _get_audio_or_404(db, audio_id)
    directory = storage_service.audio_directory(audio.path_original)

    if not directory.is_dir():
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "A pasta deste áudio não existe no servidor (nada para mover).",
        )

    storage_service.move_to_trash(directory, audio.id)
    audio.deleted_at = datetime.now()
    db.commit()

    logger.info("Áudio %s movido para a lixeira.", audio_id)

    return MessageResponse(
        message="Áudio movido para a lixeira. Use POST /trash/{id}/restore para restaurar.",
        id=audio.id,
    )
