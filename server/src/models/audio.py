"""Modelo ORM da tabela ``audios``."""

from pathlib import Path
from uuid import uuid4

from sqlalchemy import BigInteger, Column, DateTime, Float, Integer, String
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.sql import func

from ..database import Base


class Audio(Base):
    """Metadados de um áudio enviado, processado e armazenado."""

    __tablename__ = "audios"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid4)
    original_name = Column(String(255), nullable=False)
    original_ext = Column(String(20), nullable=False)
    mime_type = Column(String(100))
    size_bytes = Column(BigInteger)
    duration_sec = Column(Float)
    sample_rate = Column(Integer)
    channels = Column(Integer)
    bitrate = Column(Integer)
    processing_type = Column(String(50), nullable=False)
    processing_params = Column(JSONB)
    checksum = Column(String(64))
    created_at = Column(DateTime, default=func.current_timestamp(), nullable=False)
    deleted_at = Column(DateTime, nullable=True)
    path_original = Column(String, nullable=False)
    path_processed = Column(String, nullable=False)

    @property
    def directory(self) -> Path:
        """Pasta do UUID: contém ``original/``, ``processed/``, ``meta.json`` e ``waveform.png``."""
        return Path(self.path_original).parent.parent

    @property
    def processed_ext(self) -> str:
        return Path(self.path_processed).suffix.lower().lstrip(".")

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None
