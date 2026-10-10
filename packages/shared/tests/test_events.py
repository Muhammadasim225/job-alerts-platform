"""The listing_events outbox: events written with the change, processed once, retried
with backoff; deadline reminders in PKT that follow an extended last date."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from shared import heartbeat
from shared.events import BACKOFF_S, MAX_ATTEMPTS, PARKED, Handlers, cache_tags, process_batch, process_events
from shared.matching import queue_deadline_reminders, today_pkt
from shared.models import Alert, DeadlineChange, Listing, ListingEvent, Preference, SavedListing, User
from shared.repository import upsert_listing
from shared.slugs import slugify

FIXTURES = Path(__file__).parent / "fixtures"
SOON = today_pkt() + timedelta(days=30)  # handlers match against the real (PKT) today
DUE = datetime(2000, 1, 1, tzinfo=UTC)  # due for a retry (DB now() is the test transaction start)


def record(name="record_job_wcla", **overrides):
    rec = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))
    rec.update({"status": "open", "last_date": SOON.isoformat(), **overrides})
    return rec


def user(session, email, **pref):
    u = User(email=email, preference=Preference(**({"kinds": ["job"]} | pref)))
    session.add(u)
    session.flush()
    return u


def events(session, listing_id):
    return session.scalars(select(ListingEvent).where(ListingEvent.listing_id == listing_id).order_by(ListingEvent.id)).all()


def alerts(session, listing_id, alert_type):
    return session.scalars(select(Alert).where(Alert.listing_id == listing_id, Alert.alert_type == alert_type)).all()


class Recorder:
    def __init__(self, fail=False):
        self.calls, self.bumps, self.fail = [], 0, fail

    def revalidate(self, event_id, tags):
        if self.fail:
            raise ConnectionError("web down")
        self.calls.append((event_id, tags))

    def bump(self):
        self.bumps += 1

    def handlers(self):
        return Handlers(revalidate=self.revalidate, bump_cache=self.bump)


# --- events are written with the change ----------------------------------------


def test_new_listing_writes_a_created_event(session):
    res = upsert_listing(session, record())
    assert res.events == ["created"]
    assert [e.type for e in events(session, res.listing.id)] == ["created"]


def test_unchanged_reupsert_writes_no_event(session):
    upsert_listing(session, record())
    assert upsert_listing(session, record()).events == []


def test_deadline_change_writes_history_and_event_together(session):
    lid = upsert_listing(session, record()).listing.id
    later = SOON + timedelta(days=7)
    assert upsert_listing(session, record(last_date=later.isoformat())).events == ["deadline_changed"]
    change = session.scalar(select(DeadlineChange).where(DeadlineChange.listing_id == lid))
    assert (change.old_date, change.new_date) == (SOON, later)
    assert events(session, lid)[-1].payload == {"old": SOON.isoformat(), "new": later.isoformat()}


def test_status_and_content_changes(session):
    lid = upsert_listing(session, record()).listing.id
    assert upsert_listing(session, record(status="closed")).events == ["closed"]
    assert upsert_listing(session, record(status="open")).events == ["reopened"]
    assert upsert_listing(session, record(title="Changed title")).events == ["updated"]
    assert [e.type for e in events(session, lid)] == ["created", "closed", "reopened", "updated"]


# --- the worker -------------------------------------------------------------------


def test_one_event_queues_alerts_revalidates_and_bumps_cache(session):
    it_user = user(session, "outbox1@example.com", fields=["it"])
    listing = upsert_listing(session, record()).listing
    rec = Recorder()

    assert process_batch(session, rec.handlers()) == {"processed": 1, "failed": 0, "batch": 1}
    assert [a.user_id for a in alerts(session, listing.id, "new")] == [it_user.id]
    ((event_id, tags),) = rec.calls
    assert event_id == events(session, listing.id)[0].id
    assert {f"listing:{listing.id}", "listings", "home", "hub:lahore", "hub:punjab"} <= set(tags)
    assert rec.bumps == 1
    assert events(session, listing.id)[0].processed_at is not None


def test_processed_events_are_not_handled_again(session):
    user(session, "outbox2@example.com")
    listing = upsert_listing(session, record()).listing
    rec = Recorder()
    process_batch(session, rec.handlers())
    assert process_batch(session, rec.handlers())["batch"] == 0
    assert len(rec.calls) == 1 and len(alerts(session, listing.id, "new")) == 1


def test_cache_tags_cover_org_city_province_and_field_hubs(session):
    listing = upsert_listing(session, record()).listing
    tags = cache_tags(session, listing)
    assert f"org:{listing.org.slug}" in tags
    assert {"hub:lahore", "hub:punjab", "hub:it"} <= set(tags)


def test_failing_event_backs_off_then_parks_without_its_db_work(session):
    user(session, "outbox3@example.com")
    listing = upsert_listing(session, record()).listing
    event = events(session, listing.id)[0]
    rec = Recorder(fail=True)

    assert process_batch(session, rec.handlers()) == {"processed": 0, "failed": 1, "batch": 1}
    assert alerts(session, listing.id, "new") == []  # the savepoint undid the alert insert
    assert event.attempts == 1 and "web down" in event.last_error and event.processed_at is None
    due_in = event.next_attempt_at - datetime.now(UTC)
    assert timedelta(seconds=BACKOFF_S[0] - 5) < due_in <= timedelta(seconds=BACKOFF_S[0])
    assert process_batch(session, rec.handlers())["batch"] == 0  # not due yet

    for _ in range(MAX_ATTEMPTS - 1):
        event.next_attempt_at = DUE
        session.flush()
        process_batch(session, rec.handlers())
    assert event.attempts == MAX_ATTEMPTS and event.next_attempt_at == PARKED

    rec.fail = False  # the web is back: the next due retry goes through
    event.next_attempt_at = DUE
    session.flush()
    assert process_batch(session, rec.handlers())["processed"] == 1
    assert event.last_error is None and len(alerts(session, listing.id, "new")) == 1


def test_one_bad_event_does_not_block_the_others(session):
    user(session, "outbox4@example.com")
    bad = upsert_listing(session, record()).listing
    good = upsert_listing(session, record("record_admission_uom")).listing
    seen = []

    def revalidate(event_id, tags):
        if f"listing:{bad.id}" in tags:
            raise RuntimeError("boom")
        seen.append(event_id)

    assert process_batch(session, Handlers(revalidate=revalidate)) == {"processed": 1, "failed": 1, "batch": 2}
    assert seen == [events(session, good.id)[0].id]


def test_workers_never_claim_the_same_event(db_url):
    """Real concurrency: SKIP LOCKED makes a second worker pass over locked events."""
    engine = create_engine(db_url)
    with Session(engine) as setup:
        lid = upsert_listing(setup, record(listing_id="race-outbox")).listing.id
        setup.commit()
    s1, s2 = Session(engine), Session(engine)
    try:
        s1.scalars(select(ListingEvent).where(ListingEvent.listing_id == lid).with_for_update()).all()
        assert process_batch(s2, Handlers())["batch"] == 0
        s1.rollback()
        assert process_events(sessionmaker(engine), Handlers())["processed"] == 1
    finally:
        s1.close(), s2.rollback(), s2.close()
        with Session(engine) as cleanup:
            cleanup.query(Listing).filter(Listing.external_id == "race-outbox").delete()
            cleanup.commit()
        engine.dispose()


# --- reminders: two days before the last date, PKT ------------------------------


def _sent_new_alert(session, listing, u):
    session.add(Alert(user_id=u.id, listing_id=listing.id, alert_type="new", status="sent"))
    session.flush()


def test_reminders_for_alerted_and_saved_users_in_the_two_day_window(session):
    listing = upsert_listing(session, record()).listing
    alerted, saver, muted = (user(session, f"rem{i}@example.com") for i in range(3))
    _sent_new_alert(session, listing, alerted)
    session.add_all(
        [
            SavedListing(user_id=saver.id, listing_id=listing.id),
            SavedListing(user_id=muted.id, listing_id=listing.id, remind=False),
        ]
    )
    session.flush()

    assert queue_deadline_reminders(session, today=SOON - timedelta(days=3)) == 0  # too early
    assert queue_deadline_reminders(session, today=SOON - timedelta(days=2)) == 2
    assert queue_deadline_reminders(session, today=SOON - timedelta(days=1)) == 0  # once per deadline
    got = alerts(session, listing.id, "deadline_reminder")
    assert {a.user_id for a in got} == {alerted.id, saver.id} and {a.deadline for a in got} == {SOON}


def test_today_pkt_is_karachi_time():
    from zoneinfo import ZoneInfo

    assert today_pkt() == datetime.now(ZoneInfo("Asia/Karachi")).date()


def test_extension_moves_the_reminder_to_the_new_date(session):
    listing = upsert_listing(session, record()).listing
    alerted, saver = user(session, "ext1@example.com"), user(session, "ext2@example.com")
    _sent_new_alert(session, listing, alerted)
    session.add(SavedListing(user_id=saver.id, listing_id=listing.id))
    session.flush()
    process_batch(session, Handlers())  # the "created" event
    queue_deadline_reminders(session, today=SOON - timedelta(days=1))
    assert len(alerts(session, listing.id, "deadline_reminder")) == 2  # pending

    later = SOON + timedelta(days=10)
    upsert_listing(session, record(last_date=later.isoformat()))
    process_batch(session, Handlers())

    assert alerts(session, listing.id, "deadline_reminder") == []  # stale reminders dropped
    extended = alerts(session, listing.id, "deadline_extended")
    assert {a.user_id for a in extended} >= {alerted.id, saver.id} and {a.deadline for a in extended} == {later}
    assert queue_deadline_reminders(session, today=later - timedelta(days=2)) == 2
    assert {a.deadline for a in alerts(session, listing.id, "deadline_reminder")} == {later}


def test_sent_reminder_survives_and_shortened_deadline_sends_no_extension(session):
    listing = upsert_listing(session, record()).listing
    u = user(session, "short@example.com")
    _sent_new_alert(session, listing, u)
    queue_deadline_reminders(session, today=SOON)
    session.execute(Alert.__table__.update().where(Alert.alert_type == "deadline_reminder").values(status="sent"))
    process_batch(session, Handlers())

    earlier = SOON - timedelta(days=5)
    upsert_listing(session, record(last_date=earlier.isoformat()))
    process_batch(session, Handlers())
    assert len(alerts(session, listing.id, "deadline_reminder")) == 1  # already sent: history stays
    assert alerts(session, listing.id, "deadline_extended") == []


# --- small pieces -------------------------------------------------------------


def test_slug_never_ends_on_a_dangling_word():
    slug = slugify("Ministry of Federal Education and Professional Training Government of Pakistan", max_len=71)
    assert slug == "ministry-of-federal-education-and-professional-training-government"


def test_heartbeat_is_a_noop_without_url_and_never_raises(monkeypatch):
    assert heartbeat.ping(None) is False
    sent = []

    def fake_urlopen(req, timeout):
        sent.append(req.full_url)
        raise OSError("network down")

    monkeypatch.setattr(heartbeat.urllib.request, "urlopen", fake_urlopen)
    assert heartbeat.ping("https://hc-ping.com/abc/", ok=False, message="x") is False
    assert sent == ["https://hc-ping.com/abc/fail"]


def test_event_counts_are_visible(session):
    upsert_listing(session, record())
    pending = select(func.count()).select_from(ListingEvent).where(ListingEvent.processed_at.is_(None))
    assert session.scalar(pending) >= 1
    process_batch(session, Handlers())
    assert session.scalar(pending) == 0
