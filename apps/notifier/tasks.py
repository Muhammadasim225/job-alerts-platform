"""Celery tasks of the notifier. The logic is in service.py."""

import logging
from functools import lru_cache

import config
import service
from celery_app import app
from channels import PermanentError, SmtpMailer, WebPusher

log = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _pusher() -> WebPusher:
    return WebPusher()


@app.task(name="notify.dispatch")
def dispatch() -> int:
    """Every 2 minutes (Beat): batch settled alerts, enqueue every due delivery."""
    ids = service.dispatch_due()
    for delivery_id in ids:
        deliver.apply_async((delivery_id,), queue="notify", routing_key="notify")
    return len(ids)


@app.task(name="notify.deliver", rate_limit=config.DELIVER_RATE_LIMIT)
def deliver(delivery_id: int) -> str:
    outcome = service.deliver(delivery_id, mailer=SmtpMailer(), pusher_factory=_pusher)
    log.info("Delivery %s: %s", delivery_id, outcome)
    return outcome


@app.task(
    name="notify.send_login_code",
    autoretry_for=(Exception,),
    dont_autoretry_for=(PermanentError,),
    retry_backoff=5,
    retry_jitter=False,
    max_retries=3,
)
def send_login_code(email: str, code: str) -> None:
    """Sign-in code from the API. Retried quickly: the user is waiting for it."""
    service.send_login_code(email, code, SmtpMailer())


@app.task(name="notify.housekeeping")
def housekeeping() -> dict:
    removed = service.housekeeping()
    log.info("Notifier housekeeping: removed %s", removed)
    return removed
