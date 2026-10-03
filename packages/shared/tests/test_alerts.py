"""Alert outbox: exactly-once hand-out to concurrent senders, retries, stale claims."""

from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from shared import alerts
from shared.models import Alert, Listing, Preference, User


def _seed(session, n=3):
    listing = Listing(source="nts", external_id="x-1", url="u", status="open", kind="job", title="t")
    users = [User(telegram_chat_id=5000 + i, preference=Preference()) for i in range(n)]
    session.add_all([listing, *users])
    session.flush()
    session.add_all([Alert(user_id=u.id, listing_id=listing.id, alert_type="new") for u in users])
    session.flush()


def test_claim_send_fail_cycle(session):
    _seed(session, 3)
    claimed = alerts.claim_pending(session, limit=2)
    assert len(claimed) == 2 and all(a.status == "sending" and a.attempts == 1 for a in claimed)
    assert len(alerts.claim_pending(session, limit=10)) == 1  # only the unclaimed one is left

    alerts.mark_sent(session, claimed[0].id)
    retry = alerts.mark_failed(session, claimed[1].id, "timeout")
    assert retry.status == "pending"  # will be retried
    blocked = alerts.mark_failed(session, alerts.claim_pending(session)[0].id, "bot blocked", permanent=True)
    assert blocked.status == "failed"


def test_gives_up_after_max_attempts(session):
    _seed(session, 1)
    for _ in range(alerts.MAX_ATTEMPTS):
        a = alerts.claim_pending(session)[0]
        a = alerts.mark_failed(session, a.id, "network")
    assert a.status == "failed" and a.attempts == alerts.MAX_ATTEMPTS
    assert alerts.claim_pending(session) == []


def test_stale_claims_are_handed_out_again(session):
    _seed(session, 1)
    a = alerts.claim_pending(session)[0]
    a.claimed_at = datetime.now(timezone.utc) - timedelta(minutes=30)  # the sender crashed
    session.flush()
    again = alerts.claim_pending(session)
    assert [x.id for x in again] == [a.id] and again[0].attempts == 2


def test_two_concurrent_senders_never_get_the_same_alert(db_url):
    """Real concurrency: two connections claim at the same time (SKIP LOCKED)."""
    engine = create_engine(db_url)
    with Session(engine) as setup:
        _seed(setup, 4)
        setup.commit()
    s1, s2 = Session(engine), Session(engine)
    try:
        first = alerts.claim_pending(s1, limit=3)  # s1's transaction still open: rows locked
        second = alerts.claim_pending(s2, limit=3)
        ids1, ids2 = {a.id for a in first}, {a.id for a in second}
        assert len(ids1) == 3 and len(ids2) == 1 and not ids1 & ids2
    finally:
        s1.rollback(), s2.rollback()
        s1.close(), s2.close()
        with Session(engine) as cleanup:
            cleanup.query(Alert).delete()
            cleanup.query(User).filter(User.telegram_chat_id >= 5000).delete()
            cleanup.query(Listing).filter(Listing.external_id == "x-1").delete()
            cleanup.commit()
        engine.dispose()
