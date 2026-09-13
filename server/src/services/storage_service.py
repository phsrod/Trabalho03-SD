# Organização dos arquivos em disco: ``storage/``, ``trash/`` e ``meta.json``.

import hashlib
import json
import logging
import shutil
from datetime import date
from pathlib import Path
from uuid import UUID

from ..config import STORAGE_PATH, TRASH_PATH

logger = logging.getLogger(__name__)

ORIGINAL_DIR_NAME = "original"
PROCESSED_DIR_NAME = "processed"
AUDIO_FILE_STEM = "audio"
METADATA_FILE_NAME = "meta.json"
WAVEFORM_FILE_NAME = "waveform.png"

HASH_CHUNK_SIZE = 1024 * 1024


# --------------------------------------------------------------------------- #
# Caminhos
# --------------------------------------------------------------------------- #
def resolve_path(stored_path: str | Path) -> Path:
    path = Path(stored_path)

    return path if path.is_absolute() else STORAGE_PATH / path


def storage_relative_path(path: str | Path) -> str:
    path = Path(path)

    try:
        return path.resolve().relative_to(STORAGE_PATH.resolve()).as_posix()
    except ValueError:
        return path.name


def audio_directory(path_original: str | Path) -> Path:
    return resolve_path(path_original).parent.parent


def ensure_base_directories() -> None:
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    TRASH_PATH.mkdir(parents=True, exist_ok=True)


def safe_filename(filename: str | None) -> str:
    candidate = (filename or "").replace("\\", "/").split("/")[-1].strip()

    if not candidate:
        return "audio"

    return "".join(character for character in candidate if character.isprintable())


def build_audio_directory(audio_id: UUID | str, reference_date: date) -> Path:
    return STORAGE_PATH / reference_date.isoformat() / str(audio_id)


def create_audio_directory(audio_id: UUID | str, reference_date: date | None = None) -> Path:
    reference_date = reference_date or date.today()
    directory = build_audio_directory(audio_id, reference_date)

    (directory / ORIGINAL_DIR_NAME).mkdir(parents=True, exist_ok=True)
    (directory / PROCESSED_DIR_NAME).mkdir(parents=True, exist_ok=True)

    return directory


def audio_file_path(directory: Path, folder: str, extension: str) -> Path:
    extension = extension.lower().lstrip(".")

    return directory / folder / f"{AUDIO_FILE_STEM}.{extension}"


def reference_date_from_path(path_original: str | Path) -> date:
    directory = audio_directory(path_original)

    try:
        return date.fromisoformat(directory.parent.name)
    except ValueError:
        return date.today()


# --------------------------------------------------------------------------- #
# Arquivos e metadados
# --------------------------------------------------------------------------- #
def sha256_file(file_path: Path) -> str:
    digest = hashlib.sha256()

    with open(file_path, "rb") as file:
        while chunk := file.read(HASH_CHUNK_SIZE):
            digest.update(chunk)

    return digest.hexdigest()


def file_size(file_path: str | Path | None) -> int | None:
    if file_path is None:
        return None

    try:
        return Path(file_path).stat().st_size
    except OSError:
        return None


def directory_size(directory: Path) -> int:
    return sum(file_size(path) or 0 for path in Path(directory).rglob("*") if path.is_file())


def list_files(directory: Path) -> list[dict]:
    directory = Path(directory)

    if not directory.is_dir():
        return []

    return [
        {
            "name": path.name,
            "relative_path": path.relative_to(directory).as_posix(),
            "size_bytes": file_size(path) or 0,
        }
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    ]


def write_metadata_file(directory: Path, data: dict) -> Path:
    metadata_path = Path(directory) / METADATA_FILE_NAME

    with open(metadata_path, "w", encoding="utf-8") as metadata_file:
        json.dump(data, metadata_file, indent=4, ensure_ascii=False, default=str)

    return metadata_path


def read_metadata_file(directory: Path) -> dict:
    metadata_path = Path(directory) / METADATA_FILE_NAME

    if not metadata_path.is_file():
        raise FileNotFoundError(f"'{METADATA_FILE_NAME}' não encontrado para este áudio.")

    with open(metadata_path, encoding="utf-8") as metadata_file:
        return json.load(metadata_file)


# --------------------------------------------------------------------------- #
# Lixeira
# --------------------------------------------------------------------------- #
def trash_directory(audio_id: UUID | str) -> Path:
    return TRASH_PATH / str(audio_id)


def move_to_trash(directory: Path, audio_id: UUID | str) -> Path:
    """Move a pasta do áudio para ``trash/<uuid>``."""
    destination = trash_directory(audio_id)

    if destination.exists():
        shutil.rmtree(destination, ignore_errors=True)

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(directory), str(destination))

    return destination


def restore_from_trash(audio_id: UUID | str, reference_date: date) -> Path:
    source = trash_directory(audio_id)

    if not source.is_dir():
        raise FileNotFoundError(f"Áudio {audio_id} não está na lixeira.")

    destination = build_audio_directory(audio_id, reference_date)

    if destination.exists():
        raise FileExistsError(f"A pasta de armazenamento do áudio {audio_id} já existe no servidor.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(destination))

    return destination


def list_trash_entries() -> list[Path]:
    if not TRASH_PATH.is_dir():
        return []

    return sorted(path for path in TRASH_PATH.iterdir() if path.is_dir())


def remove_directory(directory: Path) -> None:
    shutil.rmtree(directory, ignore_errors=True)
