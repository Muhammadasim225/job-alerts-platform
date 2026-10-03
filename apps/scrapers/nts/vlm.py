"""Vision-language OCR through deAPI (model Nanonets-OCR-s) for designed adverts.

Typed PDFs and Word files are read for free (pdfplumber / XML). This is only for
images and scanned PDF pages, where Tesseract struggles with stylized banners: a
VLM reads coloured badges, multi-column layouts and tables, and returns tables as
HTML/Markdown that can be parsed structurally.

  POST {base}/api/v2/images/ocr      multipart: image, model, format=text
                                     -> {"data": {"request_id": "..."}}
  GET  {base}/api/v2/jobs/{id}       -> {"data": {"status": "pending|processing|done|error",
                                                  "result": "...", "result_url": "..."}}

Cost control: results are cached by image hash (a file is never paid for twice),
and a daily call budget (VLM_MAX_CALLS_PER_DAY) is enforced in Redis.
"""

import hashlib
import io
import logging
import time
from datetime import date

import requests

import config

log = logging.getLogger(__name__)

MAX_UPLOAD_BYTES = 9_500_000  # API limit is 10 MB
POLL_SECONDS = 3.0
TIMEOUT_SECONDS = 180


class VlmError(RuntimeError):
    pass


class InputTooLarge(VlmError):
    """The model refused the image as too large. This depends on how much text the
    image holds, not only its size. deAPI refunds failed jobs."""


def vlm_available() -> bool:
    return bool(config.DEAPI_API_KEY)


def _cache_path(digest: str):
    return config.VLM_CACHE_DIR / f"{digest}.txt"


MAX_SIDE = 4096  # model limit (min side 128)


def _encode(image) -> bytes:
    """PIL image -> JPEG bytes within the model's size limits and the upload limit."""
    from PIL import Image

    img = image.convert("RGB")
    if max(img.size) > MAX_SIDE:
        scale = MAX_SIDE / max(img.size)
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    for quality in (92, 85, 75):
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality)
        if buf.tell() <= MAX_UPLOAD_BYTES:
            return buf.getvalue()
    scale = (MAX_UPLOAD_BYTES / buf.tell()) ** 0.5
    img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


def _take_budget() -> bool:
    """Count one call against today's budget; False when the budget is spent."""
    from nts.dedup import get_redis

    key = f"nts:vlm:calls:{date.today().isoformat()}"
    try:
        r = get_redis()
        n = r.incr(key)
        r.expire(key, 60 * 60 * 48)
    except Exception:
        log.warning("Redis unavailable for VLM budget; allowing the call", exc_info=True)
        return True
    if n > config.VLM_MAX_CALLS_PER_DAY:
        log.warning("VLM daily budget (%d) spent; falling back to Tesseract", config.VLM_MAX_CALLS_PER_DAY)
        return False
    return True


def _headers() -> dict:
    return {"Authorization": f"Bearer {config.DEAPI_API_KEY}", "Accept": "application/json"}


RATE_LIMIT_RETRIES = 3
PAUSE_KEY = "nts:vlm:paused_until"


class QuotaExhausted(VlmError):
    """deAPI's daily request quota is used up; VLM is paused until it resets."""


def paused_until() -> float | None:
    """Epoch seconds until which deAPI is known to refuse us (daily quota), else None."""
    from nts.dedup import get_redis

    try:
        value = get_redis().get(PAUSE_KEY)
    except Exception:
        return None
    if value and float(value) > time.time():
        return float(value)
    return None


def _pause(until: float) -> None:
    from nts.dedup import get_redis

    try:
        get_redis().set(PAUSE_KEY, str(until), ex=max(60, int(until - time.time())))
    except Exception:
        log.warning("Could not store the VLM pause in Redis", exc_info=True)


