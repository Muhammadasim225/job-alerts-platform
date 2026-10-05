"""Notifier settings from the environment (repo-root .env via docker compose)."""

import os

DATABASE_URL = os.getenv("DATABASE_URL", "")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL") or os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Email (SMTP). Locally: Mailpit (catches everything, UI on http://localhost:8025).
# Production: any provider's SMTP relay (Brevo, Resend, Amazon SES, ...); only .env changes.
SMTP_HOST = os.getenv("SMTP_HOST", "localhost")
SMTP_PORT = int(os.getenv("SMTP_PORT", "1025"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_SECURITY = os.getenv("SMTP_SECURITY", "none").lower()  # none | starttls | ssl
SMTP_TIMEOUT = float(os.getenv("SMTP_TIMEOUT", "20"))
EMAIL_FROM = os.getenv("EMAIL_FROM", "SarkariAlert <no-reply@sarkarialert.local>")
EMAIL_REPLY_TO = os.getenv("EMAIL_REPLY_TO", "")

# Web Push (VAPID). Generate a pair once with: python vapid.py
VAPID_PRIVATE_KEY = os.getenv("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.getenv("VAPID_SUBJECT", "mailto:admin@sarkarialert.local")
PUSH_TTL_SECONDS = int(os.getenv("PUSH_TTL_SECONDS", str(24 * 3600)))  # undelivered pushes expire after a day
PUSH_TIMEOUT = float(os.getenv("PUSH_TIMEOUT", "10"))

# Links in messages
WEB_BASE_URL = os.getenv("WEB_BASE_URL", "http://localhost:3000").rstrip("/")
API_PUBLIC_URL = os.getenv("API_PUBLIC_URL", "http://localhost:8000").rstrip("/")
UNSUBSCRIBE_LINK_DAYS = 90

# Per-worker-process sending rate for the deliver task (Celery syntax, e.g. "20/s");
# keep under the email provider's limit. Empty = no limit.
DELIVER_RATE_LIMIT = os.getenv("DELIVER_RATE_LIMIT", "") or None

SENTRY_DSN = os.getenv("SENTRY_DSN", "")
