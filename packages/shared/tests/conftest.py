"""Tests run against a throwaway `<db>_test` database on the local Postgres
container, built with the real migrations. Skipped if Postgres is unreachable.

The URL is TEST_DATABASE_URL, or DATABASE_URL from the repo-root .env with the
host switched to localhost and the database name suffixed with _test.
"""

import os
import re
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from shared.db import normalize_url


def _test_url() -> str | None:
    if os.getenv("TEST_DATABASE_URL"):
        return normalize_url(os.environ["TEST_DATABASE_URL"])
    env = Path(__file__).resolve().parents[3] / ".env"
    url = os.getenv("DATABASE_URL")
    if not url and env.exists():
        url = next((l.split("=", 1)[1].strip() for l in env.read_text().splitlines() if l.startswith("DATABASE_URL=")), None)
    if not url:
        return None
    url = re.sub(r"@[^:/]+(:\d+)?/", r"@localhost\1/", normalize_url(url))
    return re.sub(r"/(\w+)$", r"/\1_test", url)


@pytest.fixture(scope="session")
def db_url():
    url = _test_url()
    if not url:
        pytest.skip("no DATABASE_URL / TEST_DATABASE_URL")
    admin_url, name = url.rsplit("/", 1)
    try:
        admin = create_engine(f"{admin_url}/postgres", isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
    except Exception as exc:  # Postgres not running
        pytest.skip(f"Postgres not reachable: {exc}")

    from shared.migrate import upgrade

    upgrade(url)
    return url


@pytest.fixture
def session(db_url):
    """A session whose changes are rolled back after each test."""
    engine = create_engine(db_url)
    conn = engine.connect()
    trans = conn.begin()
    s = Session(bind=conn, join_transaction_mode="create_savepoint")
    yield s
    s.close()
    trans.rollback()
    conn.close()
    engine.dispose()
