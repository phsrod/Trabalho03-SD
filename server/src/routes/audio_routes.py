from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Depends, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..models.audio import Audio
from ..services.storage_service import create_audio_directory
from ..services.audio_service import (get_audio_metadata, process_audio, create_metadata_file, create_waveform)


router = APIRouter(prefix="/audios", tags=["Áudios"])


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    processing_type: str = Form("original"),
    db: Session = Depends(get_db)
):
    audio_id = uuid4()

    directory = create_audio_directory(audio_id)

    extension = file.filename.split(".")[-1]

    original_path = directory / f"audio.{extension}"

    with open(original_path, "wb") as audio_file:
        content = await file.read()
        audio_file.write(content)

    processed_path = original_path

    if processing_type != "original":
        processed_extension = extension

        if processing_type == "format":
            processed_extension = "wav"           

        processed_path = directory / f"processed.{processed_extension}"

        process_audio(
            original_path,
            processed_path,
            processing_type
        )

    metadata = get_audio_metadata(original_path)

    audio = Audio(
        id=audio_id,
        original_name=file.filename,
        original_ext=extension,
        mime_type=file.content_type,
        size_bytes=original_path.stat().st_size,
        duration_sec=metadata["duration_sec"],
        sample_rate=metadata["sample_rate"],
        channels=metadata["channels"],
        bitrate=metadata["bitrate"],
        processing_type=processing_type,
        path_original=str(original_path),
        path_processed=str(processed_path)
    )

    create_metadata_file(
        directory,
        audio_id,
        file.filename,
        original_path.stat().st_size,
        metadata,
        processing_type
    )

    waveform_path = directory / "waveform.png"

    create_waveform(
        original_path,
        waveform_path
    )

    db.add(audio)
    db.commit()

    return {
        "id": str(audio_id),
        "filename": file.filename,
        "processing_type": processing_type,
        "path_original": str(original_path),
        "path_processed": str(processed_path),
        "metadata": metadata
    }

@router.get("/")
def list_audios(db: Session = Depends(get_db)):
    audios = db.query(Audio).order_by(Audio.created_at.desc()).all()

    return audios

@router.get("/{audio_id}/original")
def get_original_audio(
    audio_id: str,
    db: Session = Depends(get_db)
):
    audio = db.query(Audio).filter(Audio.id == audio_id).first()

    if audio is None:
        return {"error": "Áudio não encontrado"}

    return FileResponse(
        audio.path_original,
        media_type=audio.mime_type,
        filename=audio.original_name
    )

@router.get("/{audio_id}/processed")
def get_processed_audio(
    audio_id: str,
    db: Session = Depends(get_db)
):
    audio = db.query(Audio).filter(Audio.id == audio_id).first()

    if audio is None:
        return {"error": "Áudio não encontrado"}

    return FileResponse(
        audio.path_processed,
        media_type=audio.mime_type,
        filename=f"processed.{audio.original_ext}"
    )

@router.get("/{audio_id}/waveform")
def get_waveform(
    audio_id: str,
    db: Session = Depends(get_db)
):
    audio = db.query(Audio).filter(Audio.id == audio_id).first()

    if audio is None:
        return {"error": "Áudio não encontrado"}

    waveform_path = str(
        audio.path_original.rsplit("/", 1)[0] + "/waveform.png"
    )

    return FileResponse(
        waveform_path,
        media_type="image/png",
        filename="waveform.png"
    )