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


def queue_alerts(stored: dict | None, record: dict) -> int:
    """Queue "new" alerts for a listing that just appeared or re-opened.
    Edits to a known open listing (OCR re-runs, review flags) never re-alert."""
    if not stored or record.get("status") != "open":
        return 0
    if not (stored["is_new"] or "status" in stored["changed_fields"]):
        return 0
    from shared.db import session_scope
    from shared.matching import queue_alerts_for_listing

    with session_scope(config.DATABASE_URL) as session:
        return queue_alerts_for_listing(session, stored["listing_db_id"])


def queue_reminders(days_before: int = 2) -> int:
    if not db_enabled():
        return 0
    from shared.db import session_scope
    from shared.matching import queue_deadline_reminders

    with session_scope(config.DATABASE_URL) as session:
        return queue_deadline_reminders(session, days_before=days_before)


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
