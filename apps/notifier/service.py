"""Delivery logic, independent of Celery (tasks.py only wires it to queues).

deliver() keeps database transactions short: claim and read in one, send outside any
transaction (SMTP / push can take seconds), record the outcome in another. A claim is
committed before the network call, so a second process never sends the same delivery.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, datetime

from mailpool import PoolExhausted
from sqlalchemy import delete, update

import config
from channels import Email, GoneError, PermanentError, PushTarget
from content import digest_email, digest_push, load_items, login_email
from shared import notifications
from shared.db import session_scope
from shared.models import PushSubscription, User

log = logging.getLogger(__name__)

DISPATCH_MAX_USERS = 1000


def _db():
    return session_scope(config.DATABASE_URL or None)


def dispatch_due(now: datetime | None = None) -> list[int]:
    """Batch settled alerts into deliveries, then return every delivery due now."""
    with _db() as s:
        created = notifications.dispatch(s, now=now, max_users=DISPATCH_MAX_USERS)
        if created:
            log.info("Dispatched %d new deliveries", len(created))
    with _db() as s:
        return notifications.take_due(s, now=now)


@dataclass
class _Job:
    delivery_id: int
    channel: str
    email: Email | None = None
    payload: dict | None = None
    targets: list[PushTarget] | None = None


def _prepare(delivery_id: int) -> _Job | str:
    """Claim the delivery and build the message, or return why there is nothing to send."""
    with _db() as s:
        d = notifications.claim_delivery(s, delivery_id)
        if d is None:
            return "not claimable (already sent, being sent, or gone)"
        user = s.get(User, d.user_id)
        reason = None
        if not user.is_active:
            reason = "alerts switched off"
        elif d.channel == "email" and not (user.email_alerts and user.email_verified_at):
            reason = "email alerts switched off"
        elif d.channel == "push" and not user.push_alerts:
            reason = "push alerts switched off"
        items = [] if reason else load_items(s, d.alert_ids)
        if not reason and not items:
            reason = "listings no longer exist"
        if d.channel == "push" and not reason:
            targets = [PushTarget(p.endpoint, p.p256dh, p.auth) for p in user.push_subscriptions]
            if not targets:
                reason = "no push device"
        if reason:
            notifications.mark_delivery_skipped(s, d.id, reason)
            return f"skipped: {reason}"
        if d.channel == "email":
            return _Job(d.id, "email", email=digest_email(user, items))
        return _Job(d.id, "push", payload=digest_push(items), targets=targets)


def _send_push(job: _Job, pusher) -> tuple[list[str], list[str]]:
    """Send to every device. Returns (delivered endpoints, gone endpoints); raises the
    last temporary error if no device got it and some may on retry."""
    delivered, gone, temporary = [], [], None
    for target in job.targets:
        try:
            pusher.send(target, job.payload)
            delivered.append(target.endpoint)
        except GoneError:
            gone.append(target.endpoint)
        except PermanentError as exc:
            log.warning("Push to a device of delivery %s rejected: %s", job.delivery_id, exc)
        except Exception as exc:  # network, 5xx, 429: maybe next time
            temporary = exc
    if not delivered and temporary is not None:
        with _db() as s:  # clean up even when retrying
            _forget_endpoints(s, gone)
        raise temporary
    return delivered, gone


def _forget_endpoints(s, endpoints: list[str]) -> None:
    if endpoints:
        s.execute(delete(PushSubscription).where(PushSubscription.endpoint.in_(endpoints)))
        log.info("Removed %d expired push subscription(s)", len(endpoints))


def deliver(delivery_id: int, mailer, pusher_factory) -> str:
    """Send one delivery. Returns a short outcome for logs; never raises for a send error
    (the outcome is recorded on the delivery and retried from Postgres)."""
    job = _prepare(delivery_id)
    if isinstance(job, str):
        return job
    try:
        if job.channel == "email":
            mailer.send(job.email)
            delivered, gone = [], []
        else:
            delivered, gone = _send_push(job, pusher_factory())
    except PoolExhausted as exc:
        with _db() as s:
            notifications.defer_delivery(s, job.delivery_id, exc.retry_at, str(exc))
        return f"deferred: {exc}"
    except PermanentError as exc:
        with _db() as s:
            notifications.mark_delivery_failed(s, job.delivery_id, str(exc), permanent=True)
        log.warning("Delivery %s failed permanently: %s", job.delivery_id, exc)
        return f"failed: {exc}"
    except Exception as exc:
        with _db() as s:
            d = notifications.mark_delivery_failed(s, job.delivery_id, f"{type(exc).__name__}: {exc}")
            status = d.status
        log.warning("Delivery %s failed (%s), status now %s", job.delivery_id, exc, status)
        return f"error: {exc}"

    with _db() as s:
        _forget_endpoints(s, gone)
        if job.channel == "push" and not delivered:
            notifications.mark_delivery_skipped(s, job.delivery_id, "no reachable push device")
            return "skipped: no reachable push device"
        if delivered:
            s.execute(
                update(PushSubscription).where(PushSubscription.endpoint.in_(delivered)).values(last_success_at=datetime.now(UTC))
            )
        notifications.mark_delivery_sent(s, job.delivery_id)
    return "sent"


def send_login_code(email: str, code: str, mailer) -> None:
    mailer.send(login_email(email, code))


def housekeeping() -> dict[str, int]:
    with _db() as s:
        return notifications.cleanup(s)
