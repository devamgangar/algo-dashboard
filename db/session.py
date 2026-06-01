"""Database engine + session factory.

One process-wide engine, lazily created. `get_session()` is a context manager:
commits on success, rolls back on exception, always closes.

On first import, ensures the DB file exists and has the schema applied. This
makes the app deployable to environments where `python db/init_db.py` was never
run manually (e.g., Streamlit Community Cloud).
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "backtest.db"


def _ensure_db_initialized() -> None:
    """Idempotent: create the DB and apply the schema if the file is missing.

    Schema uses CREATE TABLE IF NOT EXISTS, so it's safe even if partially
    initialized. Imported here (not at module top) to avoid circular imports.
    """
    if DB_PATH.exists():
        return
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    from db.init_db import init_db
    init_db()


_ensure_db_initialized()

_engine = create_engine(
    f"sqlite:///{DB_PATH}",
    future=True,
    echo=False,
)


# SQLite has foreign-key enforcement OFF by default. Turn it on for every
# new DBAPI connection so ON DELETE CASCADE actually works.
@event.listens_for(_engine, "connect")
def _enable_foreign_keys(dbapi_conn, _connection_record) -> None:
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.close()


_SessionLocal = sessionmaker(bind=_engine, expire_on_commit=False, future=True)


@contextmanager
def get_session() -> Iterator[Session]:
    """Yield a session, commit on success, rollback on exception, always close."""
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_engine():
    return _engine
