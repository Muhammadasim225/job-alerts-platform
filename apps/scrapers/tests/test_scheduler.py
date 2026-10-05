"""Schedule, routing and reliability settings of the Celery app."""

import os
import time

import config
from beat_schedule import BEAT_SCHEDULE
from celery_app import TASK_TIME_LIMIT, app

DAILY = {name: e for name, e in BEAT_SCHEDULE.items() if name != "notify-dispatch"}


def test_scrape_runs_once_a_day_at_six():
    s = BEAT_SCHEDULE["nts-scrape"]["schedule"]
    assert s.hour == {6} and s.minute == {0}
    assert BEAT_SCHEDULE["nts-scrape"]["task"] == "tasks.scrape_nts"


def test_daily_order_housekeeping_scrape_reminders():
    hours = {name: next(iter(e["schedule"].hour)) for name, e in DAILY.items()}
    assert hours["housekeeping"] < hours["nts-scrape"] < hours["deadline-reminders"]


def test_missed_run_is_not_expired_too_soon():
    # Beat re-sends a missed daily run when it comes back; a short expiry would drop it
    assert all(e["options"]["expires"] >= 6 * 3600 for e in DAILY.values())


def test_notifier_dispatch_runs_often_and_never_piles_up():
    e = BEAT_SCHEDULE["notify-dispatch"]
    interval = e["schedule"].total_seconds()
    assert e["task"] == "notify.dispatch" and interval <= 300
    assert e["options"]["queue"] == "notify" and e["options"]["expires"] < interval
    assert BEAT_SCHEDULE["notify-housekeeping"]["options"]["queue"] == "notify"


def test_heavy_and_light_work_use_separate_queues():
    routes = app.conf.task_routes
    assert routes["tasks.scrape_nts"]["queue"] == "scrape"
    assert routes["tasks.process_nts_listing"]["queue"] == "process"
    assert app.conf.task_default_queue == "default"  # reminders, housekeeping


def test_redelivery_cannot_duplicate_long_tasks():
    assert app.conf.task_acks_late and app.conf.worker_prefetch_multiplier == 1
    assert app.conf.broker_transport_options["visibility_timeout"] > TASK_TIME_LIMIT
    assert app.conf.task_soft_time_limit < app.conf.task_time_limit


def test_registered_tasks():
    import tasks  # noqa: F401  (registers the tasks)

    names = set(app.tasks)
    assert {"tasks.scrape_nts", "tasks.process_nts_listing", "tasks.queue_deadline_reminders", "tasks.housekeeping"} <= names


def test_cleanup_old_runs_keeps_recent_and_latest(tmp_path, monkeypatch):
    from tasks import cleanup_old_runs

    monkeypatch.setattr(config, "RUNS_DIR", tmp_path)
    old = time.time() - 40 * 86400
    for i in range(8):
        p = tmp_path / f"2026080{i}T000000Z.json"
        p.write_text("{}")
        os.utime(p, (old + i, old + i))
    fresh = tmp_path / "20261003T000000Z.json"
    fresh.write_text("{}")

    deleted = cleanup_old_runs(retention_days=30, keep_latest=3)
    remaining = sorted(p.name for p in tmp_path.iterdir())
    assert deleted == 6  # 9 files, newest 3 always kept, the other 6 are older than 30 days
    assert fresh.name in remaining and len(remaining) == 3


def test_each_queue_has_its_own_routing_key():
    keys = {q.name: (q.exchange.name, q.routing_key) for q in app.conf.task_queues}
    assert keys == {q: (q, q) for q in ("scrape", "process", "default", "notify")}
    assert len(set(keys.values())) == 4  # no message can fan out to several queues
