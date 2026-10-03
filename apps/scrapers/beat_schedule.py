"""Periodic schedule for Celery Beat."""

from celery.schedules import crontab

import config

BEAT_SCHEDULE = {
    # Every N hours on the hour (Asia/Karachi), e.g. 00:00, 03:00, 06:00 ...
    "nts-scrape": {
        "task": "tasks.scrape_nts",
        "schedule": crontab(minute=0, hour=f"*/{config.SCRAPE_INTERVAL_HOURS}"),
        "options": {"expires": 60 * 60},  # skip a run that sat in the queue for an hour
    },
}
