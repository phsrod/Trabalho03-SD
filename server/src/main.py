"""Servidor FastAPI do sistema de processamento de áudio.

O servidor é a camada intermediária: recebe os áudios enviados pelo cliente
PySide6, processa com FFmpeg, guarda os arquivos organizados por data e UUID e
registra os metadados no PostgreSQL.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from sqlalchemy import text

from .config import STORAGE_PATH, TRASH_PATH
from .database import engine, init_db
from .routes.audio_routes import router as audio_router
from .routes.trash_routes import router as trash_router
from .schemas.audio import HealthResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

DESCRIPTION = """
Servidor do trabalho de Sistemas Distribuídos: recebe arquivos de áudio, aplica
processamentos com **FFmpeg**, armazena os arquivos organizados por data e UUID e
registra os metadados no **PostgreSQL**.

### Processamentos disponíveis (campo `processing_type` do upload)

| Valor | O que faz | Parâmetro extra |
|---|---|---|
| `original` | Não altera o áudio (grava uma cópia idêntica) | — |
| `volume` | Normalização de volume (loudnorm / EBU R128) | `loudness_target` (LUFS) |
| `mono` | Converte para 1 canal | — |
| `speed` | Altera a velocidade sem mudar o tom (atempo) | `speed_factor` (0.5–2.0) |
| `bitrate` | Reduz a taxa de bits | `bitrate` (ex.: `64k`) |
| `format` | Converte o formato | `target_format` (wav, mp3, ogg, flac, m4a, opus) |

### Estrutura em disco

```
storage/<AAAA-MM-DD>/<uuid>/original/audio.<ext>
storage/<AAAA-MM-DD>/<uuid>/processed/audio.<ext>
storage/<AAAA-MM-DD>/<uuid>/waveform.png
storage/<AAAA-MM-DD>/<uuid>/meta.json
trash/<uuid>/...
```

A interface web para ouvir os áudios direto no navegador fica em [`/web`](/web).
"""

TAGS_METADATA = [
    {
        "name": "Áudios",
        "description": "Upload, histórico, reprodução e exclusão de áudios.",
    },
    {
        "name": "Lixeira",
        "description": "Exclusão reversível: restaurar, excluir definitivamente e esvaziar.",
    },
    {
        "name": "Infraestrutura",
        "description": "Estado do servidor, banco de dados e interface web.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Garante as pastas de armazenamento e as tabelas antes de aceitar requisições."""
    STORAGE_PATH.mkdir(parents=True, exist_ok=True)
    TRASH_PATH.mkdir(parents=True, exist_ok=True)
    init_db()
    logger.info("Storage em %s | lixeira em %s", STORAGE_PATH, TRASH_PATH)
    yield


app = FastAPI(
    title="Sistema de Processamento de Áudio",
    description=DESCRIPTION,
    version="2.0.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

# O cliente é desktop (PySide6), mas liberamos CORS para permitir testes
# no navegador (inclusive a interface web aberta de outra máquina).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition", "Content-Length", "Accept-Ranges"],
)

app.include_router(audio_router)
app.include_router(trash_router)


@app.get("/", tags=["Infraestrutura"], summary="Resumo dos endpoints do servidor")
def root():
    """Ponto de entrada simples para conferir se o servidor está no ar."""
    return {
        "message": "Servidor de processamento de áudio funcionando!",
        "docs": "/docs",
        "web": "/web",
        "endpoints": {
            "upload": "POST /audios/upload",
            "historico": "GET /audios/",
            "processamentos": "GET /audios/processing-types",
            "original": "GET /audios/{id}/original",
            "processado": "GET /audios/{id}/processed",
            "waveform": "GET /audios/{id}/waveform",
            "meta": "GET /audios/{id}/meta",
            "excluir": "DELETE /audios/{id}",
            "lixeira": "GET /trash/",
        },
    }


@app.get(
    "/health",
    response_model=HealthResponse,
    tags=["Infraestrutura"],
    summary="Verifica servidor, banco e pastas de armazenamento",
)
def health():
    """Testa a conexão com o PostgreSQL e informa os caminhos usados em disco."""
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        database_status = "ok"
    except Exception as error:  # pragma: no cover - depende do ambiente
        logger.error("Falha ao consultar o banco: %s", error)
        database_status = f"erro: {error}"

    return HealthResponse(
        status="ok" if database_status == "ok" else "degradado",
        database=database_status,
        storage_path=str(STORAGE_PATH),
        trash_path=str(TRASH_PATH),
    )


@app.get("/web", tags=["Infraestrutura"], summary="Interface web dos áudios")
def web_interface():
    """Interface web simples para ouvir os áudios armazenados pelo navegador."""
    return FileResponse(Path(__file__).parent / "web" / "index.html")


@app.get("/web/", include_in_schema=False)
def web_interface_trailing_slash():
    return web_interface()
