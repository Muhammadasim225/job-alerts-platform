"""deAPI keys: a pool of accounts with a daily cap and per-minute pacing per key.

DEAPI_API_KEYS="k1,k2,k3" in .env. Keys are used in order: a new OCR job goes to the
first key with room today, so a second key is touched only when the first one's day
is spent. A key is benched (skipped until its reset) when

  - our own daily cap is reached (DEAPI_KEY_DAILY_LIMIT, a little below deAPI's own
    quota, so we never run into its hard block),
  - deAPI answers 429 "daily" (benched until the reset time it sends), or
  - deAPI refuses the key (401/402/403: revoked, out of credit): benched for a day.

Requests are paced per key (DEAPI_KEY_PER_MINUTE): over the limit, the call waits for
the next minute instead of collecting 429s. The daily cap only gates new jobs; status
polls of a started job are counted but never refused, so a paid job can finish.

Counters live in Redis under a short hash of the key: the key itself is never stored
or logged. When every key is spent, one error per day goes to the log and Sentry and
the parser reads with Tesseract until a key resets.
"""

import hashlib
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import config

log = logging.getLogger(__name__)

DAY_S = 24 * 3600
MINUTE_WAITS = 3


class KeyExhausted(RuntimeError):
    """This key cannot be used until its reset; the next key may still work."""


@dataclass(frozen=True)
class Key:
    id: str  # short hash of the secret: safe for logs and Redis key names
    secret: str = field(repr=False)


def keys() -> list[Key]:
    return [Key(hashlib.sha256(s.encode()).hexdigest()[:10], s) for s in dict.fromkeys(config.DEAPI_API_KEYS)]


def _redis():
    from nts.dedup import get_redis

    try:
        r = get_redis()
        r.ping()
        return r
    except Exception:
        log.warning("Redis unavailable for deAPI key counters; using keys without caps")
        return None


def _day_key(key: Key) -> str:
    return f"deapi:key:{key.id}:day:{datetime.now(UTC).date().isoformat()}"


def _minute_key(key: Key) -> str:
    return f"deapi:key:{key.id}:min:{int(time.time() // 60)}"


def _bench_key(key: Key) -> str:
    return f"deapi:key:{key.id}:benched_until"


def _next_utc_midnight() -> float:
    tomorrow = datetime.now(UTC).date() + timedelta(days=1)
    return datetime(tomorrow.year, tomorrow.month, tomorrow.day, tzinfo=UTC).timestamp()


def _benched_until(r, key: Key) -> float | None:
    value = r.get(_bench_key(key))
    return float(value) if value and float(value) > time.time() else None


def _usable(r, key: Key) -> bool:
    return not _benched_until(r, key) and int(r.get(_day_key(key)) or 0) < config.DEAPI_KEY_DAILY_LIMIT


def available(exclude: set[str] | frozenset[str] = frozenset()) -> Key | None:
    """The key for a new job: the first usable one, preferring one with room this
    minute. None when every key is spent for today."""
    candidates = [k for k in keys() if k.id not in exclude]
    r = _redis()
    if r is None:
        return candidates[0] if candidates else None
    usable = [k for k in candidates if _usable(r, k)]
    free_now = [k for k in usable if int(r.get(_minute_key(k)) or 0) < config.DEAPI_KEY_PER_MINUTE]
    return (free_now or usable or [None])[0]


def paused_until() -> float | None:
    """When every key is spent: the earliest time one comes back. Else None."""
    pool = keys()
    r = _redis()
    if not pool or r is None or any(_usable(r, k) for k in pool):
        return None
    return min(_benched_until(r, k) or _next_utc_midnight() for k in pool)


def spend(key: Key, *, new_job: bool, sleep=time.sleep) -> None:
    """Count one request against the key. Waits for the next minute when the key's
    per-minute share is used. For a new job, raises KeyExhausted when the key's daily
    cap is reached (and benches it)."""
    r = _redis()
    if r is None:  # no counters: deAPI's own 429s still protect us
        return
    day_key = _day_key(key)
    used = r.incr(day_key)
    r.expire(day_key, 2 * DAY_S)
    if new_job and used > config.DEAPI_KEY_DAILY_LIMIT:
        bench(key, _next_utc_midnight(), f"daily cap of {config.DEAPI_KEY_DAILY_LIMIT} requests reached")
        raise KeyExhausted(f"deAPI key {key.id}: daily cap reached")
    for _ in range(MINUTE_WAITS):
        minute_key = _minute_key(key)
        n = r.incr(minute_key)
        r.expire(minute_key, 120)
        if n <= config.DEAPI_KEY_PER_MINUTE:
            return
        wait = 60 - time.time() % 60 + 0.5
        log.info("deAPI key %s: %d requests this minute, waiting %.0fs", key.id, n - 1, wait)
        sleep(wait)


def bench(key: Key, until: float, reason: str) -> None:
    """Skip this key until `until` (epoch seconds)."""
    log.warning(
        "deAPI key %s benched until %s UTC: %s",
        key.id,
        datetime.fromtimestamp(until, UTC).strftime("%Y-%m-%d %H:%M"),
        reason,
    )
    r = _redis()
    if r is None:
        return
    r.set(_bench_key(key), str(until), ex=max(60, int(until - time.time())))
    if paused_until() is not None and r.set(f"deapi:all_spent:{datetime.now(UTC).date()}", "1", nx=True, ex=DAY_S):
        log.error("All %d deAPI keys are used up for today: OCR falls back to Tesseract until a key resets", len(keys()))
