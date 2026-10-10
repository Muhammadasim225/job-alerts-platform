"""Email provider pool: caps, failover, counting and alerts (fake SMTP, fake Redis)."""

import logging
import smtplib

import fakeredis
import mailpool
import pytest
from mailpool import PooledMailer, PoolExhausted, Provider, provider_fault, providers_from_env

import config
from channels import Email, PermanentError, SmtpSettings

MAIL = Email("a@example.com", "s", "t", "<p>h</p>")


def provider(name, daily=None, monthly=None):
    return Provider(name, SmtpSettings(f"smtp.{name}.test", 587, "u", "pw-secret"), daily, monthly)


class FakeMailers:
    """mailer_factory: `errors` maps a host to the exception its sends raise."""

    def __init__(self, errors=None):
        self.errors, self.sent = errors or {}, []

    def __call__(self, settings):
        test = self

        class Mailer:
            def send(self, mail):
                if settings.host in test.errors:
                    raise test.errors[settings.host]
                test.sent.append(settings.host)

        return Mailer()


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def pool(r, providers, errors=None):
    mailers = FakeMailers(errors)
    return PooledMailer(providers, redis_client=r, mailer_factory=mailers), mailers


def test_first_provider_until_its_daily_cap_then_the_next(r):
    mailer, sent = pool(r, [provider("brevo", daily=2), provider("mailjet", daily=5)])
    assert [mailer.send(MAIL) for _ in range(3)] == ["brevo", "brevo", "mailjet"]
    assert mailer.usage()["brevo"]["day"] == 2 and mailer.usage()["mailjet"]["month"] == 1


def test_monthly_cap_counts_too(r):
    mailer, _ = pool(r, [provider("resend", daily=100, monthly=1), provider("smtp2go")])
    assert [mailer.send(MAIL) for _ in range(2)] == ["resend", "smtp2go"]


def test_failing_provider_is_benched_and_the_message_still_goes_out(r):
    mailer, mailers = pool(r, [provider("brevo"), provider("mailjet")], {"smtp.brevo.test": ConnectionRefusedError()})
    assert mailer.send(MAIL) == "mailjet"
    del mailers.errors["smtp.brevo.test"]
    assert mailer.send(MAIL) == "mailjet"  # still benched for a few minutes
    assert 0 < r.ttl("mail:bench:brevo") <= mailpool.CONNECTION_BENCH_S


def test_provider_quota_reply_benches_until_tomorrow(r):
    quota = PermanentError("SMTP 550")
    quota.__cause__ = smtplib.SMTPDataError(550, b"Daily sending quota exceeded")
    mailer, _ = pool(r, [provider("brevo"), provider("mailjet")], {"smtp.brevo.test": quota})
    assert mailer.send(MAIL) == "mailjet"
    assert r.get("mail:bench:brevo").startswith("quota") and r.ttl("mail:bench:brevo") >= 60


def test_recipient_errors_go_back_without_trying_other_providers(r):
    refused = PermanentError("recipient refused")
    refused.__cause__ = smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")})
    mailer, mailers = pool(r, [provider("brevo"), provider("mailjet")], {"smtp.brevo.test": refused})
    with pytest.raises(PermanentError):
        mailer.send(MAIL)
    assert mailers.sent == [] and not r.exists("mail:bench:brevo")


@pytest.mark.parametrize(
    "exc, at_fault",
    [
        (smtplib.SMTPAuthenticationError(535, b"bad credentials"), "login refused"),
        (smtplib.SMTPConnectError(421, b"busy"), "cannot connect"),
        (smtplib.SMTPServerDisconnected("gone"), "connection failed"),
        (TimeoutError(), "connection failed"),
        (smtplib.SMTPDataError(421, b"try later"), "quota or rate limit"),
        (smtplib.SMTPDataError(451, b"Rate limit reached"), "quota or rate limit"),
        (smtplib.SMTPDataError(552, b"mailbox full"), None),
        (smtplib.SMTPDataError(554, b"rejected as spam"), None),
    ],
)
def test_provider_fault_classification(exc, at_fault):
    fault = provider_fault(exc)
    assert (fault[0].split(" (")[0] if fault else None) == at_fault


def test_all_full_raises_with_a_retry_time_and_alerts_once(r, caplog):
    caplog.set_level(logging.WARNING)
    mailer, _ = pool(r, [provider("brevo", daily=1)])
    mailer.send(MAIL)
    for _ in range(2):
        with pytest.raises(PoolExhausted) as info:
            mailer.send(MAIL)
    assert info.value.retry_at > mailpool.datetime.now(mailpool.UTC)
    assert len([x for x in caplog.records if x.levelno == logging.ERROR]) == 1


def test_capacity_warning_once_a_day(r, caplog, monkeypatch):
    caplog.set_level(logging.WARNING)
    monkeypatch.setattr(config, "MAIL_ALERT_PERCENT", 50)
    mailer, _ = pool(r, [provider("brevo", daily=2), provider("mailjet", daily=2)])
    for _ in range(3):
        mailer.send(MAIL)
    warnings = [x.getMessage() for x in caplog.records if "Email pool at" in x.getMessage()]
    assert warnings == ["Email pool at 2 of 4 today (50%): add a provider or raise a plan"]


def test_daily_summary_of_yesterday(r, caplog):
    caplog.set_level(logging.INFO)
    mailer, _ = pool(r, [provider("brevo")])
    r.set(f"mail:sent:brevo:{mailer._day(-1)}", 7)
    mailer.send(MAIL)
    mailer.send(MAIL)
    summaries = [x.getMessage() for x in caplog.records if x.getMessage().startswith("Emails sent on")]
    assert summaries == [f"Emails sent on {mailer._day(-1)}: 7 (brevo 7)"]


def test_without_redis_providers_are_tried_in_order():
    class Down:
        def ping(self):
            raise ConnectionError("down")

    mailer, _ = pool(Down(), [provider("brevo", daily=1)])
    assert [mailer.send(MAIL) for _ in range(2)] == ["brevo", "brevo"]  # uncounted, never blocked


def test_providers_from_env(monkeypatch):
    monkeypatch.setattr(config, "SMTP_PROVIDERS", ["brevo", "mailjet"])
    env = {
        "SMTP_BREVO_HOST": "smtp-relay.brevo.com",
        "SMTP_BREVO_USER": "me",
        "SMTP_BREVO_PASSWORD": "pw-secret",
        "SMTP_BREVO_DAILY_LIMIT": "290",
        "SMTP_MAILJET_HOST": "in-v3.mailjet.com",
        "SMTP_MAILJET_DAILY_LIMIT": "190",
        "SMTP_MAILJET_MONTHLY_LIMIT": "5800",
    }
    brevo, mailjet = providers_from_env(env)
    assert (brevo.smtp.port, brevo.smtp.security, brevo.daily_limit, brevo.monthly_limit) == (587, "starttls", 290, None)
    assert mailjet.monthly_limit == 5800
    assert "pw-secret" not in repr(brevo)
    monkeypatch.setattr(config, "SMTP_PROVIDERS", ["nohost"])
    with pytest.raises(RuntimeError, match="SMTP_NOHOST_HOST"):
        providers_from_env(env)


def test_single_relay_without_a_pool(monkeypatch):
    monkeypatch.setattr(config, "SMTP_PROVIDERS", [])
    (only,) = providers_from_env({})
    assert only.name == "default" and only.smtp.host == config.SMTP_HOST
