"""Rotas da lixeira: listar, restaurar, excluir permanentemente e esvaziar.

A exclusão de um áudio é sempre reversível: a pasta do UUID sai de
``storage/<data>/<uuid>`` e vai para ``trash/<uuid>``, e a coluna ``deleted_at`` do
registro é preenchida. Somente as rotas deste arquivo apagam arquivos do disco.
"""

import logging
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..models.audio import Audio
from ..schemas.audio import (
    MessageResponse,
    TrashItem,
    TrashOperationResponse,
)
from ..schemas.serializers import to_audio_response
from ..services import storage_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/trash", tags=["Lixeira"])


def _trash_entries() -> list[tuple[UUID, Path]]:
    """Percorre ``trash/`` e devolve apenas as pastas com nome de UUID."""
    entries: list[tuple[UUID, Path]] = []

    for directory in storage_service.list_trash_entries():
        try:
            audio_id = UUID(directory.name)
        except ValueError:
            logger.warning("Ignorando item inesperado na lixeira: %s", directory)
            continue

        entries.append((audio_id, directory))

    return entries


@router.get("/", response_model=list[TrashItem], summary="Lista os itens da lixeira")
def list_trash(db: Session = Depends(get_db)):
    """Lista as pastas em ``trash/`` junto do registro correspondente no banco."""
    items = []

    for audio_id, directory in _trash_entries():
        audio = db.get(Audio, audio_id)

        items.append(
            TrashItem(
                id=audio_id,
                directory=directory.as_posix(),
                size_bytes=storage_service.directory_size(directory),
                files=[item["relative_path"] for item in storage_service.list_files(directory)],
                deleted_at=audio.deleted_at if audio is not None else None,
                audio=to_audio_response(audio) if audio is not None else None,
            )
        )

    items.sort(key=lambda item: item.deleted_at or datetime.min, reverse=True)

    return items


@router.post(
    "/{audio_id}/restore",
    response_model=MessageResponse,
    summary="Restaura um áudio que está na lixeira",
)
def restore_audio(audio_id: UUID, db: Session = Depends(get_db)):
    """Move a pasta de ``trash/<uuid>`` de volta para ``storage/<data>/<uuid>`` e
    limpa o campo ``deleted_at``."""
    audio = db.get(Audio, audio_id)

    if audio is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "O registro deste áudio não existe mais no banco de dados.",
        )

    if not audio.is_deleted:
        raise HTTPException(status.HTTP_409_CONFLICT, "Este áudio não está na lixeira.")

    reference_date = storage_service.reference_date_from_path(audio.path_original)

    try:
        destination = storage_service.restore_from_trash(audio.id, reference_date)
    except FileNotFoundError as error:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(error)) from error
    except FileExistsError as error:
        raise HTTPException(status.HTTP_409_CONFLICT, str(error)) from error

    audio.deleted_at = None
    db.commit()

    logger.info("Áudio %s restaurado para %s", audio_id, destination)

    return MessageResponse(message=f"Áudio restaurado em {destination.as_posix()}.", id=audio.id)


@router.delete(
    "/{audio_id}",
    response_model=MessageResponse,
    summary="Exclui definitivamente um item da lixeira",
)
def delete_trash_item(audio_id: UUID, db: Session = Depends(get_db)):
    """Apaga a pasta do disco e remove o registro do banco. Não tem volta."""
    directory = storage_service.trash_directory(audio_id)
    audio = db.get(Audio, audio_id)

    if not directory.exists() and audio is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Item não encontrado na lixeira.")

    if directory.exists():
        storage_service.remove_directory(directory)

    if audio is not None:
        db.delete(audio)
        db.commit()

    logger.info("Áudio %s excluído definitivamente.", audio_id)

    return MessageResponse(message="Áudio excluído definitivamente.", id=audio_id)


@router.delete("/", response_model=TrashOperationResponse, summary="Esvazia a lixeira")
def empty_trash(db: Session = Depends(get_db)):
    """Apaga todas as pastas de ``trash/`` e remove do banco os registros excluídos."""
    removed_directories = 0

    for directory in storage_service.list_trash_entries():
        storage_service.remove_directory(directory)
        removed_directories += 1

    deleted_audios = db.query(Audio).filter(Audio.deleted_at.isnot(None)).all()

    for audio in deleted_audios:
        db.delete(audio)

    db.commit()

    logger.info(
        "Lixeira esvaziada: %s pastas e %s registros removidos.",
        removed_directories,
        len(deleted_audios),
    )

    return TrashOperationResponse(
        message="Lixeira esvaziada.",
        removed_directories=removed_directories,
        removed_records=len(deleted_audios),
    )
