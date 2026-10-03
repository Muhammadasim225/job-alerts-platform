"""Celery application for the scraper worker.

Worker:  uv run celery -A celery_app worker --loglevel=INFO --pool=solo   (use --pool=solo on Windows)
Beat:    uv run celery -A celery_app beat --loglevel=INFO
Flower:  uv run celery -A celery_app flower
"""

import logging

from celery import Celery

import config
from beat_schedule import BEAT_SCHEDULE

log = logging.getLogger(__name__)


def init_sentry() -> None:
    if not config.SENTRY_DSN:
        return
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(dsn=config.SENTRY_DSN, integrations=[CeleryIntegration(monitor_beat_tasks=True)], traces_sample_rate=0.0)
    log.info("Sentry enabled")


init_sentry()

app = Celery("scrapers", broker=config.CELERY_BROKER_URL, backend=config.REDIS_URL, include=["tasks"])
app.conf.update(
    timezone="Asia/Karachi",
    enable_utc=True,
    task_acks_late=True,  # a task killed mid-run is redelivered instead of lost
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_time_limit=60 * 30,
    task_soft_time_limit=60 * 25,
    result_expires=60 * 60 * 24,
    beat_schedule=BEAT_SCHEDULE,
    broker_connection_retry_on_startup=True,
)
