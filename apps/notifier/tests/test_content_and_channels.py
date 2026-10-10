"""Message content and transports, without a database or network."""

import json
import smtplib
from datetime import date

import pytest

import channels
import content
import vapid
from channels import Email, GoneError, PermanentError, PushTarget, SmtpMailer, WebPusher
from content import Item
from shared.models import User
from shared.security import verify


def item(title="WCLA", alert_type="new", kind="job", days_left=5, posts=("Computer Operator",), more=0):
    return Item(
        alert_type=alert_type,
        kind=kind,
        title=title,
        organization="Walled City of Lahore Authority",
        last_date=date(2026, 10, 10),
        days_left=days_left,
        posts=list(posts),
        more_posts=more,
        web_url="http://localhost:3000/listings/1",
        official_url="https://portal.nts.org.pk/Alldetail/MQ==",
    )


def test_subjects():
    assert content.digest_subject([item()]) == "New job: WCLA"
    assert content.digest_subject([item(), item("B")]) == "2 new jobs for you"
    assert content.digest_subject([item(kind="admission"), item("B", kind="test")]) == "2 new admissions for you"
    assert content.digest_subject([item(), item("B", kind="admission")]) == "2 new listings for you"
    assert content.digest_subject([item(alert_type="deadline_reminder", days_left=2)]) == "Last date in 2 days: WCLA"
    assert content.digest_subject([item(alert_type="deadline_reminder", days_left=0)]) == "Last day today: WCLA"
    assert content.digest_subject([item(alert_type="deadline_reminder")] * 3) == "3 deadlines coming up"
    assert content.digest_subject([item(), item("R", alert_type="deadline_reminder")]) == "New job: WCLA (+1 closing soon)"


def test_digest_email_escapes_and_links():
    user = User(id=42, email="ali@example.com")
    mail = content.digest_email(user, [item(title="<script>alert(1)</script> & Co", more=3)])
    assert "<script>alert" not in mail.html and "&lt;script&gt;" in mail.html
    assert "<script>alert(1)</script> & Co" in mail.text  # plain text is not HTML-escaped
    assert "and 3 more" in mail.text and "and 3 more" in mail.html
    assert "Official advert: https://portal.nts.org.pk/Alldetail/MQ==" in mail.text
    two = content.digest_email(user, [item("A"), item("B", days_left=0)]).text
    assert "MQ==\n\nB\n" in two  # a blank line between items
    assert "(last day today)" in two and "(5 days left)" in two
    unsubscribe = mail.headers["List-Unsubscribe"]
    assert unsubscribe.startswith("<http://localhost:8000/v1/email/unsubscribe?token=")
    token = unsubscribe.split("token=")[1].rstrip(">")
    assert verify(token, "unsubscribe")["uid"] == 42


def test_push_payload_is_small_and_points_to_the_right_page():
    one = content.digest_push([item()])
    assert one["url"] == "http://localhost:3000/listings/1" and "last date in 5 days" in one["body"]
    many = content.digest_push([item(title="x" * 300)] * 50)
    assert many["url"] == "http://localhost:3000/alerts" and many["count"] == 50
    assert len(json.dumps(many).encode()) < 1024  # Web Push allows ~4 KB


def test_message_headers(monkeypatch):
    monkeypatch.setattr(channels.config, "EMAIL_FROM", "LastBell <alerts@lastbell.pk>")
    mail = content.digest_email(User(id=7, email="a@example.com"), [item()])
    raw = channels.build_message(mail).as_bytes().decode()
    # Long one-click unsubscribe URL stays a plain <url> on one line (no RFC 2047 encoding)
    line = next(l for l in raw.splitlines() if l.startswith("List-Unsubscribe:"))
    assert line.startswith("List-Unsubscribe: <http://localhost:8000/v1/email/unsubscribe?token=") and line.endswith(">")
    assert "=?utf-8?" not in raw.split("\r\n\r\n")[0]  # headers

    msg = channels.build_message(Email("a@example.com", "Hi", "text", "<p>html</p>", {"X-Test": "1"}))
    assert msg["Message-ID"].endswith("@lastbell.pk>") and msg["X-Test"] == "1"
    assert [p.get_content_type() for p in msg.iter_parts()] == ["text/plain", "text/html"]


class _FakeSMTP:
    error: Exception | None = None
    sent: list = []

    def __init__(self, host, port, timeout):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def send_message(self, msg):
        if _FakeSMTP.error:
            raise _FakeSMTP.error
        _FakeSMTP.sent.append(msg)


@pytest.mark.parametrize(
    "error, expected",
    [
        (None, None),
        (smtplib.SMTPRecipientsRefused({"a@example.com": (550, b"no such user")}), PermanentError),
        (smtplib.SMTPDataError(554, b"rejected as spam"), PermanentError),
        (smtplib.SMTPDataError(552, b"mailbox full"), smtplib.SMTPDataError),  # temporary
        (smtplib.SMTPDataError(451, b"try later"), smtplib.SMTPDataError),
        (ConnectionRefusedError(), ConnectionRefusedError),
    ],
)
def test_smtp_error_classification(monkeypatch, error, expected):
    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    _FakeSMTP.error, _FakeSMTP.sent = error, []
    mail = Email("a@example.com", "s", "t", "<p>h</p>")
    if expected is None:
        SmtpMailer().send(mail)
        assert len(_FakeSMTP.sent) == 1
    else:
        with pytest.raises(expected):
            SmtpMailer().send(mail)


def test_vapid_keys_sign_and_push_errors_are_classified(monkeypatch):
    private, public = vapid.generate()
    assert len(public) == 87  # 65-byte uncompressed P-256 point, base64url
    pusher = WebPusher(private_key=private, subject="mailto:test@example.com")

    import pywebpush

    class Resp:
        def __init__(self, code):
            self.status_code, self.text = code, ""

    calls = []

    def fake_webpush(code):
        def send(**kw):
            calls.append(kw)
            if code >= 300:
                raise pywebpush.WebPushException("failed", response=Resp(code))

        return send

    target = PushTarget("https://fcm.googleapis.com/fcm/send/x", "k", "a")
    for code, expected in (
        (201, None),
        (410, GoneError),
        (404, GoneError),
        (413, PermanentError),
        (429, pywebpush.WebPushException),
    ):
        monkeypatch.setattr(pywebpush, "webpush", fake_webpush(code))
        if expected is None:
            pusher.send(target, {"title": "t"})
        else:
            with pytest.raises(expected):
                pusher.send(target, {"title": "t"})
    assert calls[0]["vapid_claims"] == {"sub": "mailto:test@example.com"} and calls[0]["ttl"] == 86400


def test_vapid_private_key_really_signs():
    private, _ = vapid.generate()
    from py_vapid import Vapid

    headers = Vapid.from_string(private).sign({"sub": "mailto:a@example.com", "aud": "https://fcm.googleapis.com"})
    assert headers["Authorization"].startswith("vapid t=")
