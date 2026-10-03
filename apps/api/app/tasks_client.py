"""Send tasks to the scraper's Celery workers without importing scraper code.

The queue definitions must match apps/scrapers/celery_app.py (one direct exchange and
routing key per queue), otherwise a message could be routed to the wrong queue.
"""

from functools import lru_cache

from celery import Celery
from kombu import Exchange, Queue

from app.config import settings

QUEUES = ("scrape", "process", "default")


@lru_cache(maxsize=1)
def _client() -> Celery:
    app = Celery("api-client", broker=settings.redis_url)
    app.conf.update(
        task_queues=[Queue(q, Exchange(q, type="direct"), routing_key=q) for q in QUEUES],
        task_ignore_result=True,
        broker_connection_retry_on_startup=True,
    )
    return app


def send_task(name: str, queue: str, kwargs: dict | None = None) -> str:
    if queue not in QUEUES:
        raise ValueError(f"unknown queue {queue}")
    result = _client().send_task(name, kwargs=kwargs or {}, queue=queue, routing_key=queue)
    return result.id
