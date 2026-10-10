import logging

import pytest

from shared import redact as r

SECRET = "sk-live-abcdef123456"
KEY_A, KEY_B = "deapi-key-aaaa1111", "deapi-key-bbbb2222"


@pytest.fixture(autouse=True)
def secret_env(monkeypatch):
    monkeypatch.setenv("APP_SECRET", SECRET)
    monkeypatch.setenv("DEAPI_API_KEYS", f"{KEY_A},{KEY_B}")
    monkeypatch.setenv("POSTGRES_PORT_HINT", "55432")  # not a secret name: left alone
    monkeypatch.setenv("SHORT_TOKEN", "abc")  # too short to mask safely
    r.refresh()
    yield
    r.refresh()


def test_masks_env_secrets_and_each_listed_key():
    text = f"secret={SECRET} keys={KEY_A},{KEY_B} one={KEY_B} port=55432 abc"
    assert r.redact(text) == "secret=*** keys=*** one=*** port=55432 abc"


def test_masks_url_passwords_and_bearer_tokens():
    assert r.redact("postgresql://postgres:hunter2@db:5432/jobalert") == "postgresql://postgres:***@db:5432/jobalert"
    assert r.redact("Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.x.y") == "Authorization: Bearer ***"


def test_log_lines_and_tracebacks_are_masked():
    logger = logging.getLogger("test.redact")
    stream_records: list[str] = []

    class ListHandler(logging.Handler):
        def emit(self, record):
            stream_records.append(self.format(record))

    handler = ListHandler()
    logger.handlers[:] = [handler]
    logger.propagate = False
    r.install_redaction(logger)
    r.install_redaction(logger)  # idempotent: not wrapped twice
    try:
        raise RuntimeError(f"provider rejected key {KEY_A}")
    except RuntimeError:
        logger.exception("send failed with %s", SECRET)
    assert SECRET not in stream_records[0] and KEY_A not in stream_records[0]
    assert "send failed with ***" in stream_records[0] and "rejected key ***" in stream_records[0]
    assert not isinstance(handler.formatter.inner, r.RedactingFormatter)


def test_sentry_event_is_scrubbed():
    event = {
        "message": f"boom {SECRET}",
        "extra": {"smtp_password": "plain-but-named-secret", "url": "redis://:pw12345678@redis:6379/0"},
        "breadcrumbs": [{"message": KEY_B}],
    }
    out = r.sentry_before_send(event, None)
    assert out["message"] == "boom ***"
    assert out["extra"]["smtp_password"] == "***"
    assert out["extra"]["url"] == "redis://:***@redis:6379/0"
    assert out["breadcrumbs"][0]["message"] == "***"
