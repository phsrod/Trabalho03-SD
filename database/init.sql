-- Estrutura inicial do banco. Executado automaticamente pelo container do
-- PostgreSQL na primeira vez que o volume é criado.
--
-- Observação: se o volume já existir, o servidor aplica as colunas extras via
-- ALTER TABLE (ver server/src/database.py). Para recriar tudo do zero:
--     docker compose down -v && docker compose up --build

CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS audios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Dados do arquivo ORIGINAL enviado pelo cliente.
    original_name VARCHAR(255) NOT NULL,
    original_ext VARCHAR(20) NOT NULL,
    mime_type VARCHAR(100),
    size_bytes BIGINT,
    duration_sec DOUBLE PRECISION,
    sample_rate INTEGER,
    channels INTEGER,
    bitrate INTEGER,

    -- Processamento aplicado e parâmetros usados (ex.: {"speed_factor": 1.5}).
    processing_type VARCHAR(50) NOT NULL,
    processing_params JSONB,

    -- Checksum SHA-256 do arquivo original (também gravado no meta.json).
    checksum VARCHAR(64),

    -- Controle de exclusão: quando preenchido, o áudio está na lixeira.
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    -- Caminhos em disco do original e do processado.
    path_original TEXT NOT NULL,
    path_processed TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audios_created_at ON audios (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audios_processing_type ON audios (processing_type);
CREATE INDEX IF NOT EXISTS idx_audios_deleted_at ON audios (deleted_at);
