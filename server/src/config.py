# Configurações centralizadas do servidor.

import os
from pathlib import Path

SERVER_ROOT = Path(__file__).resolve().parent.parent

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@postgres:5432/audio_db",)

STORAGE_PATH = Path(os.getenv("STORAGE_PATH", str(SERVER_ROOT / "storage")))
TRASH_PATH = Path(os.getenv("TRASH_PATH", str(SERVER_ROOT / "trash")))

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# Limite de tamanho do upload (padrão: 200 MB) e tamanho dos blocos lidos do disco.
MAX_UPLOAD_SIZE_BYTES = int(os.getenv("MAX_UPLOAD_SIZE_BYTES", str(200 * 1024 * 1024)))
UPLOAD_CHUNK_SIZE = 1024 * 1024
