"""Helpers shared by the NTS spider, downloader and normalizer."""

import base64
import binascii
import hashlib
import json
import re
from urllib.parse import unquote, urlparse

SOURCE = "nts"

# https://portal.nts.org.pk/Alldetail/MTAxMzM0  -> id is base64("101334")
_PORTAL_RE = re.compile(r"portal\.nts\.org\.pk/Alldetail/([A-Za-z0-9+/=_-]+)", re.I)
# https://nts.org.pk/Test&Products/Announced/06_26/ISMO_June2026_Online/ISMO.php
_LEGACY_RE = re.compile(r"/Test&Products/(?:Announced|Lists)/([^/]+)/([^/]+)/", re.I)


def clean_text(value: str | None) -> str:
    """Collapse whitespace and &nbsp; into single spaces."""
    if not value:
        return ""
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def listing_id_from_url(url: str) -> str:
    """Stable ID for a listing, derived from its detail URL.

    Portal listings use the numeric project ID NTS encodes in the URL; old-style
    "Announced" pages use their folder name. Anything else falls back to a URL hash.
    """
    m = _PORTAL_RE.search(url)
    if m:
        token = m.group(1)
        try:
            decoded = base64.b64decode(token + "=" * (-len(token) % 4)).decode()
            if decoded.isdigit():
                return f"portal-{decoded}"
        except (binascii.Error, UnicodeDecodeError):
            pass
        return f"portal-{token}"

    m = _LEGACY_RE.search(unquote(url))
    if m:
        return f"legacy-{m.group(1)}-{m.group(2)}"

    return "url-" + hashlib.sha1(url.encode()).hexdigest()[:12]


def detail_kind(url: str) -> str:
    host = urlparse(url).netloc.lower()
    if host.startswith("portal."):
        return "portal"
    return "legacy"


def fingerprint(data: dict) -> str:
    """Hash of the fields that matter for change detection (not scrape timestamps)."""
    payload = json.dumps(data, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()
