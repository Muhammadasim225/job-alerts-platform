"""Notification outbox: from a user's alerts to email digests and Web Push.

    alerts (pending) --dispatch()--> deliveries (one per user per channel) --notifier--> sent

dispatch()
    Batches each user's pending alerts into one notification per channel, so a morning
    run with 6 matches is one email and one push, not 12 messages. A user's batch is
    taken once it has settled (no new alert for SETTLE), or after MAX_WAIT at the
    latest, while the daily run is still producing alerts. The alerts become "sent":
    they are in the user's inbox on the website even with every channel switched off.

take_due() / claim_delivery() / mark_delivery_*()
    The notifier enqueues due deliveries and sends each one. claim_delivery moves a row
    to "sending" under SELECT ... FOR UPDATE SKIP LOCKED, so however many notifier
    processes run (and however often a message is redelivered) a notification goes
    out once. Failures are retried with backoff; a crashed sender's claim expires after
    STALE_AFTER. Retry state lives in Postgres, not in the broker, so it survives
    restarts.
"""

from collections import defaultdict
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.orm import Session

from shared.models import Alert, AuthSession, Delivery, PushSubscription, User

CHANNELS = ("email", "push")

SETTLE = timedelta(minutes=10)
MAX_WAIT = timedelta(minutes=60)
STALE_AFTER = timedelta(minutes=10)
# A delivery handed to the broker is not handed out again for this long (lost message)
REQUEUE_AFTER = timedelta(minutes=15)
MAX_ATTEMPTS = 5
BACKOFF = (timedelta(minutes=1), timedelta(minutes=5), timedelta(minutes=30), timedelta(hours=2))
DELIVERY_RETENTION = timedelta(days=90)


def _now() -> datetime:
    return datetime.now(UTC)


def channels_for(user: User, has_push_subscription: bool) -> list[str]:
    channels = []
    if user.email_alerts and user.email_verified_at is not None:
        channels.append("email")
    if user.push_alerts and has_push_subscription:
        channels.append("push")
    return channels


def dispatch(
    session: Session,
    now: datetime | None = None,
    settle: timedelta = SETTLE,
    max_wait: timedelta = MAX_WAIT,
    max_users: int = 500,
) -> list[int]:
    """Turn settled pending alerts into deliveries. Returns the new delivery ids."""
    now = now or _now()
    user_ids = session.scalars(
        select(Alert.user_id)
        .where(Alert.status == "pending")
        .group_by(Alert.user_id)
        .having(or_(func.max(Alert.created_at) <= now - settle, func.min(Alert.created_at) <= now - max_wait))
        .order_by(func.min(Alert.created_at))
        .limit(max_users)
    ).all()
    if not user_ids:
        return []

    alerts = session.scalars(
        select(Alert)
        .where(Alert.status == "pending", Alert.user_id.in_(user_ids))
        .order_by(Alert.user_id, Alert.created_at, Alert.id)
        .with_for_update(skip_locked=True)
    ).all()
    by_user: dict[int, list[Alert]] = defaultdict(list)
    for alert in alerts:
        by_user[alert.user_id].append(alert)

    users = {u.id: u for u in session.scalars(select(User).where(User.id.in_(by_user)))}
    with_push = set(session.scalars(select(PushSubscription.user_id).where(PushSubscription.user_id.in_(by_user)).distinct()))

    created: list[Delivery] = []
    for user_id, items in by_user.items():
        user = users[user_id]
        if not user.is_active:
            for a in items:
                a.status, a.error = "skipped", "alerts switched off"
            continue
        for a in items:
            a.status, a.sent_at = "sent", now
        ids = [a.id for a in items]
        for channel in channels_for(user, user_id in with_push):
            delivery = Delivery(user_id=user_id, channel=channel, alert_ids=ids, status="pending", next_attempt_at=now)
            session.add(delivery)
            created.append(delivery)
    session.flush()
    return [d.id for d in created]


