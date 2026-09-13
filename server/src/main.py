from fastapi import FastAPI

app = FastAPI(
    title="Sistema de Processamento de Áudio",
    description="Servidor para envio, processamento e armazenamento de arquivos de áudio.",
    version="1.0.0"
)


@app.get("/")
def root():
    return {"message": "Servidor de processamento de áudio funcionando!"}