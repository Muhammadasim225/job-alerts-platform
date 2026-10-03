"""API tests run against a throwaway `<db>_apitest` Postgres database built with the
real migrations, seeded with real normalized NTS records. Each test runs inside a
transaction that is rolled back. Skipped if Postgres is unreachable."""

import json
import os
import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

import app.deps as deps
from app.config import Settings
from app.main import app
from shared.db import normalize_url
from shared.repository import upsert_listing

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "packages" / "shared" / "tests" / "fixtures"
API_KEY = "test-internal-key"


def _url() -> str | None:
    if os.getenv("TEST_DATABASE_URL"):
        return normalize_url(os.environ["TEST_DATABASE_URL"])
    env = ROOT / ".env"
    url = os.getenv("DATABASE_URL") or next(
        (l.split("=", 1)[1].strip() for l in env.read_text().splitlines() if l.startswith("DATABASE_URL=")), None
    ) if env.exists() else os.getenv("DATABASE_URL")
    if not url:
        return None
    url = re.sub(r"@[^:/]+(:\d+)?/", r"@localhost\1/", normalize_url(url))
    return re.sub(r"/(\w+)$", r"/\1_apitest", url)


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


def load_record(name: str, **overrides) -> dict:
    rec = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))
    rec.update(overrides)
    return rec


@pytest.fixture
def db(db_url):
    engine = create_engine(db_url)
    conn = engine.connect()
    trans = conn.begin()
    session = Session(bind=conn, join_transaction_mode="create_savepoint")
    # Seed: an open job (WCLA) and an open admission (UOM) with future deadlines
    soon = (date.today() + timedelta(days=5)).isoformat()
    later = (date.today() + timedelta(days=20)).isoformat()
    upsert_listing(session, load_record("record_job_wcla", status="open", last_date=soon))
    upsert_listing(session, load_record("record_admission_uom", status="open", last_date=later))
    upsert_listing(session, load_record("record_job_wcla", listing_id="old-closed", status="closed", last_date="2026-01-01"))
    session.flush()
    yield session
    session.close()
    trans.rollback()
    conn.close()
    engine.dispose()


@pytest.fixture
def client(db, monkeypatch):
    app.dependency_overrides[deps.get_db] = lambda: db
    monkeypatch.setattr(deps, "settings", Settings(internal_api_key=API_KEY))
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def internal(client):
    client.headers.update({"X-API-Key": API_KEY})
    return client
