"""Small security helpers shared by the API and the notifier.

- signed tokens for links in emails (one-click unsubscribe): HMAC-SHA256 with
  APP_SECRET, bound to a purpose, with an expiry; nothing to store
- token hashing for login sessions (only the hash is kept in the database)
- the Web Push endpoint allowlist: the notifier POSTs to endpoints that browsers
  hand to users, so only real push services are accepted (no requests to internal
  hosts via a crafted "endpoint")
"""

import base64
import hashlib
import hmac
import json
import os
import time
from urllib.parse import urlsplit

PUSH_HOST_SUFFIXES = (
    "fcm.googleapis.com",  # Chrome, Edge (Android/desktop), Samsung Internet, Opera
    "push.services.mozilla.com",  # Firefox
    "notify.windows.com",  # legacy Edge / Windows
    "push.apple.com",  # Safari (macOS, iOS 16.4+ home-screen web apps)
)


def app_secret() -> str:
    return os.getenv("APP_SECRET", "")


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def sign(payload: dict, purpose: str, ttl_seconds: int, secret: str | None = None) -> str:
    secret = secret or app_secret()
    if not secret:
        raise RuntimeError("APP_SECRET is not set")
    body = _b64(json.dumps({**payload, "p": purpose, "exp": int(time.time()) + ttl_seconds}, separators=(",", ":")).encode())
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def verify(token: str, purpose: str, secret: str | None = None) -> dict | None:
    """The payload, or None if the token is forged, for another purpose, or expired."""
    secret = secret or app_secret()
    try:
        body, mac = token.split(".", 1)
        expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
        if not secret or not hmac.compare_digest(_unb64(mac), expected):
            return None
        data = json.loads(_unb64(body))
    except (ValueError, TypeError):
        return None
    if data.get("p") != purpose or data.get("exp", 0) < time.time():
        return None
    return data


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_push_endpoint_allowed(endpoint: str) -> bool:
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.port not in (None, 443):
        return False
    return any(host == s or host.endswith("." + s) for s in PUSH_HOST_SUFFIXES)
