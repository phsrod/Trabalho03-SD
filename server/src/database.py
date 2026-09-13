# Conexão com o PostgreSQL (SQLAlchemy) e preparação do esquema.

import logging
import time

from sqlalchemy import create_engine, inspect, text
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


def _add_missing_columns() -> None:
    from .models.audio import Audio

    table_name = Audio.__tablename__
    inspector = inspect(engine)

    if not inspector.has_table(table_name):
        return

    existing = {column["name"] for column in inspector.get_columns(table_name)}

    missing = [
        column
        for column in Audio.__table__.columns
        if column.name not in existing
        and (column.nullable or column.default is not None or column.server_default is not None)
    ]

    if not missing:
        return

    with engine.begin() as connection:
        for column in missing:
            column_type = column.type.compile(dialect=engine.dialect)
            connection.execute(
                text(f'ALTER TABLE {table_name} ADD COLUMN IF NOT EXISTS "{column.name}" {column_type}')
            )
            logger.info("Coluna adicionada: %s.%s (%s)", table_name, column.name, column_type)


def init_db(retries: int = 15, delay_seconds: float = 2.0) -> None:
    from .models import audio  # noqa: F401

    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
            _add_missing_columns()
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
