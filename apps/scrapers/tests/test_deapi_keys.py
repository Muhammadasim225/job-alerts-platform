"""deAPI key pool: rotation, daily caps, per-minute pacing, benching (fake Redis/HTTP)."""

import logging

import fakeredis
import pytest

import config
from nts import deapi_keys, dedup, vlm


class Resp:
    def __init__(self, body, status=200, headers=None):
        self._body, self.status_code, self.text, self.headers = body, status, str(body), headers or {}

    def json(self):
        return self._body


DAILY_429 = Resp({}, 429, {"X-RateLimit-Type": "daily", "X-RateLimit-Daily-Remaining": "0"})


class AccountSession:
    """deAPI per account: `refuse` maps a key to the response its submits get."""

    def __init__(self, refuse=None):
        self.refuse = refuse or {}
        self.used = []  # (method, key) per request

    def _key(self, kw):
        return kw["headers"]["Authorization"].removeprefix("Bearer ")

    def post(self, url, **kw):
        key = self._key(kw)
        self.used.append(("post", key))
        return self.refuse.get(key) or Resp({"data": {"request_id": f"job-{key}"}})

    def get(self, url, **kw):
        key = self._key(kw)
        self.used.append(("get", key))
        assert url.endswith(f"job-{key}"), "a job must be polled with the key that started it"
        return Resp({"data": {"status": "done", "result": f"read by {key}"}})


@pytest.fixture
def redis(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(dedup, "get_redis", lambda: r)
    monkeypatch.setattr(config, "DEAPI_API_KEYS", ["key-one-secret", "key-two-secret"])
    monkeypatch.setattr(config, "DEAPI_KEY_DAILY_LIMIT", 45)
    monkeypatch.setattr(config, "DEAPI_KEY_PER_MINUTE", 100)
    monkeypatch.setattr(vlm.time, "sleep", lambda s: None)
    return r


def ocr(session):
    return vlm._wait(*vlm._submit(b"jpeg", session), session)


def test_first_key_is_used_until_its_day_is_spent(redis):
    session = AccountSession(refuse={"key-one-secret": DAILY_429})
    assert ocr(session) == "read by key-two-secret"
    assert session.used == [("post", "key-one-secret"), ("post", "key-two-secret"), ("get", "key-two-secret")]
    # key one is benched: the next job goes straight to key two
    session.used.clear()
    ocr(session)
    assert session.used[0] == ("post", "key-two-secret")


def test_refused_key_is_benched_and_skipped(redis):
    session = AccountSession(refuse={"key-one-secret": Resp({"error": "no credit"}, 402)})
    assert ocr(session) == "read by key-two-secret"
    assert deapi_keys.available().secret == "key-two-secret"


def test_our_daily_cap_moves_to_the_next_key_before_deapi_blocks(redis, monkeypatch):
    monkeypatch.setattr(config, "DEAPI_KEY_DAILY_LIMIT", 2)  # one job = submit + one poll here
    session = AccountSession()
    assert ocr(session) == "read by key-one-secret"
    assert ocr(session) == "read by key-two-secret"
    assert deapi_keys.available() is None and deapi_keys.paused_until() is not None
    with pytest.raises(vlm.QuotaExhausted):
        vlm._submit(b"jpeg", session)


def test_polls_of_a_started_job_are_never_refused_by_our_cap(redis, monkeypatch):
    monkeypatch.setattr(config, "DEAPI_KEY_DAILY_LIMIT", 1)
    key = deapi_keys.keys()[0]
    deapi_keys.spend(key, new_job=True)
    deapi_keys.spend(key, new_job=False)  # over the cap, but finishing a paid job
    with pytest.raises(deapi_keys.KeyExhausted):
        deapi_keys.spend(key, new_job=True)


def test_all_keys_spent_alerts_once(redis, caplog):
    caplog.set_level(logging.WARNING)
    for key in deapi_keys.keys():
        deapi_keys.bench(key, vlm.time.time() + 3600, "test")
    deapi_keys.bench(deapi_keys.keys()[0], vlm.time.time() + 3600, "again")
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert len(errors) == 1 and "All 2 deAPI keys" in errors[0].getMessage()


def test_per_minute_pacing_waits_instead_of_hitting_429(redis, monkeypatch):
    monkeypatch.setattr(config, "DEAPI_KEY_PER_MINUTE", 2)
    waits = []
    key = deapi_keys.keys()[0]
    for _ in range(3):
        deapi_keys.spend(key, new_job=False, sleep=waits.append)
    assert len(waits) >= 1 and all(0 < w <= 61 for w in waits)


def test_new_jobs_prefer_a_key_with_room_this_minute(redis, monkeypatch):
    monkeypatch.setattr(config, "DEAPI_KEY_PER_MINUTE", 1)
    one, two = deapi_keys.keys()
    deapi_keys.spend(one, new_job=True)
    assert deapi_keys.available() == two


def test_secrets_never_reach_logs_or_redis(redis, caplog):
    caplog.set_level(logging.INFO)
    session = AccountSession(refuse={"key-one-secret": DAILY_429})
    ocr(session)
    assert "secret" not in repr(deapi_keys.keys()[0])
    assert not any("secret" in k for k in redis.keys("*"))
    assert not any("secret" in r.getMessage() for r in caplog.records)


def test_old_single_key_and_duplicates(monkeypatch):
    monkeypatch.setattr(config, "DEAPI_API_KEYS", ["a-key", "a-key", "b-key"])
    assert [k.secret for k in deapi_keys.keys()] == ["a-key", "b-key"]


def test_without_redis_the_first_key_is_used(monkeypatch):
    def down():
        raise ConnectionError("redis down")

    monkeypatch.setattr(dedup, "get_redis", down)
    monkeypatch.setattr(config, "DEAPI_API_KEYS", ["a-key", "b-key"])
    key = deapi_keys.available()
    assert key.secret == "a-key"
    deapi_keys.spend(key, new_job=True)  # no counters, no error
    assert deapi_keys.paused_until() is None
