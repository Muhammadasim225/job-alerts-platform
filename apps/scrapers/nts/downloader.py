"""Download advertisement files (PDFs / images) attached to NTS listings.

Files are stored under data/raw/attachments/<listing_id>/ and never re-downloaded
when the same URL was already fetched and the file is still on disk.
"""

import hashlib
import logging
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import unquote, urlparse

import requests

import config
from nts import dedup

log = logging.getLogger(__name__)

ALLOWED_TYPES = {
    "application/pdf": ".pdf",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/tiff": ".tif",
    # NTS also attaches Word files (e.g. "Content Weightages" = test syllabus per post)
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
    "application/msword": ".doc",
}


@dataclass
class DownloadedFile:
    url: str
    path: str  # relative to DATA_DIR
    content_type: str
    sha256: str
    size: int
    reused: bool


class DownloadError(Exception):
    pass


_session: requests.Session | None = None


def _get_session() -> requests.Session:
    global _session
    if _session is None:
        _session = requests.Session()
        _session.headers.update({"User-Agent": config.USER_AGENT, "Accept": "*/*"})
    return _session


def _safe_filename(url: str, content_type: str) -> str:
    name = Path(unquote(urlparse(url).path)).name or "attachment"
    name = re.sub(r"[^A-Za-z0-9._-]+", "_", name).strip("._") or "attachment"
    stem, ext = Path(name).stem[:100], Path(name).suffix.lower()
    if not ext:
        ext = ALLOWED_TYPES.get(content_type) or mimetypes.guess_extension(content_type) or ""
    # Prefix with a URL hash so two different URLs with the same file name never collide
    return f"{hashlib.sha1(url.encode()).hexdigest()[:8]}_{stem}{ext}"


def _find_existing(folder: Path, url: str) -> Path | None:
    prefix = hashlib.sha1(url.encode()).hexdigest()[:8] + "_"
    if folder.exists():
        for p in folder.iterdir():
            if p.name.startswith(prefix):
                return p
    return None


def _meta_from_headers(headers) -> dict:
    return {
        "etag": headers.get("ETag", ""),
        "last_modified": headers.get("Last-Modified", ""),
        "length": headers.get("Content-Length", ""),
    }


def remote_file_changed(url: str) -> bool:
    """Cheap HEAD check: has the server replaced the file behind this URL since we
    downloaded it (e.g. a corrigendum uploaded under the same name)?

    Unknown or failed checks count as unchanged, so a network hiccup never makes
    every listing reprocess."""
    if not dedup.known_file_hash(url):
        return False  # never downloaded; the normal download path handles it
    known = dedup.known_file_meta(url)
    try:
        resp = _get_session().head(url, timeout=(10, 30), allow_redirects=True)
        resp.raise_for_status()
    except requests.RequestException as exc:
        log.warning("HEAD check failed for %s: %s", url, exc)
        return False
    current = _meta_from_headers(resp.headers)
    if not known:
        # Downloaded before headers were recorded: take today's as the baseline
        dedup.remember_file_meta(url, current)
        return False
    for field in ("etag", "last_modified", "length"):
        if known.get(field) and current.get(field) and known[field] != current[field]:
            log.info("Attachment changed on server (%s): %s -> %s  %s", field, known[field], current[field], url)
            return True
    return False


def listing_files_changed(listing: dict) -> list[str]:
    """URLs of this listing's attachments that were replaced on the server."""
    return [a["url"] for a in (listing.get("detail") or {}).get("attachments", []) if remote_file_changed(a["url"])]


def download_attachment(listing_id: str, url: str, retries: int = 3, use_cache: bool = True) -> DownloadedFile:
    folder = config.ATTACHMENTS_DIR / listing_id
    folder.mkdir(parents=True, exist_ok=True)

    if use_cache and remote_file_changed(url):
        use_cache = False

    if use_cache:
        existing = _find_existing(folder, url)
        known = dedup.known_file_hash(url)
        if existing and known:
            data = existing.read_bytes()
            if hashlib.sha256(data).hexdigest() == known:
                ctype = mimetypes.guess_type(existing.name)[0] or "application/octet-stream"
                return DownloadedFile(url, str(existing.relative_to(config.DATA_DIR)), ctype, known, len(data), True)

    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            with _get_session().get(url, stream=True, timeout=(15, 120)) as resp:
                resp.raise_for_status()
                ctype = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
                if ctype not in ALLOWED_TYPES:
                    guessed = mimetypes.guess_type(urlparse(url).path)[0]
                    if guessed in ALLOWED_TYPES and ctype in ("", "application/octet-stream", "binary/octet-stream"):
                        ctype = guessed
                    else:
                        raise DownloadError(f"Unexpected content type {ctype!r} for {url}")

                meta = _meta_from_headers(resp.headers)
                chunks, size = [], 0
                for chunk in resp.iter_content(64 * 1024):
                    size += len(chunk)
                    if size > config.MAX_ATTACHMENT_BYTES:
                        raise DownloadError(f"{url} is larger than {config.MAX_ATTACHMENT_BYTES} bytes")
                    chunks.append(chunk)
            data = b"".join(chunks)
            break
        except DownloadError:
            raise
        except requests.RequestException as exc:
            last_exc = exc
            log.warning("Download attempt %d/%d failed for %s: %s", attempt, retries, url, exc)
            time.sleep(2**attempt)
    else:
        raise DownloadError(f"Giving up on {url}: {last_exc}")

    sha = hashlib.sha256(data).hexdigest()
    path = folder / _safe_filename(url, ctype)
    path.write_bytes(data)
    dedup.remember_file(url, sha)
    dedup.remember_file_meta(url, meta)
    log.info("Downloaded %s (%d bytes) -> %s", url, len(data), path)
    return DownloadedFile(url, str(path.relative_to(config.DATA_DIR)), ctype, sha, len(data), False)


def download_listing_attachments(listing: dict) -> tuple[list[dict], list[dict]]:
    """Download every attachment of a listing. Returns (downloaded, errors)."""
    downloaded, errors = [], []
    for att in (listing.get("detail") or {}).get("attachments", []):
        try:
            f = download_attachment(listing["listing_id"], att["url"])
            downloaded.append({"name": att.get("name"), **asdict(f)})
            if not f.reused:
                time.sleep(config.DOWNLOAD_DELAY)
        except Exception as exc:  # one bad file should not sink the listing
            log.exception("Attachment failed for %s", att["url"])
            errors.append({"url": att["url"], "error": str(exc)})
    return downloaded, errors
