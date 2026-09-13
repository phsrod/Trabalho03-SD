from pathlib import Path
from uuid import UUID
from datetime import date


STORAGE_PATH = Path("/app/storage")


def create_audio_directory(audio_id: UUID):
    today = date.today()

    directory = STORAGE_PATH / str(today) / str(audio_id)
    directory.mkdir(parents=True, exist_ok=True)

    return directory