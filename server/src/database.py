"""Conexão com o PostgreSQL (SQLAlchemy)."""

import logging
import time

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker

from .config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
)

Base = declarative_base()

# Colunas adicionadas depois da primeira versão da tabela. Como o init.sql só roda
# quando o volume do PostgreSQL é criado, aplicamos aqui um ALTER TABLE idempotente
# para que bancos já existentes continuem funcionando sem precisar apagar o volume.
_EXTRA_COLUMNS = (
    ("processing_params", "JSONB"),
    ("checksum", "VARCHAR(64)"),
    ("deleted_at", "TIMESTAMP"),
)


def _apply_schema_updates() -> None:
    with engine.begin() as connection:
        for column_name, column_type in _EXTRA_COLUMNS:
            connection.execute(
                text(
                    f"ALTER TABLE audios "
                    f"ADD COLUMN IF NOT EXISTS {column_name} {column_type}"
                )
            )


def init_db(retries: int = 15, delay_seconds: float = 2.0) -> None:
    """Cria as tabelas (se necessário) aguardando o PostgreSQL ficar disponível."""
    # Import necessário para registrar o modelo no metadata do SQLAlchemy.
    from .models import audio  # noqa: F401

    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _apply_schema_updates()
            logger.info("Banco de dados pronto.")
            return
        except OperationalError:
            if attempt == retries:
                raise
            logger.warning(
                "PostgreSQL indisponível (tentativa %s/%s). Aguardando %.1fs...",
                attempt,
                retries,
                delay_seconds,
            )
            time.sleep(delay_seconds)
