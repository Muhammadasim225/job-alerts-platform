"""FastAPI dependencies: a DB session per request and the internal API key check."""

import hmac
from collections.abc import Iterator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from shared.db import session_factory


def get_db() -> Iterator[Session]:
    """One session per request; committed by the endpoint when it writes, always closed."""
    session = session_factory(settings.database_url or None)()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def require_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """Guard for internal endpoints. Constant-time compare; disabled when no key is configured."""
    if not settings.internal_api_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Internal API is disabled (INTERNAL_API_KEY not set)")
    if not x_api_key or not hmac.compare_digest(x_api_key, settings.internal_api_key):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")


DB = Depends(get_db)
INTERNAL = [Depends(require_api_key)]
