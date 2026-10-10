"""Celery application for the notifier (queue "notify").

Worker:  celery -A celery_app worker -Q notify --pool=threads --concurrency=8
         Sending is network-bound (SMTP, push services), so threads are enough and light.
To send faster, run more notifier containers: claims in Postgres keep every
notification single-sent whatever the number of workers.

The periodic tasks (notify.dispatch every 2 minutes, notify.housekeeping daily) are
scheduled by the one system Beat (apps/scrapers/beat_schedule.py), never by a notifier,
so scaling notifiers never multiplies the schedule.
"""

import logging
import os

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from kombu import Exchange, Queue

import config
from shared.redact import install_redaction, sentry_before_send

log = logging.getLogger(__name__)


def _scrub(event, hint):
    """Task arguments can be an email address and a sign-in code: never send them."""
    job = (event.get("extra") or {}).get("celery-job")
    if isinstance(job, dict):
        job["args"], job["kwargs"] = "[scrubbed]", "[scrubbed]"
    return sentry_before_send(event, hint)


def init_sentry() -> None:
    if not config.SENTRY_DSN:
        return
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        integrations=[CeleryIntegration()],
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=_scrub,
    )


init_sentry()


@after_setup_logger.connect
@after_setup_task_logger.connect
def _mask_secrets_in_logs(logger, *args, **kwargs):
    install_redaction(logger)


app = Celery("notifier", broker=config.CELERY_BROKER_URL, include=["tasks"])
app.conf.update(
    timezone="Asia/Karachi",
    enable_utc=True,
    # Delivery state lives in Postgres (claims, retries, stale-claim recovery), so a lost
    # broker message is re-enqueued by the next dispatch run: early acks are safe here.
    task_acks_late=False,
    worker_prefetch_multiplier=4,
    broker_connection_retry_on_startup=True,
    task_ignore_result=True,
    task_queues=[Queue("notify", Exchange("notify", type="direct"), routing_key="notify")],
    task_default_queue="notify",
    task_default_exchange="notify",
    task_default_routing_key="notify",
    worker_send_task_events=True,
    task_send_sent_event=True,
)
