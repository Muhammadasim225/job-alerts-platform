"""Runtime settings, read from environment variables (see .env at repo root)."""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
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
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0 Safari/537.36",
)

# Seconds between requests to the same site
DOWNLOAD_DELAY = float(os.getenv("SCRAPER_DOWNLOAD_DELAY", "2"))
MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(40 * 1024 * 1024)))

# Path to tesseract.exe on Windows if it is not on PATH
TESSERACT_CMD = os.getenv("TESSERACT_CMD")
OCR_LANGS = os.getenv("OCR_LANGS", "eng")
# A PDF page with fewer extracted characters than this is treated as scanned and OCR'd
MIN_TEXT_CHARS_PER_PAGE = int(os.getenv("MIN_TEXT_CHARS_PER_PAGE", "80"))

SCRAPE_INTERVAL_HOURS = int(os.getenv("NTS_SCRAPE_INTERVAL_HOURS", "3"))

# Optional vision-language OCR (deAPI, Nanonets-OCR-s) for stylized image adverts and
# scanned pages. Off unless an API key is set; Tesseract is used otherwise / on failure.
DEAPI_API_KEY = os.getenv("DEAPI_API_KEY")
DEAPI_BASE_URL = os.getenv("DEAPI_BASE_URL", "https://api.deapi.ai")
DEAPI_OCR_MODEL = os.getenv("DEAPI_OCR_MODEL", "Nanonets_Ocr_S_F16")
VLM_MAX_CALLS_PER_DAY = int(os.getenv("VLM_MAX_CALLS_PER_DAY", "200"))  # one call per strip
VLM_CACHE_DIR = DATA_DIR / "vlm_cache"

SENTRY_DSN = os.getenv("SENTRY_DSN")
