"""Runtime settings, read from environment variables (see .env at repo root)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Postgres (shared schema in packages/shared). When unset, records are only written as JSON.
DATABASE_URL = os.getenv("DATABASE_URL")
CELERY_BROKER_URL = os.getenv("CELERY_BROKER_URL", REDIS_URL)

# Everything the pipeline writes (raw snapshots, attachments, parsed text, records, run logs)
DATA_DIR = Path(os.getenv("DATA_DIR", BASE_DIR / "data")).resolve()
RAW_HTML_DIR = DATA_DIR / "raw" / "html"
ATTACHMENTS_DIR = DATA_DIR / "raw" / "attachments"
PARSED_DIR = DATA_DIR / "parsed"
NORMALIZED_DIR = DATA_DIR / "normalized"
RUNS_DIR = DATA_DIR / "runs"

NTS_LISTING_URL = os.getenv("NTS_LISTING_URL", "https://www.nts.org.pk/new/projectsnew.php")

USER_AGENT = os.getenv(
    "SCRAPER_USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
)

# Seconds between requests to the same site
DOWNLOAD_DELAY = float(os.getenv("SCRAPER_DOWNLOAD_DELAY", "2"))
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(40 * 1024 * 1024)))

# Path to tesseract.exe on Windows if it is not on PATH
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
OCR_LANGS = os.getenv("OCR_LANGS", "eng")
# A PDF page with fewer extracted characters than this is treated as scanned and OCR'd
MIN_TEXT_CHARS_PER_PAGE = int(os.getenv("MIN_TEXT_CHARS_PER_PAGE", "80"))

# Daily schedule (Asia/Karachi). One full run a day: scrape -> process -> store -> queue alerts.
SCRAPE_HOUR = int(os.getenv("NTS_SCRAPE_HOUR", "6"))
SCRAPE_MINUTE = int(os.getenv("NTS_SCRAPE_MINUTE", "0"))
REMINDER_HOUR = int(os.getenv("REMINDER_HOUR", "9"))  # after the scrape has finished
REMINDER_DAYS_BEFORE = int(os.getenv("REMINDER_DAYS_BEFORE", "2"))
HOUSEKEEPING_HOUR = int(os.getenv("HOUSEKEEPING_HOUR", "3"))
RETENTION_DAYS = int(os.getenv("RUN_LOG_RETENTION_DAYS", "30"))

# Optional vision-language OCR (deAPI, Nanonets-OCR-s) for stylized image adverts and
# scanned pages. Off unless a key is set; Tesseract is used otherwise / on failure.
# DEAPI_API_KEYS: several accounts' keys, comma-separated, used in order (the next one
# when a key's day is spent). The older single DEAPI_API_KEY still works.
DEAPI_API_KEYS = [k.strip() for k in (os.getenv("DEAPI_API_KEYS") or os.getenv("DEAPI_API_KEY") or "").split(",") if k.strip()]
DEAPI_KEY_DAILY_LIMIT = int(os.getenv("DEAPI_KEY_DAILY_LIMIT", "45"))  # requests/key/UTC day (free tier: 50)
DEAPI_KEY_PER_MINUTE = int(os.getenv("DEAPI_KEY_PER_MINUTE", "5"))  # requests/key/minute (free tier: 5)
DEAPI_BASE_URL = os.getenv("DEAPI_BASE_URL", "https://api.deapi.ai")
DEAPI_OCR_MODEL = os.getenv("DEAPI_OCR_MODEL", "Nanonets_Ocr_S_F16")
VLM_MAX_CALLS_PER_DAY = int(os.getenv("VLM_MAX_CALLS_PER_DAY", "200"))  # one call per strip
VLM_CACHE_DIR = DATA_DIR / "vlm_cache"

SENTRY_DSN = os.getenv("SENTRY_DSN")

# Website revalidation webhook (Next.js POST /api/revalidate); empty = skipped (dev)
WEB_REVALIDATE_URL = os.getenv("WEB_REVALIDATE_URL", "")
WEB_REVALIDATE_SECRET = os.getenv("WEB_REVALIDATE_SECRET", "")
# Healthchecks.io ping URLs, one per scheduled job; empty = no ping
HEALTHCHECK_URL_SCRAPE = os.getenv("HEALTHCHECK_URL_SCRAPE", "")
HEALTHCHECK_URL_OUTBOX = os.getenv("HEALTHCHECK_URL_OUTBOX", "")
HEALTHCHECK_URL_REMINDERS = os.getenv("HEALTHCHECK_URL_REMINDERS", "")
