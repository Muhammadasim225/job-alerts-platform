"""Keep secrets out of logs and Sentry.

Masks, in every formatted log line (tracebacks included) and in Sentry events:
  - the values of environment variables whose names look secret (KEY, SECRET,
    PASSWORD, TOKEN, DSN, AUTH), e.g. DEAPI_API_KEY, SMTP_PASSWORD, APP_SECRET;
  - passwords inside URLs (postgresql://user:***@host/db);
  - bearer tokens.

Use install_redaction(logger) after logging is configured, and
sentry_before_send as Sentry's before_send hook.
"""

import logging
import os
import re
from functools import lru_cache

MASK = "***"
_SECRET_NAME = re.compile(r"KEY|SECRET|PASSWORD|PASSWD|TOKEN|DSN|AUTH", re.I)
_URL_CREDENTIALS = re.compile(r"(\b[a-z][a-z0-9+.-]*://[^:/\s@]*:)([^@\s/]+)(@)", re.I)
_BEARER = re.compile(r"(\bBearer\s+)[A-Za-z0-9._~+/=-]{8,}", re.I)
_MIN_SECRET_LEN = 8  # shorter values ("true", "5432") would mask ordinary words


@lru_cache(maxsize=1)
def _secret_values() -> tuple[str, ...]:
    values = set()
    for name, value in os.environ.items():
        if _SECRET_NAME.search(name) and value and len(value) >= _MIN_SECRET_LEN:
            values.add(value)
            # comma-separated key lists (DEAPI_API_KEYS=a,b,c): mask each key too
            values.update(v.strip() for v in value.split(",") if len(v.strip()) >= _MIN_SECRET_LEN)
    return tuple(sorted(values, key=len, reverse=True))  # longest first: no partial leftovers


def refresh() -> None:
    """Re-read the environment (tests, or after secrets are loaded late)."""
    _secret_values.cache_clear()


def redact(text: str) -> str:
    if not text:
        return text
    for value in _secret_values():
        if value in text:
            text = text.replace(value, MASK)
    text = _URL_CREDENTIALS.sub(rf"\1{MASK}\3", text)
    return _BEARER.sub(rf"\1{MASK}", text)


class RedactingFormatter(logging.Formatter):
    """Wraps another formatter and masks secrets in its output."""

    def __init__(self, inner: logging.Formatter | None = None):
        super().__init__()
        self.inner = inner or logging.Formatter()

    def format(self, record: logging.LogRecord) -> str:
        return redact(self.inner.format(record))


def install_redaction(logger: logging.Logger | None = None) -> None:
    """Wrap the formatter of every handler on the logger (default: root). Idempotent."""
    for handler in (logger or logging.getLogger()).handlers:
        if not isinstance(handler.formatter, RedactingFormatter):
            handler.setFormatter(RedactingFormatter(handler.formatter))


def _scrub(value):
    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: (MASK if isinstance(k, str) and _SECRET_NAME.search(k) else _scrub(v)) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub(v) for v in value)
    return value


def sentry_before_send(event, hint):  # noqa: ARG001 - Sentry's hook signature
    """Sentry before_send hook: mask secrets anywhere in the event."""
    return _scrub(event)
