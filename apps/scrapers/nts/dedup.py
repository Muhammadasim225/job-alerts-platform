"""Redis-backed de-duplication for NTS listings and downloaded files.

A listing is (re)processed only when its fingerprint changes: a new listing, a
changed deadline, a new attachment or a new post. Listings are marked seen only
after processing succeeds, so a failed run is retried on the next schedule.

Keys:
  nts:listing:<listing_id>   hash {fingerprint, first_seen, last_changed, status}
  nts:file:<sha1(url)>       sha256 of the downloaded content
  nts:filemeta:<sha1(url)>   hash {etag, last_modified, length} from the server, to spot a replaced file
  nts:claim:<id>:<fp>        short-lived lock while one version of a listing is queued/processing
"""

import hashlib
from datetime import UTC, datetime

import redis

import config
from nts.common import fingerprint

LISTING_KEY = "nts:listing:{}"
FILE_KEY = "nts:file:{}"
CLAIM_KEY = "nts:claim:{}:{}"
FILE_META_KEY = "nts:filemeta:{}"

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(config.REDIS_URL, decode_responses=True)
    return _client


def listing_fingerprint(listing: dict) -> str:
    """Fingerprint only the fields whose change should trigger re-processing/alerts."""
    detail = listing.get("detail") or {}
    return fingerprint(
        {
            "title": listing.get("title"),
            "deadline": listing.get("deadline_raw"),
            "last_date": detail.get("last_date_raw"),
            "test_date": detail.get("test_date_raw"),
            "attachments": sorted(a["url"] for a in detail.get("attachments", [])),
            "posts": [p.get("raw") for p in detail.get("posts", [])],
        }
    )


def is_new_or_changed(listing: dict, r: redis.Redis | None = None) -> bool:
    r = r or get_redis()
    stored = r.hget(LISTING_KEY.format(listing["listing_id"]), "fingerprint")
    return stored != listing_fingerprint(listing)


def was_seen_before(listing_id: str, r: redis.Redis | None = None) -> bool:
    r = r or get_redis()
    return bool(r.exists(LISTING_KEY.format(listing_id)))


def mark_processed(listing: dict, r: redis.Redis | None = None) -> None:
    r = r or get_redis()
    key = LISTING_KEY.format(listing["listing_id"])
    now = datetime.now(UTC).isoformat()
    pipe = r.pipeline()
    pipe.hsetnx(key, "first_seen", now)
    pipe.hset(key, mapping={"fingerprint": listing_fingerprint(listing), "last_changed": now, "status": listing["status"]})
    pipe.execute()


def update_status(listing: dict, r: redis.Redis | None = None) -> None:
    """Record open->closed without re-processing a listing."""
    r = r or get_redis()
    key = LISTING_KEY.format(listing["listing_id"])
    if r.exists(key):
        r.hset(key, "status", listing["status"])


def claim(listing: dict, ttl: int = 60 * 60, r: redis.Redis | None = None) -> bool:
    """Reserve this version of a listing for processing. Returns False if another run
    already queued the same version, so overlapping runs never process it twice."""
    r = r or get_redis()
    key = CLAIM_KEY.format(listing["listing_id"], listing_fingerprint(listing)[:16])
    return bool(r.set(key, "1", nx=True, ex=ttl))


def release_claim(listing: dict, r: redis.Redis | None = None) -> None:
    r = r or get_redis()
    r.delete(CLAIM_KEY.format(listing["listing_id"], listing_fingerprint(listing)[:16]))


def _url_key(url: str) -> str:
    return FILE_KEY.format(hashlib.sha1(url.encode()).hexdigest())


def known_file_hash(url: str, r: redis.Redis | None = None) -> str | None:
    r = r or get_redis()
    return r.get(_url_key(url))


def remember_file(url: str, content_sha256: str, r: redis.Redis | None = None) -> None:
    r = r or get_redis()
    r.set(_url_key(url), content_sha256)


def _meta_key(url: str) -> str:
    return FILE_META_KEY.format(hashlib.sha1(url.encode()).hexdigest())


def known_file_meta(url: str, r: redis.Redis | None = None) -> dict:
    """ETag / Last-Modified / Content-Length recorded when the file was downloaded."""
    r = r or get_redis()
    return r.hgetall(_meta_key(url))


def remember_file_meta(url: str, meta: dict, r: redis.Redis | None = None) -> None:
    r = r or get_redis()
    meta = {k: v for k, v in meta.items() if v}
    if meta:
        key = _meta_key(url)
        r.delete(key)
        r.hset(key, mapping=meta)


def forget_listing(listing_id: str, r: redis.Redis | None = None) -> None:
    """Force a listing to be processed again on the next run."""
    r = r or get_redis()
    r.delete(LISTING_KEY.format(listing_id))