def _rate_limited(call):
    """Run an HTTP call and handle 429s by their kind (see X-RateLimit-* headers):

    - daily quota spent (free tier: 50/day): pause VLM until the daily reset and fail
      at once, so every remaining image goes straight to Tesseract instead of waiting
      (that waiting once made a single listing take 20 minutes)
    - per-minute limit (5/min): wait for the window to reset, a few times at most
    """
    for attempt in range(RATE_LIMIT_RETRIES):
        resp = call()
        if resp.status_code != 429:
            return resp
        headers = getattr(resp, "headers", {}) or {}
        if headers.get("X-RateLimit-Daily-Remaining") == "0" or headers.get("X-RateLimit-Type") == "daily":
            try:
                reset = float(headers.get("X-RateLimit-Daily-Reset"))
            except (TypeError, ValueError):
                reset = time.time() + 6 * 3600
            _pause(reset)
            raise QuotaExhausted(
                f"deAPI daily quota used up (limit {headers.get('X-RateLimit-Daily-Limit')}); "
                f"VLM paused until {time.strftime('%Y-%m-%d %H:%M', time.localtime(reset))}"
            )
        wait = headers.get("Retry-After") or headers.get("X-RateLimit-Reset")
        try:
            wait = float(wait)
            if wait > 1e9:  # an epoch timestamp, not seconds
                wait -= time.time()
        except (TypeError, ValueError):
            wait = 15 * (attempt + 1)
        wait = min(max(wait, 2), 65)
        log.info("deAPI per-minute limit hit; waiting %.0fs", wait)
        time.sleep(wait)
    return resp


def _submit(data: bytes, session) -> str:
    resp = _rate_limited(
        lambda: session.post(
            f"{config.DEAPI_BASE_URL}/api/v2/images/ocr",
            headers=_headers(),
            files={"image": ("advert.jpg", data, "image/jpeg")},
            data={"model": config.DEAPI_OCR_MODEL, "format": "text", "return_result_in_response": "true"},
            timeout=(15, 60),
        )
    )
    if resp.status_code >= 400:
        raise VlmError(f"deAPI OCR submit failed: HTTP {resp.status_code} {resp.text[:300]}")
    body = resp.json()
    request_id = (body.get("data") or {}).get("request_id") or body.get("request_id")
    if not request_id:
        raise VlmError(f"deAPI OCR submit returned no request_id: {str(body)[:300]}")
    return request_id


def _poll_delays():
    """Seconds between status checks: a job takes ~5-20 s, and every check counts
    against the API's request limits (5/min, 50/day on the free tier), so start
    late and back off instead of polling every few seconds."""
    yield 8
    delay = 6.0
    while True:
        yield delay
        delay = min(delay * 1.5, 30)


def _wait(request_id: str, session) -> str:
    deadline = time.monotonic() + TIMEOUT_SECONDS
    delays = _poll_delays()
    time.sleep(next(delays) if POLL_SECONDS else 0)
    while time.monotonic() < deadline:
        resp = _rate_limited(
            lambda: session.get(f"{config.DEAPI_BASE_URL}/api/v2/jobs/{request_id}", headers=_headers(), timeout=(10, 30))
        )
        if resp.status_code >= 400:
            raise VlmError(f"deAPI job status failed: HTTP {resp.status_code} {resp.text[:300]}")
        data = resp.json().get("data") or {}
        status = data.get("status")
        if status == "done":
            if data.get("result"):
                return data["result"]
            if data.get("result_url"):
                return session.get(data["result_url"], timeout=(10, 60)).text
            raise VlmError("deAPI job done but returned no result")
        if status == "error":
            reason = data.get("error_reason") or data.get("error_code") or "unknown"
            if reason == "INPUT_TOO_LARGE":
                raise InputTooLarge(f"deAPI job {request_id}: {reason}")
            raise VlmError(f"deAPI job {request_id} failed: {reason}")
        time.sleep(next(delays) if POLL_SECONDS else 0)
    raise VlmError(f"deAPI job {request_id} timed out after {TIMEOUT_SECONDS}s")


