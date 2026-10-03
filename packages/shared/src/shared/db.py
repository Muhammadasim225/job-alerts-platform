"""Database engine and sessions (PostgreSQL via psycopg 3).

DATABASE_URL comes from the environment (repo-root .env), e.g.
    postgresql://postgres:secret@postgres:5432/jobalert    (inside Docker)
    postgresql://postgres:secret@localhost:5432/jobalert   (from the host)
"""

import os
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def normalize_url(url: str) -> str:
    """Use the psycopg 3 driver whatever scheme the URL was written with."""
    for prefix in ("postgresql+psycopg2://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix) :]
    return url


def database_url() -> str:
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    return normalize_url(url)


@lru_cache(maxsize=4)
def get_engine(url: str | None = None) -> Engine:
    return create_engine(normalize_url(url) if url else database_url(), pool_pre_ping=True, future=True)


def session_factory(url: str | None = None) -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(url), expire_on_commit=False)


@contextmanager
def session_scope(url: str | None = None):
    """A transaction: commits on success, rolls back on error."""
    session = session_factory(url)()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
