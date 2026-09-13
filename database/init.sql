CREATE EXTENSION IF NOT EXISTS "pgcrypto";

CREATE TABLE IF NOT EXISTS audios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    original_name VARCHAR(255) NOT NULL,
    original_ext VARCHAR(20) NOT NULL,
    mime_type VARCHAR(100),
    size_bytes BIGINT,
    duration_sec DOUBLE PRECISION,
    sample_rate INTEGER,
    channels INTEGER,
    bitrate INTEGER,
    processing_type VARCHAR(50) NOT NULL,
    processing_params JSONB,
    checksum VARCHAR(64),
    deleted_at TIMESTAMP,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    path_original TEXT NOT NULL,
    path_processed TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_audios_created_at ON audios (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audios_processing_type ON audios (processing_type);
CREATE INDEX IF NOT EXISTS idx_audios_deleted_at ON audios (deleted_at);