# Measured against the API (Oct 2026): any image taller than ~850 px fails with
# INPUT_TOO_LARGE regardless of width (2000x700 works, 600x900 does not), so tall
# adverts are read in horizontal strips.
MAX_STRIP_HEIGHT = 800
MIN_STRIP_HEIGHT = 450
MAX_WIDTH = 2000


def split_strips(image) -> list:
    """Cut a tall image into strips no taller than MAX_STRIP_HEIGHT, cutting on the
    emptiest row near each boundary so no text line is sliced in half."""
    from PIL import Image

    img = image.convert("RGB")
    if img.width > MAX_WIDTH:
        scale = MAX_WIDTH / img.width
        img = img.resize((MAX_WIDTH, int(img.height * scale)), Image.LANCZOS)
    if img.height <= MAX_STRIP_HEIGHT:
        return [img]

    gray = img.convert("L")
    px = gray.load()
    xs = range(0, gray.width, 4)

    def ink(y: int) -> int:
        # count "non-background" pixels against the row's own median brightness,
        # so cuts work on dark or coloured backgrounds too
        row = sorted(px[x, y] for x in xs)
        bg = row[len(row) // 2]
        return sum(abs(px[x, y] - bg) > 40 for x in xs)

    strips, top = [], 0
    while img.height - top > MAX_STRIP_HEIGHT:
        lo, hi = top + MIN_STRIP_HEIGHT, top + MAX_STRIP_HEIGHT
        cut = min(range(lo, hi, 2), key=ink)
        strips.append(img.crop((0, top, img.width, cut)))
        top = cut
    strips.append(img.crop((0, top, img.width, img.height)))
    return strips


def ocr_image(image, session=None) -> str:
    """Text (Markdown, with tables as HTML/Markdown) of a PIL image via deAPI.
    Tall images are read strip by strip and the texts joined."""
    if not vlm_available():
        raise VlmError("DEAPI_API_KEY is not set")
    strips = split_strips(image)
    session = session or requests.Session()
    return "\n".join(_ocr_adaptive(strip, session) for strip in strips)


MIN_SPLIT_HEIGHT = 120


def _ocr_adaptive(image, session, depth: int = 0) -> str:
    """OCR a strip; if the model says it is too large (too much text in it), cut it
    in half on the emptiest row near the middle and read the halves."""
    try:
        return _ocr_one(image, session)
    except InputTooLarge:
        if image.height < 2 * MIN_SPLIT_HEIGHT or depth >= 4:
            raise
        top, bottom = _halve(image)
        log.info("VLM: strip %sx%s too large, splitting", image.width, image.height)
        return _ocr_adaptive(top, session, depth + 1) + "\n" + _ocr_adaptive(bottom, session, depth + 1)


def _halve(image):
    gray = image.convert("L")
    px = gray.load()
    xs = range(0, gray.width, 4)

    def ink(y: int) -> int:
        row = sorted(px[x, y] for x in xs)
        bg = row[len(row) // 2]
        return sum(abs(px[x, y] - bg) > 40 for x in xs)

    mid = image.height // 2
    span = image.height // 4
    cut = min(range(mid - span, mid + span), key=lambda y: (ink(y), abs(y - mid)))
    return image.crop((0, 0, image.width, cut)), image.crop((0, cut, image.width, image.height))


def _ocr_one(image, session) -> str:
    data = _encode(image)
    digest = hashlib.sha256(data).hexdigest()
    cached = _cache_path(digest)
    if cached.exists():
        return cached.read_text(encoding="utf8")
    until = paused_until()
    if until:
        raise QuotaExhausted(f"deAPI paused until {time.strftime('%Y-%m-%d %H:%M', time.localtime(until))} (daily quota)")
    if not _take_budget():
        raise VlmError("daily VLM budget spent")

    session = session or requests.Session()
    text = _wait(_submit(data, session), session)
    config.VLM_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached.write_text(text, encoding="utf8")
    log.info("VLM OCR: %d chars (cached as %s)", len(text), digest[:12])
    return text
