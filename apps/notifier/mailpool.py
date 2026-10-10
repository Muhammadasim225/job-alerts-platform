"""Email provider pool: several (free) SMTP providers with daily/monthly caps and failover.

Free tiers are small but add up (Oct 2026: Brevo 300/day, Mailjet 200/day and 6,000/
month, SMTP2GO 200/day and 1,000/month, Mailtrap 150/day and 4,000/month, Resend
100/day and 3,000/month: ~950 emails a day for nothing). Each provider needs our
sending domain verified (SPF include + DKIM) before it is added.

A message goes to the first provider in SMTP_PROVIDERS order with room left today and
this month. When a provider is at fault (cannot connect, login refused, its own quota
or rate limit), it is benched for a while and the next provider sends the message.
When the recipient is at fault (address refused, mailbox full), the error goes back
to the caller unchanged: another provider would not do better.

Counting: every accepted message is counted per provider per UTC day and month in
Redis. The log (and so Sentry) gets a warning once a day when today's sends pass
MAIL_ALERT_PERCENT of the pool's daily capacity, an error when no provider can send
or a provider refuses our login, and every day yesterday's totals.
"""

import logging
import os
import re
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import config
from channels import Email, PermanentError, SmtpMailer, SmtpSettings

log = logging.getLogger(__name__)

LIMIT_WORDS = re.compile(r"quota|limit|exceeded|too many|throttl|rate", re.I)
AUTH_CODES = {530, 534, 535}
CONNECTION_BENCH_S = 5 * 60
LOGIN_BENCH_S = 60 * 60
DAY_S = 24 * 3600


class PoolExhausted(Exception):
    """No provider can send right now (all full or failing). Temporary: retry at retry_at,
    when the first bench or daily count runs out."""

    def __init__(self, message: str, retry_at: datetime):
        super().__init__(message)
        self.retry_at = retry_at


@dataclass(frozen=True)
class Provider:
    name: str
    smtp: SmtpSettings
    daily_limit: int | None = None
    monthly_limit: int | None = None


def providers_from_env(env=os.environ) -> list[Provider]:
    """The pool from SMTP_PROVIDERS; without it, the single SMTP_* relay."""
    if not config.SMTP_PROVIDERS:
        return [Provider("default", SmtpSettings.from_config(), config.SMTP_DAILY_LIMIT, config.SMTP_MONTHLY_LIMIT)]
    pool = []
    for name in config.SMTP_PROVIDERS:
        p = f"SMTP_{name.upper()}_"
        if not env.get(f"{p}HOST"):
            raise RuntimeError(f"SMTP provider {name!r} is listed in SMTP_PROVIDERS but {p}HOST is not set")
        smtp = SmtpSettings(
            host=env[f"{p}HOST"],
            port=int(env.get(f"{p}PORT", "587")),
            user=env.get(f"{p}USER", ""),
            password=env.get(f"{p}PASSWORD", ""),
            security=env.get(f"{p}SECURITY", "starttls").lower(),
        )
        daily, monthly = env.get(f"{p}DAILY_LIMIT"), env.get(f"{p}MONTHLY_LIMIT")
        pool.append(Provider(name, smtp, int(daily) if daily else None, int(monthly) if monthly else None))
    return pool


def provider_fault(exc: Exception) -> tuple[str, float] | None:
    """(reason, seconds to bench) when the provider is at fault, None when the recipient
    or the message is (then no other provider would do better)."""
    e = exc.__cause__ if isinstance(exc, PermanentError) and exc.__cause__ else exc
    if isinstance(e, smtplib.SMTPRecipientsRefused):
        return None
    if isinstance(e, smtplib.SMTPAuthenticationError) or getattr(e, "smtp_code", None) in AUTH_CODES:
        return "login refused", LOGIN_BENCH_S
    if isinstance(e, smtplib.SMTPConnectError):
        return "cannot connect", CONNECTION_BENCH_S
    if isinstance(e, smtplib.SMTPResponseException):
        if e.smtp_code == 421 or LIMIT_WORDS.search(str(e.smtp_error)):
            return f"quota or rate limit ({e.smtp_code})", _seconds_to_utc_midnight()
        return None
    if isinstance(e, OSError):  # disconnects, timeouts, refused connections, TLS errors
        return f"connection failed ({type(e).__name__})", CONNECTION_BENCH_S
    return None


def _seconds_to_utc_midnight() -> float:
    now = datetime.now(UTC)
    return (datetime(now.year, now.month, now.day, tzinfo=UTC) + timedelta(days=1) - now).total_seconds()


def _redis_client():
    import redis

    return redis.Redis.from_url(config.CELERY_BROKER_URL, decode_responses=True, socket_timeout=2)


