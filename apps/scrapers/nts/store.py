"""Persist normalized records to Postgres (schema in packages/shared)."""

import json
import logging

import config

log = logging.getLogger(__name__)


def db_enabled() -> bool:
    return bool(config.DATABASE_URL)


def store_record(record: dict) -> dict | None:
    """Upsert one normalized record. Returns {listing_db_id, is_new, changed_fields},
    or None when no database is configured. Raises on DB errors so the caller does
    not mark the listing processed (it is retried on the next run)."""
    if not db_enabled():
        return None
    from shared.db import session_scope
    from shared.repository import upsert_listing

    with session_scope(config.DATABASE_URL) as session:
        res = upsert_listing(session, record)
        return {"listing_db_id": res.listing.id, "is_new": res.is_new, "changed_fields": res.changed_fields}


def backfill(paths) -> tuple[int, int]:
    """Load existing normalized JSON files into the database: (stored, failed)."""
    stored = failed = 0
    for path in paths:
        try:
            store_record(json.loads(path.read_text(encoding="utf8")))
            stored += 1
        except Exception:
            log.exception("Backfill failed for %s", path)
            failed += 1
    return stored, failed
