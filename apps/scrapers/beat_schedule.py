"""Periodic schedule for Celery Beat (Asia/Karachi time).

  03:00  housekeeping        delete old run logs / scrape feeds
  06:00  nts-scrape          the daily run: scrape NTS, fan out one task per new/changed
                             listing (download, parse, store, queue alerts)
  09:00  deadline-reminders  reminders for listings closing in N days
  03:30  notify-housekeeping expired login sessions, old deliveries (notifier)
  every 2 min  notify-dispatch  batch settled alerts into email/push deliveries and
                                enqueue due ones (notifier, queue "notify")

This is the one Beat of the system: the notifier's periodic tasks are scheduled here
by name (no code import), so running several notifiers never multiplies them.

Beat keeps the last run times in data/celerybeat-schedule, so if the machine is off
at 06:00 the missed run starts as soon as Beat is back (once, not once per day missed).
"""

from datetime import timedelta

from celery.schedules import crontab

import config

HOUR = 60 * 60

BEAT_SCHEDULE = {
    "nts-scrape": {
        "task": "tasks.scrape_nts",
        "schedule": crontab(minute=config.SCRAPE_MINUTE, hour=config.SCRAPE_HOUR),
        # A daily run that cannot start within 12 h is dropped; the next day's run
        # covers it (dedup makes runs catch up on everything they missed).
        "options": {"expires": 12 * HOUR},
    },
    "deadline-reminders": {
        "task": "tasks.queue_deadline_reminders",
        "schedule": crontab(minute=0, hour=config.REMINDER_HOUR),
        "kwargs": {"days_before": config.REMINDER_DAYS_BEFORE},
        "options": {"expires": 12 * HOUR},
    },
    "notify-dispatch": {
        "task": "notify.dispatch",
        "schedule": timedelta(minutes=2),
        # A run that waited longer than its interval is dropped: the next one covers it
        "options": {"queue": "notify", "routing_key": "notify", "expires": 110},
    },
    "notify-housekeeping": {
        "task": "notify.housekeeping",
        "schedule": crontab(minute=30, hour=config.HOUSEKEEPING_HOUR),
        "options": {"queue": "notify", "routing_key": "notify", "expires": 12 * HOUR},
    },
    "housekeeping": {
        "task": "tasks.housekeeping",
        "schedule": crontab(minute=0, hour=config.HOUSEKEEPING_HOUR),
        "options": {"expires": 12 * HOUR},
    },
}
