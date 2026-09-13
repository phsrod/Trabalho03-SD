from fastapi import FastAPI, Depends

from .database import engine
from .models.audio import Audio
from sqlalchemy.orm import Session
from .dependencies import get_db
from .routes.audio_routes import router as audio_router


app = FastAPI(
    title="Sistema de Processamento de Áudio",
    description="Servidor para envio, processamento e armazenamento de arquivos de áudio.",
    version="1.0.0"
)

app.include_router(audio_router)


@app.get("/")
def root():
    return {"message": "Servidor de processamento de áudio funcionando!"}


@app.get("/teste-banco")
def teste_banco(db: Session = Depends(get_db)):
    return {"message": "Conexão com PostgreSQL funcionando!"}