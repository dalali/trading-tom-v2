"""SQLAlchemy engine/session/Base setup.

Important: creating the engine here does NOT connect to the database —
SQLAlchemy's create_engine() is lazy; the first real connection happens
on first use (e.g. the first query or alembic's run). This keeps module
import safe with no live DB required (architecture Section 8.1 startup
ordering: db healthy -> alembic upgrade head -> bootstrap -> uvicorn).
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency: yields a session, always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
