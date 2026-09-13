"""Dependências compartilhadas pelas rotas."""

from collections.abc import Iterator

from sqlalchemy.orm import Session

from .database import SessionLocal


def get_db() -> Iterator[Session]:
    """Fornece uma sessão do banco por requisição e garante o fechamento no final."""
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()
