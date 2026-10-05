"""Notification outbox: batching alerts into deliveries, exactly-once claims, retries."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from shared import notifications as n
from shared.models import Alert, AuthSession, Delivery, Listing, PushSubscription, User

NOW = datetime(2026, 10, 5, 6, 30, tzinfo=UTC)


def _user(session, email, push=False, verified=True, **kw):
    u = User(email=email, email_verified_at=NOW if verified else None, **kw)
    if push:
        u.push_subscriptions.append(PushSubscription(endpoint=f"https://push.example/{email}", p256dh="k", auth="a"))
    session.add(u)
    session.flush()
    return u


def _listings(session, count, prefix="n"):
    rows = [
        Listing(source="nts", external_id=f"{prefix}-{i}", url="u", status="open", kind="job", title=f"t{i}")
        for i in range(count)
    ]
    session.add_all(rows)
    session.flush()
    return rows


def _alerts(session, user, listings, age=timedelta(minutes=30)):
    rows = [Alert(user_id=user.id, listing_id=l.id, alert_type="new", created_at=NOW - age) for l in listings]
    session.add_all(rows)
    session.flush()
    return rows


def test_one_delivery_per_channel_carries_all_of_a_users_alerts(session):
    both = _user(session, "both@example.com", push=True)
    email_only = _user(session, "mail@example.com")
    listings = _listings(session, 3)
    _alerts(session, both, listings)
    _alerts(session, email_only, listings[:1])

    ids = n.dispatch(session, now=NOW)
    rows = session.scalars(select(Delivery).where(Delivery.id.in_(ids))).all()
    got = sorted((d.user_id, d.channel, len(d.alert_ids)) for d in rows)
    assert got == sorted([(both.id, "email", 3), (both.id, "push", 3), (email_only.id, "email", 1)])
    assert {a.status for a in session.scalars(select(Alert))} == {"sent"}
    assert n.dispatch(session, now=NOW) == []  # nothing pending any more


def test_batch_waits_until_the_users_alerts_settle(session):
    u = _user(session, "settle@example.com")
    old, fresh = _listings(session, 2)
    _alerts(session, u, [old], age=timedelta(minutes=20))
    _alerts(session, u, [fresh], age=timedelta(minutes=2))  # the morning run is still matching
    assert n.dispatch(session, now=NOW) == []
    # ...but never longer than MAX_WAIT
    assert len(n.dispatch(session, now=NOW + n.MAX_WAIT)) == 1


def test_no_channel_means_inbox_only_and_inactive_users_are_skipped(session):
    quiet = _user(session, "quiet@example.com", email_alerts=False, push_alerts=False)
    unverified = _user(session, "new@example.com", verified=False)
    off = _user(session, "off@example.com", is_active=False)
    listing = _listings(session, 1)
    for u in (quiet, unverified, off):
        _alerts(session, u, listing)
    assert n.dispatch(session, now=NOW) == []
    status = {a.user_id: a.status for a in session.scalars(select(Alert))}
    assert status == {quiet.id: "sent", unverified.id: "sent", off.id: "skipped"}


def test_claim_send_retry_and_give_up(session):
    u = _user(session, "retry@example.com")
    _alerts(session, u, _listings(session, 1))
    [did] = n.dispatch(session, now=NOW)

    assert n.take_due(session, now=NOW) == [did]
    assert n.take_due(session, now=NOW) == []  # already handed to the broker
    d = n.claim_delivery(session, did, now=NOW)
    assert d.status == "sending" and d.attempts == 1
    assert n.claim_delivery(session, did, now=NOW) is None  # a redelivered message sends nothing

    d = n.mark_delivery_failed(session, did, "SMTP timeout", now=NOW)
    assert d.status == "pending" and d.next_attempt_at == NOW + n.BACKOFF[0]
    assert n.take_due(session, now=NOW) == []  # backing off
    assert n.take_due(session, now=NOW + n.BACKOFF[0]) == [did]

    for _ in range(n.MAX_ATTEMPTS - 1):
        n.claim_delivery(session, did, now=NOW)
        d = n.mark_delivery_failed(session, did, "SMTP timeout", now=NOW)
    assert d.status == "failed" and d.attempts == n.MAX_ATTEMPTS


def test_permanent_failure_and_sent(session):
    u = _user(session, "perm@example.com", push=True)
    _alerts(session, u, _listings(session, 1))
    email, push = sorted(n.dispatch(session, now=NOW))
    n.claim_delivery(session, email)
    assert n.mark_delivery_failed(session, email, "550 no such user", permanent=True).status == "failed"
    n.claim_delivery(session, push)
    assert n.mark_delivery_sent(session, push, now=NOW).sent_at == NOW


def test_crashed_sender_claim_is_handed_out_again(session):
    u = _user(session, "crash@example.com")
    _alerts(session, u, _listings(session, 1))
    [did] = n.dispatch(session, now=NOW)
    n.claim_delivery(session, did, now=NOW)
    assert n.take_due(session, now=NOW + timedelta(minutes=1)) == []
    assert n.take_due(session, now=NOW + n.STALE_AFTER + timedelta(seconds=1)) == [did]
    assert n.claim_delivery(session, did).attempts == 2


def test_skip_pending_on_switch_off(session):
    u = _user(session, "stop@example.com", push=True)
    first, second = _listings(session, 2)
    _alerts(session, u, [first])
    n.dispatch(session, now=NOW)
    _alerts(session, u, [second])

    n.skip_pending(session, u.id, "email alerts switched off", channel="email")
    by_channel = {d.channel: d.status for d in session.scalars(select(Delivery))}
    assert by_channel == {"email": "skipped", "push": "pending"}

    n.skip_pending(session, u.id, "alerts switched off")
    assert {d.status for d in session.scalars(select(Delivery))} == {"skipped"}
    assert session.scalar(select(Alert.status).where(Alert.listing_id == second.id)) == "skipped"


def test_cleanup_drops_expired_sessions_and_old_deliveries(session):
    u = _user(session, "old@example.com")
    session.add_all(
        [
            AuthSession(user_id=u.id, token_hash="a" * 64, expires_at=NOW - timedelta(days=1)),
            AuthSession(user_id=u.id, token_hash="b" * 64, expires_at=NOW + timedelta(days=1)),
            Delivery(user_id=u.id, channel="email", alert_ids=[], status="sent", created_at=NOW - timedelta(days=100)),
            Delivery(user_id=u.id, channel="email", alert_ids=[], status="pending", created_at=NOW - timedelta(days=100)),
        ]
    )
    session.flush()
    assert n.cleanup(session, now=NOW) == {"sessions": 1, "deliveries": 1}


def test_two_notifiers_never_claim_the_same_delivery(db_url):
    """Real concurrency: two connections race for the same rows (SKIP LOCKED)."""
    engine = create_engine(db_url)
    with Session(engine) as setup:
        u = _user(setup, "race@example.com")
        _alerts(setup, u, _listings(setup, 2, prefix="race"))
        did = n.dispatch(setup, now=NOW)[0]
        setup.commit()
    s1, s2 = Session(engine), Session(engine)
    try:
        assert n.claim_delivery(s1, did) is not None  # s1's transaction still open: row locked
        assert n.claim_delivery(s2, did) is None
        assert n.take_due(s2, now=NOW + timedelta(days=1)) == []  # locked rows are skipped, not waited on
    finally:
        s1.rollback(), s2.rollback()
        s1.close(), s2.close()
        with Session(engine) as cleanup:
            cleanup.query(User).filter(User.email == "race@example.com").delete()
            cleanup.query(Listing).filter(Listing.external_id.like("race-%")).delete()
            cleanup.commit()
        engine.dispose()