def take_due(session: Session, now: datetime | None = None, limit: int = 1000) -> list[int]:
    """Deliveries to hand to the broker now: new ones, retries whose backoff is over,
    and ones whose sender died. Each is not handed out again for REQUEUE_AFTER."""
    now = now or _now()
    rows = session.scalars(
        select(Delivery)
        .where(
            or_(
                (Delivery.status == "pending") & (Delivery.next_attempt_at <= now),
                (Delivery.status == "sending") & (Delivery.claimed_at < now - STALE_AFTER),
            )
        )
        .order_by(Delivery.next_attempt_at, Delivery.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for d in rows:
        d.status, d.claimed_at, d.next_attempt_at = "pending", None, now + REQUEUE_AFTER
    session.flush()
    return [d.id for d in rows]


def claim_delivery(session: Session, delivery_id: int, now: datetime | None = None) -> Delivery | None:
    """Take one delivery for sending, or None if it is already sent, being sent by
    another process, or gone. Commit right after so the claim is visible."""
    delivery = session.scalar(
        select(Delivery).where(Delivery.id == delivery_id, Delivery.status == "pending").with_for_update(skip_locked=True)
    )
    if delivery is None:
        return None
    delivery.status, delivery.claimed_at = "sending", now or _now()
    delivery.attempts = (delivery.attempts or 0) + 1
    session.flush()
    return delivery


def _locked(session: Session, delivery_id: int) -> Delivery:
    delivery = session.get(Delivery, delivery_id, with_for_update=True)
    if delivery is None:
        raise LookupError(f"delivery {delivery_id} not found")
    return delivery


def mark_delivery_sent(session: Session, delivery_id: int, now: datetime | None = None) -> Delivery:
    d = _locked(session, delivery_id)
    d.status, d.sent_at, d.error, d.claimed_at = "sent", now or _now(), None, None
    session.flush()
    return d


def mark_delivery_skipped(session: Session, delivery_id: int, reason: str) -> Delivery:
    """Not sent on purpose (channel switched off meanwhile, no device left)."""
    d = _locked(session, delivery_id)
    d.status, d.error, d.claimed_at = "skipped", reason[:1000], None
    session.flush()
    return d


def mark_delivery_failed(
    session: Session, delivery_id: int, error: str, permanent: bool = False, now: datetime | None = None
) -> Delivery:
    """Retry after a backoff, unless the error is permanent (invalid address) or the
    attempts are used up."""
    d = _locked(session, delivery_id)
    d.error, d.claimed_at = error[:1000], None
    if permanent or d.attempts >= MAX_ATTEMPTS:
        d.status = "failed"
    else:
        d.status = "pending"
        d.next_attempt_at = (now or _now()) + BACKOFF[min(d.attempts, len(BACKOFF)) - 1]
    session.flush()
    return d


def defer_delivery(session: Session, delivery_id: int, until: datetime, reason: str) -> Delivery:
    """Nothing could even try to send it (e.g. every email provider is full for today):
    retry at `until` without using up an attempt."""
    d = _locked(session, delivery_id)
    d.status, d.claimed_at, d.error, d.next_attempt_at = "pending", None, reason[:1000], until
    d.attempts = max((d.attempts or 1) - 1, 0)
    session.flush()
    return d


def skip_pending(session: Session, user_id: int, reason: str, channel: str | None = None) -> None:
    """The user switched alerts (or one channel) off: nothing queued goes out any more.
    With no channel, pending alerts are skipped too."""
    q = update(Delivery).where(Delivery.user_id == user_id, Delivery.status == "pending")
    if channel:
        q = q.where(Delivery.channel == channel)
    session.execute(q.values(status="skipped", error=reason))
    if channel is None:
        session.execute(
            update(Alert).where(Alert.user_id == user_id, Alert.status == "pending").values(status="skipped", error=reason)
        )
    session.flush()


def cleanup(session: Session, now: datetime | None = None) -> dict[str, int]:
    """Daily: drop expired login sessions and finished deliveries past retention."""
    now = now or _now()
    sessions = session.execute(delete(AuthSession).where(AuthSession.expires_at < now))
    deliveries = session.execute(
        delete(Delivery).where(Delivery.status.in_(("sent", "failed", "skipped")), Delivery.created_at < now - DELIVERY_RETENTION)
    )
    session.flush()
    return {"sessions": sessions.rowcount, "deliveries": deliveries.rowcount}
