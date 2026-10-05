"""Transports: SMTP email and Web Push. They know nothing about alerts or the database.

Errors are classified for the retry logic:
  PermanentError  retrying cannot help (address rejected, endpoint gone, payload too big)
  GoneError       a push endpoint no longer exists: delete the subscription
  anything else   temporary (network, 5xx, rate limit): retried with backoff
"""

import json
import logging
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.policy import SMTP
from email.utils import formatdate, make_msgid, parseaddr

import config

log = logging.getLogger(__name__)

# RFC 5322 allows 998-character lines. With the default 78, a long List-Unsubscribe URL
# cannot be folded and gets RFC 2047-encoded, which mail apps then fail to recognise.
POLICY = SMTP.clone(max_line_length=998)


class PermanentError(Exception):
    pass


class GoneError(PermanentError):
    pass


@dataclass
class Email:
    to: str
    subject: str
    text: str
    html: str
    headers: dict[str, str] = field(default_factory=dict)


def build_message(mail: Email) -> EmailMessage:
    msg = EmailMessage(policy=POLICY)
    msg["From"] = config.EMAIL_FROM
    msg["To"] = mail.to
    msg["Subject"] = mail.subject
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=parseaddr(config.EMAIL_FROM)[1].rpartition("@")[2] or None)
    if config.EMAIL_REPLY_TO:
        msg["Reply-To"] = config.EMAIL_REPLY_TO
    for name, value in mail.headers.items():
        msg[name] = value
    msg.set_content(mail.text)
    msg.add_alternative(mail.html, subtype="html")
    return msg


class SmtpMailer:
    def send(self, mail: Email) -> None:
        msg = build_message(mail)
        try:
            if config.SMTP_SECURITY == "ssl":
                server = smtplib.SMTP_SSL(
                    config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT, context=ssl.create_default_context()
                )
            else:
                server = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=config.SMTP_TIMEOUT)
            with server:
                if config.SMTP_SECURITY == "starttls":
                    server.starttls(context=ssl.create_default_context())
                if config.SMTP_USER:
                    server.login(config.SMTP_USER, config.SMTP_PASSWORD)
                server.send_message(msg)
        except smtplib.SMTPRecipientsRefused as exc:
            raise PermanentError(f"recipient refused: {exc.recipients}") from exc
        except smtplib.SMTPResponseException as exc:
            if 500 <= exc.smtp_code < 600 and exc.smtp_code != 552:  # 5xx = permanent (552: mailbox full, retry)
                raise PermanentError(f"SMTP {exc.smtp_code} {exc.smtp_error!r}") from exc
            raise


@dataclass
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


class WebPusher:
    def __init__(self, private_key: str | None = None, subject: str | None = None):
        from py_vapid import Vapid

        key = private_key if private_key is not None else config.VAPID_PRIVATE_KEY
        if not key:
            raise RuntimeError("VAPID_PRIVATE_KEY is not set")
        self._vapid = Vapid.from_string(key)  # parsed once, not per message
        self._subject = subject or config.VAPID_SUBJECT

    def send(self, target: PushTarget, payload: dict) -> None:
        from pywebpush import WebPushException, webpush

        try:
            webpush(
                subscription_info={"endpoint": target.endpoint, "keys": {"p256dh": target.p256dh, "auth": target.auth}},
                data=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                vapid_private_key=self._vapid,
                vapid_claims={"sub": self._subject},
                ttl=config.PUSH_TTL_SECONDS,
                timeout=config.PUSH_TIMEOUT,
                headers={"Urgency": "normal"},
            )
        except WebPushException as exc:
            code = getattr(exc.response, "status_code", None)
            if code in (404, 410):
                raise GoneError(f"push endpoint gone ({code})") from exc
            if code in (400, 413):
                raise PermanentError(f"push rejected ({code}): {exc.message[:200]}") from exc
            raise
