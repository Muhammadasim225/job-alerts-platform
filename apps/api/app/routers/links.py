"""Endpoints reached without signing in: the Web Push public key and the one-click
unsubscribe link in alert emails."""

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import settings
from app.deps import DB
from app.schemas_account import EmailPrefsOut, PushKey
from shared import notifications
from shared.models import User
from shared.security import verify

router = APIRouter(prefix="/v1", tags=["account"])


@router.get("/push/public-key", response_model=PushKey)
def push_public_key():
    """VAPID application server key for PushManager.subscribe({applicationServerKey})."""
    if not settings.vapid_public_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Web Push is not configured")
    return {"public_key": settings.vapid_public_key}


@router.post("/email/unsubscribe", response_model=EmailPrefsOut)
def email_unsubscribe(token: str = Query(max_length=500), db: Session = DB):
    """Turn off alert emails from the signed link in an email. Works as the RFC 8058
    one-click target (List-Unsubscribe-Post), so mail apps can do it without a page."""
    data = verify(token, "unsubscribe")
    user = db.get(User, data["uid"]) if data else None
    if user is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired link")
    if user.email_alerts:
        notifications.skip_pending(db, user.id, "email alerts switched off", channel="email")
        user.email_alerts = False
        db.commit()
    return {"email_alerts": False}
