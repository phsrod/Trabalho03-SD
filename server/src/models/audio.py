from sqlalchemy import Column, String, BigInteger, Float, Integer, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from ..database import Base


class Audio(Base):
    __tablename__ = "audios"

    id = Column(UUID(as_uuid=True), primary_key=True)
    original_name = Column(String(255), nullable=False)
    original_ext = Column(String(20), nullable=False)
    mime_type = Column(String(100))
    size_bytes = Column(BigInteger)
    duration_sec = Column(Float)
    sample_rate = Column(Integer)
    channels = Column(Integer)
    bitrate = Column(Integer)
    processing_type = Column(String(50), nullable=False)
    created_at = Column(DateTime, server_default=func.current_timestamp())
    path_original = Column(String, nullable=False)
    path_processed = Column(String, nullable=False)