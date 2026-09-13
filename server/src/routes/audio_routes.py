from uuid import uuid4

from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session

from ..dependencies import get_db
from ..models.audio import Audio
from ..services.storage_service import create_audio_directory
from ..services.audio_service import get_audio_metadata


router = APIRouter(prefix="/audios", tags=["Áudios"])


@router.post("/upload")
async def upload_audio(
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    audio_id = uuid4()

    directory = create_audio_directory(audio_id)

    extension = file.filename.split(".")[-1]

    file_path = directory / f"audio.{extension}"

    with open(file_path, "wb") as audio_file:
        content = await file.read()
        audio_file.write(content)

    metadata = get_audio_metadata(file_path)

    audio = Audio(
        id=audio_id,
        original_name=file.filename,
        original_ext=extension,
        mime_type=file.content_type,
        size_bytes=file_path.stat().st_size,
        duration_sec=metadata["duration_sec"],
        sample_rate=metadata["sample_rate"],
        channels=metadata["channels"],
        bitrate=metadata["bitrate"],
        processing_type="original",
        path_original=str(file_path),
        path_processed=str(file_path)
    )

    db.add(audio)
    db.commit()

    return {
        "id": str(audio_id),
        "filename": file.filename,
        "path": str(file_path),
        "metadata": metadata
    }