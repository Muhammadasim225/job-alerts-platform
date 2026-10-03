"""The alert outbox: how a sender (the Telegram bot, later WhatsApp) takes alerts to send.

    claim_pending()  atomically hands out pending alerts: status -> "sending"
    mark_sent()      delivered
    mark_failed()    back to "pending" for a retry, or "failed" after MAX_ATTEMPTS

claim_pending uses SELECT ... FOR UPDATE SKIP LOCKED, so any number of sender
processes can poll at once and each alert goes to exactly one of them: no user ever
gets the same message twice. Alerts left in "sending" by a crashed sender are handed
out again after STALE_AFTER.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from shared.models import Alert

MAX_ATTEMPTS = 3
STALE_AFTER = timedelta(minutes=10)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def claim_pending(session: Session, limit: int = 50) -> list[Alert]:
    now = _now()
    alerts = session.scalars(
        select(Alert)
        .where(
            or_(
                Alert.status == "pending",
                (Alert.status == "sending") & (Alert.claimed_at < now - STALE_AFTER),
            )
        )
        .order_by(Alert.created_at, Alert.id)
        .limit(limit)
        .with_for_update(skip_locked=True)
    ).all()
    for alert in alerts:
        alert.status = "sending"
        alert.claimed_at = now
        alert.attempts = (alert.attempts or 0) + 1
    session.flush()
    return alerts


def _get(session: Session, alert_id: int) -> Alert:
    alert = session.get(Alert, alert_id, with_for_update=True)
    if alert is None:
        raise LookupError(f"alert {alert_id} not found")
    return alert


def mark_sent(session: Session, alert_id: int) -> Alert:
    alert = _get(session, alert_id)
    alert.status = "sent"
    alert.sent_at = _now()
    alert.error = None
    session.flush()
    return alert


def mark_failed(session: Session, alert_id: int, error: str, permanent: bool = False) -> Alert:
    """Retry later unless the error is permanent (e.g. the user blocked the bot) or
    the attempts are used up."""
    alert = _get(session, alert_id)
    alert.error = error[:1000]
    alert.claimed_at = None
    alert.status = "failed" if permanent or alert.attempts >= MAX_ATTEMPTS else "pending"
    session.flush()
    return alert
