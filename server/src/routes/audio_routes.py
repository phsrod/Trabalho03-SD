from uuid import uuid4

from fastapi import APIRouter, UploadFile, File

from ..services.storage_service import create_audio_directory


router = APIRouter(prefix="/audios", tags=["Áudios"])


@router.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    audio_id = uuid4()

    directory = create_audio_directory(audio_id)

    extension = file.filename.split(".")[-1]

    file_path = directory / f"audio.{extension}"

    with open(file_path, "wb") as audio_file:
        content = await file.read()
        audio_file.write(content)

    return {
        "id": str(audio_id),
        "filename": file.filename,
        "path": str(file_path)
    }