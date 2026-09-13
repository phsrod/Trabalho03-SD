FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STORAGE_PATH=/app/storage \
    TRASH_PATH=/app/trash

WORKDIR /app

# O FFmpeg (ffmpeg + ffprobe) é usado para processar e inspecionar os áudios.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/

RUN mkdir -p /app/storage /app/trash

EXPOSE 8000

# --reload-dir limita o auto-reload ao código do servidor (ignora testes e storage).
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload", "--reload-dir", "/app/src"]