class PooledMailer:
    """Same interface as SmtpMailer: send(mail). Counters and benches live in Redis; without
    Redis the providers are simply tried in order, uncounted."""

    def __init__(
        self,
        providers: list[Provider],
        redis_client=None,
        mailer_factory: Callable[[SmtpSettings], SmtpMailer] = SmtpMailer,
    ):
        if not providers:
            raise RuntimeError("no SMTP provider configured")
        self.providers = providers
        self._redis = redis_client
        self._mailer = mailer_factory

    # --- Redis, failing soft ------------------------------------------------------

    def _r(self):
        try:
            if self._redis is None:
                self._redis = _redis_client()
            self._redis.ping()
            return self._redis
        except Exception:
            log.warning("Redis unavailable: email counters and caps are off for this message")
            return None

    @staticmethod
    def _day(offset: int = 0) -> str:
        return (datetime.now(UTC).date() + timedelta(days=offset)).isoformat()

    def _counts(self, r, p: Provider, day: str | None = None) -> tuple[int, int]:
        day = day or self._day()
        return int(r.get(f"mail:sent:{p.name}:{day}") or 0), int(r.get(f"mail:sent:{p.name}:{day[:7]}") or 0)

    def _has_room(self, r, p: Provider) -> bool:
        if r is None:
            return True
        if r.exists(f"mail:bench:{p.name}"):
            return False
        today, month = self._counts(r, p)
        return (p.daily_limit is None or today < p.daily_limit) and (p.monthly_limit is None or month < p.monthly_limit)

    def _count(self, r, p: Provider) -> None:
        day = self._day()
        for key, ttl in ((f"mail:sent:{p.name}:{day}", 3 * DAY_S), (f"mail:sent:{p.name}:{day[:7]}", 40 * DAY_S)):
            r.incr(key)
            r.expire(key, ttl)

    def _bench(self, r, p: Provider, reason: str, seconds: float) -> None:
        level = logging.ERROR if reason == "login refused" else logging.WARNING  # a refused login needs a human
        log.log(level, "Email provider %s benched for %.0f min: %s", p.name, seconds / 60, reason)
        if r is not None:
            r.set(f"mail:bench:{p.name}", reason, ex=max(60, int(seconds)))

    def _once_a_day(self, r, what: str) -> bool:
        return r is not None and bool(r.set(f"mail:alerted:{what}:{self._day()}", "1", nx=True, ex=2 * DAY_S))

    # --- reporting ----------------------------------------------------------------

    def usage(self, day: str | None = None) -> dict[str, dict]:
        """Per provider: sent that day / that month and the caps (for logs and admin pages)."""
        r = self._r()
        out = {}
        for p in self.providers:
            sent, month = self._counts(r, p, day) if r is not None else (0, 0)
            out[p.name] = {"day": sent, "month": month, "daily_limit": p.daily_limit, "monthly_limit": p.monthly_limit}
        return out

    def _daily_summary(self, r) -> None:
        yesterday = self._day(-1)
        if r is not None and r.set(f"mail:summary:{yesterday}", "1", nx=True, ex=3 * DAY_S):
            used = self.usage(yesterday)
            log.info(
                "Emails sent on %s: %d (%s)",
                yesterday,
                sum(u["day"] for u in used.values()),
                ", ".join(f"{name} {u['day']}" for name, u in used.items()),
            )

    def _check_capacity(self, r) -> None:
        if any(p.daily_limit is None for p in self.providers):
            return  # an uncapped provider: no capacity to run out of
        capacity = sum(p.daily_limit for p in self.providers)
        sent = sum(self._counts(r, p)[0] for p in self.providers)
        if sent * 100 >= capacity * config.MAIL_ALERT_PERCENT and self._once_a_day(r, "capacity"):
            log.warning(
                "Email pool at %d of %d today (%d%%): add a provider or raise a plan", sent, capacity, sent * 100 // capacity
            )

    def _next_free_at(self, r) -> datetime:
        """Earliest time a provider may have room again: its bench ends, or the UTC day
        rolls over for a full one (a month-full provider waits for the next day's check)."""
        now = datetime.now(UTC)
        waits = [_seconds_to_utc_midnight()]
        if r is not None:
            waits += [ttl for p in self.providers if (ttl := r.ttl(f"mail:bench:{p.name}")) and ttl > 0]
        return now + timedelta(seconds=max(60, min(waits)))

    # --- sending ------------------------------------------------------------------

    def send(self, mail: Email) -> str:
        """Send through the first provider with room; returns the provider's name."""
        r = self._r()
        self._daily_summary(r)
        for p in self.providers:
            if not self._has_room(r, p):
                continue
            try:
                self._mailer(p.smtp).send(mail)
            except Exception as exc:
                fault = provider_fault(exc)
                if fault is None:
                    raise  # the recipient's or the message's problem
                self._bench(r, p, *fault)
                continue
            if r is not None:
                self._count(r, p)
                self._check_capacity(r)
            return p.name
        if self._once_a_day(r, "exhausted") or r is None:
            log.error("No email provider can send (all full or failing): emails wait for a retry")
        raise PoolExhausted("no email provider can send right now", self._next_free_at(r))
