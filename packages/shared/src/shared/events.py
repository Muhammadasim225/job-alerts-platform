"""The listing_events outbox worker.

repository.upsert_listing writes a listing change and its event in one transaction.
This worker reads unprocessed events with SELECT ... FOR UPDATE SKIP LOCKED (several
workers never take the same event) and does three things per event:

  1. alerts     created/reopened -> "new" alerts for matching users;
                deadline_changed -> drop stale reminders, "deadline_extended" alerts
  2. revalidate POST the website's revalidation webhook with the cache tags of the
                listing page and every hub it appears on (home, its org, city,
                province and field hubs)
  3. caches     bump the public API cache version (cached hub counts / stats expire)

Idempotency: the alert inserts and processed_at are committed in the same
transaction, so an event's DB work happens once; alert inserts are ON CONFLICT DO
NOTHING anyway, and the webhook carries the event id and is safe to repeat. A failing
event is retried with backoff (1 min, 5 min, 30 min, 2 h, 6 h) and then parked with
its error for a human to look at; other events keep flowing.
"""

import json
import logging
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from shared.matching import queue_alerts_for_listing, queue_deadline_change_alerts
from shared.models import HubSlug, Listing, ListingEvent

log = logging.getLogger(__name__)

BACKOFF_S = (60, 300, 1800, 7200, 21600)
MAX_ATTEMPTS = len(BACKOFF_S) + 1
PARKED = datetime(9999, 1, 1, tzinfo=UTC)  # gave up: needs a human


@dataclass
class Handlers:
    """Side effects outside the database; None = not configured (local dev)."""

    revalidate: Callable[[int, list[str]], None] | None = None
    bump_cache: Callable[[], None] | None = None
    extra: dict = field(default_factory=dict)


def cache_tags(session: Session, listing: Listing) -> list[str]:
    """Next.js cache tags whose pages show this listing."""
    tags = {f"listing:{listing.id}", "listings", "home"}
    if listing.org is not None:
        tags.add(f"org:{listing.org.slug}")
    values = set(listing.cities or []) | set(listing.provinces or [])
    fields = {v.field for v in listing.vacancies if v.field}
    hubs = session.scalars(
        select(HubSlug.slug).where(
            ((HubSlug.kind != "field") & HubSlug.matches.overlap(sorted(values)))
            | ((HubSlug.kind == "field") & HubSlug.matches.overlap(sorted(fields)))
        )
    ).all()
    tags.update(f"hub:{slug}" for slug in hubs)
    return sorted(tags)


def handle(session: Session, event: ListingEvent, handlers: Handlers) -> None:
    listing = session.get(Listing, event.listing_id)
    if listing is None:  # deleted meanwhile: nothing to do
        return
    if event.type in ("created", "reopened") and listing.status == "open":
        queue_alerts_for_listing(session, listing.id)
    elif event.type == "deadline_changed":
        old, new = (event.payload or {}).get("old"), (event.payload or {}).get("new")
        queue_deadline_change_alerts(
            session, listing.id, date.fromisoformat(old) if old else None, date.fromisoformat(new) if new else None
        )
    if handlers.revalidate:
        handlers.revalidate(event.id, cache_tags(session, listing))
    if handlers.bump_cache:
        handlers.bump_cache()


def process_events(factory: sessionmaker[Session], handlers: Handlers, batch: int = 50) -> dict:
    """Process one batch of due events in one transaction. Returns counts for logs and
    the heartbeat."""
    with factory() as session, session.begin():
        return process_batch(session, handlers, batch)


def process_batch(session: Session, handlers: Handlers, batch: int = 50) -> dict:
    """Claim and handle due events inside the caller's transaction (does not commit)."""
    done = failed = 0
    events = session.scalars(
        select(ListingEvent)
        .where(ListingEvent.processed_at.is_(None), ListingEvent.next_attempt_at <= func.now())
        .order_by(ListingEvent.id)
        .limit(batch)
        .with_for_update(skip_locked=True)
    ).all()
    for event in events:
        try:
            with session.begin_nested():  # an event's failure undoes only its own DB work
                handle(session, event, handlers)
            event.processed_at = datetime.now(UTC)
            event.last_error = None
            done += 1
        except Exception as exc:
            failed += 1
            event.attempts += 1
            event.last_error = f"{type(exc).__name__}: {exc}"[:1000]
            if event.attempts >= MAX_ATTEMPTS:
                event.next_attempt_at = PARKED
                log.error("Listing event %s parked after %d attempts: %s", event.id, event.attempts, event.last_error)
            else:
                event.next_attempt_at = datetime.now(UTC) + timedelta(seconds=BACKOFF_S[event.attempts - 1])
                log.warning("Listing event %s failed (attempt %d): %s", event.id, event.attempts, event.last_error)
    return {"processed": done, "failed": failed, "batch": len(events)}


def revalidator(url: str | None, secret: str | None, timeout: float = 5.0):
    """Webhook caller for the website's POST /api/revalidate; None when not configured."""
    if not url or not secret:
        return None

    def call(event_id: int, tags: list[str]) -> None:
        body = json.dumps({"event_id": event_id, "tags": tags}).encode()
        req = urllib.request.Request(
            url, data=body, method="POST", headers={"Content-Type": "application/json", "X-Revalidate-Secret": secret}
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            if resp.status >= 300:
                raise RuntimeError(f"revalidate webhook answered {resp.status}")

    return call


PUBLIC_CACHE_VERSION_KEY = "cache:public:version"


def cache_bumper(redis_client):
    """Invalidate every cached public API response by bumping their version key."""
    if redis_client is None:
        return None
    return lambda: redis_client.incr(PUBLIC_CACHE_VERSION_KEY)
