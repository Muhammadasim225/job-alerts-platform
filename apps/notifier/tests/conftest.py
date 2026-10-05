"""Notifier tests run against a throwaway `<db>_notifytest` database (real migrations).
The service commits for real, so every table is emptied after each test. Skipped if
Postgres is unreachable."""

import os
import re
from pathlib import Path

os.environ.pop("SENTRY_DSN", None)
os.environ["APP_SECRET"] = "test-app-secret"

import pytest
from sqlalchemy import create_engine, text

import config
from shared.db import normalize_url, session_scope

ROOT = Path(__file__).resolve().parents[3]


def _url() -> str | None:
    if os.getenv("TEST_DATABASE_URL"):
        return normalize_url(os.environ["TEST_DATABASE_URL"])
    env = ROOT / ".env"
    url = os.getenv("DATABASE_URL")
    if not url and env.exists():
        url = next((l.split("=", 1)[1].strip() for l in env.read_text().splitlines() if l.startswith("DATABASE_URL=")), None)
    if not url:
        return None
    url = re.sub(r"@[^:/]+(:\d+)?/", r"@localhost\1/", normalize_url(url))
    return re.sub(r"/(\w+)$", r"/\1_notifytest", url)


@pytest.fixture(scope="session")
def db_url():
    url = _url()
    if not url:
        pytest.skip("no DATABASE_URL")
    admin_url, name = url.rsplit("/", 1)
    try:
        admin = create_engine(f"{admin_url}/postgres", isolation_level="AUTOCOMMIT")
        with admin.connect() as c:
            c.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
            c.execute(text(f'CREATE DATABASE "{name}"'))
        admin.dispose()
    except Exception as exc:
        pytest.skip(f"Postgres not reachable: {exc}")
    from shared.migrate import upgrade

    upgrade(url)
    return url


@pytest.fixture
def db(db_url, monkeypatch):
    """Point the service at the test database; empty it afterwards."""
    monkeypatch.setattr(config, "DATABASE_URL", db_url)
    yield lambda: session_scope(db_url)
    engine = create_engine(db_url)
    with engine.begin() as c:
        c.execute(text("TRUNCATE users, listings, alerts, deliveries, push_subscriptions, auth_sessions CASCADE"))
    engine.dispose()
