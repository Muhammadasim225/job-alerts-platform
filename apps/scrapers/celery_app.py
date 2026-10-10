"""Celery application for the scraper worker.

Queues
  scrape    tasks.scrape_nts           light, one at a time (Redis lock)
  process   tasks.process_nts_listing  heavy: download + OCR + store, runs in parallel
  default   reminders, housekeeping    small and quick, never stuck behind OCR
  notify    (declared only)            consumed by apps/notifier; Beat schedules into it

Worker:  celery -A celery_app worker -Q scrape,process,default --concurrency=4
         (on Windows without Docker add --pool=solo)
Beat:    celery -A celery_app beat
To scale OCR, run more workers on the "process" queue (another container or machine
pointed at the same Redis) — nothing else needs to change.
"""

import logging
import os

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger
from kombu import Exchange, Queue

import config
from beat_schedule import BEAT_SCHEDULE
from shared.redact import install_redaction, sentry_before_send

log = logging.getLogger(__name__)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _mask_secrets_in_logs(logger, *args, **kwargs):
    install_redaction(logger)


def init_sentry() -> None:
    if not config.SENTRY_DSN:
        return
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=config.SENTRY_DSN,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        # monitor_beat_tasks: each Beat schedule becomes a Sentry cron monitor, so a daily
        # run that did not happen (machine off, worker stuck) raises an alert, not silence
        integrations=[CeleryIntegration(monitor_beat_tasks=True)],
        traces_sample_rate=0.0,
        send_default_pii=False,
        before_send=sentry_before_send,
    )
    log.info("Sentry enabled")


init_sentry()

QUEUES = ("scrape", "process", "default", "notify")
TASK_TIME_LIMIT = 60 * 30  # hard kill: one listing (OCR of several pages) never needs 30 min
TASK_SOFT_TIME_LIMIT = 60 * 25

app = Celery("scrapers", broker=config.CELERY_BROKER_URL, include=["tasks"])
app.conf.update(
    timezone="Asia/Karachi",
    enable_utc=True,
    # Reliability: a task killed mid-run (crash, deploy, OOM) is redelivered, not lost.
    # Every task is idempotent (dedup fingerprints, claims, unique alerts), so a
    # redelivery can never double-process or double-alert.
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # long tasks: take one at a time, leave the rest to free workers
    task_time_limit=TASK_TIME_LIMIT,
    task_soft_time_limit=TASK_SOFT_TIME_LIMIT,
    # With acks_late on Redis, an unacked task is redelivered after the visibility
    # timeout; it must exceed the longest task or long tasks would run twice.
    broker_transport_options={"visibility_timeout": 2 * TASK_TIME_LIMIT},
    broker_connection_retry_on_startup=True,
    # Results are not needed (runs are logged to data/runs and the DB); keep Redis lean.
    task_ignore_result=True,
    # OCR / PIL leak memory over time: recycle worker processes regularly.
    worker_max_tasks_per_child=20,
    worker_max_memory_per_child=600_000,  # KiB
    # Each queue has its own exchange and routing key. With one shared key, a direct
    # exchange delivers every message to every queue bound to it, i.e. each task would
    # run once per queue.
    task_queues=[Queue(name, Exchange(name, type="direct"), routing_key=name) for name in QUEUES],
    task_default_queue="default",
    task_default_exchange="default",
    task_default_routing_key="default",
    task_routes={
        "tasks.scrape_nts": {"queue": "scrape", "routing_key": "scrape"},
        "tasks.process_nts_listing": {"queue": "process", "routing_key": "process"},
    },
    beat_schedule=BEAT_SCHEDULE,
    # Task events for Flower (live task view); cheap at our volume
    worker_send_task_events=True,
    task_send_sent_event=True,
)
