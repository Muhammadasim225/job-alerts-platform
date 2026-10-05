"""Passwordless sign-in for the website: a 6-digit code sent by email.

    POST /v1/auth/code    {email}         -> a code is emailed (valid 10 min)
    POST /v1/auth/verify  {email, code}   -> account created on first sign-in; returns a
                                             session token for "Authorization: Bearer"

No passwords to store, leak or reset, and every account has a verified email.

Codes live in Redis only as an HMAC (APP_SECRET), are single-use, and allow
MAX_TRIES wrong guesses before they are burned. Sending is throttled per address
(one per minute, five per hour) and per IP, so the endpoint cannot be used to flood an
inbox. The response is the same whether or not an account exists.

Sessions: a random token (32 bytes) is returned once; the database keeps its SHA-256
(auth_sessions), so a database leak does not expose working tokens.
"""

import hashlib
import hmac
import logging
import secrets
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import redis
from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import DB
from shared.models import AuthSession, Preference, User
from shared.security import hash_token

log = logging.getLogger("api.auth")

CODE_TTL = 600
MAX_TRIES = 5
RESEND_AFTER = 60
PER_EMAIL_PER_HOUR = 5
PER_IP_PER_HOUR = 20
TOUCH_EVERY = timedelta(hours=1)


@lru_cache(maxsize=4)
def _redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, socket_timeout=2, socket_connect_timeout=2)


def get_redis() -> redis.Redis:
    return _redis(settings.redis_url)


def _key(email: str) -> str:
    # Emails never appear in Redis keys
    return hashlib.sha256(email.encode()).hexdigest()[:32]


def _mac(email: str, code: str) -> str:
    return hmac.new(settings.app_secret.encode(), f"{email}:{code}".encode(), hashlib.sha256).hexdigest()


def require_auth_enabled() -> None:
    if not settings.app_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in is disabled (APP_SECRET not set)")


def _too_many(detail: str, retry_after: int) -> HTTPException:
    return HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, detail, headers={"Retry-After": str(retry_after)})


def issue_code(r: redis.Redis, email: str, ip: str) -> str:
    """Throttle, then store a fresh code. Raises 429 when over a limit."""
    k = _key(email)
    hour = datetime.now(UTC).strftime("%Y%m%d%H")
    pipe = r.pipeline()
    pipe.incr(f"auth:ip:{ip}:{hour}")
    pipe.expire(f"auth:ip:{ip}:{hour}", 3700)
    if pipe.execute()[0] > PER_IP_PER_HOUR:
        raise _too_many("Too many sign-in requests from this network, try again later", 3600)
    if not r.set(f"auth:cooldown:{k}", 1, nx=True, ex=RESEND_AFTER):
        raise _too_many("A code was just sent, wait a minute before asking again", RESEND_AFTER)
    pipe = r.pipeline()
    pipe.incr(f"auth:sent:{k}:{hour}")
    pipe.expire(f"auth:sent:{k}:{hour}", 3700)
    if pipe.execute()[0] > PER_EMAIL_PER_HOUR:
        raise _too_many("Too many codes for this address, try again later", 3600)

    code = f"{secrets.randbelow(10**6):06d}"
    pipe = r.pipeline()
    pipe.set(f"auth:code:{k}", _mac(email, code), ex=CODE_TTL)
    pipe.delete(f"auth:tries:{k}")
    pipe.execute()
    return code


def check_code(r: redis.Redis, email: str, code: str) -> bool:
    """True once per issued code. Wrong guesses are counted; the code is burned after MAX_TRIES."""
    k = _key(email)
    pipe = r.pipeline()
    pipe.incr(f"auth:tries:{k}")
    pipe.expire(f"auth:tries:{k}", CODE_TTL)
    pipe.get(f"auth:code:{k}")
    tries, _, stored = pipe.execute()
    if tries > MAX_TRIES:
        r.delete(f"auth:code:{k}")
        raise _too_many("Too many wrong codes, request a new one", RESEND_AFTER)
    if stored is None or not hmac.compare_digest(stored.decode(), _mac(email, code)):
        return False
    # Single use: of two requests racing with the same code, only one deletes it
    return r.delete(f"auth:code:{k}") == 1


def sign_in(db: Session, email: str, user_agent: str | None) -> tuple[User, str, datetime]:
    """Create the account on first sign-in, then a session. Returns (user, token, expiry)."""
    now = datetime.now(UTC)
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email, preference=Preference())
        db.add(user)
    user.email_verified_at = user.email_verified_at or now
    user.last_login_at = now
    db.flush()
    token = secrets.token_urlsafe(32)
    expires = now + timedelta(days=settings.session_days)
    db.add(AuthSession(user_id=user.id, token_hash=hash_token(token), user_agent=(user_agent or "")[:200], expires_at=expires))
    db.commit()
    db.refresh(user)
    return user, token, expires


def _bearer(authorization: str | None) -> str:
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required", headers={"WWW-Authenticate": "Bearer"})
    return token.strip()


def current_session(request: Request, authorization: str | None = Header(default=None), db: Session = DB) -> AuthSession:
    token = _bearer(authorization)
    now = datetime.now(UTC)
    session = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if session is None or session.expires_at <= now:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Session expired, sign in again", headers={"WWW-Authenticate": "Bearer"}
        )
    if now - session.last_seen_at > TOUCH_EVERY:  # one write per hour, not per request
        session.last_seen_at = now
        db.commit()
    request.state.user_id = session.user_id
    return session


def current_user(session: AuthSession = Depends(current_session), db: Session = DB) -> User:
    user = db.get(User, session.user_id)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sign in required")
    return user


USER = Depends(current_user)
