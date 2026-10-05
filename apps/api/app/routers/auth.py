"""Sign-in by emailed code (see app/auth.py for the security model)."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app import auth
from app.deps import DB
from app.routers.me import me_out
from app.schemas_account import CodeIn, CodeSent, EmailIn, SessionOut
from shared.models import AuthSession

log = logging.getLogger("api.auth")
router = APIRouter(prefix="/v1/auth", tags=["account"], dependencies=[Depends(auth.require_auth_enabled)])


@router.post("/code", response_model=CodeSent, status_code=status.HTTP_202_ACCEPTED)
def request_code(body: EmailIn, request: Request, r=Depends(auth.get_redis)):
    """Email a 6-digit sign-in code. Same answer whether or not the account exists."""
    from app.tasks_client import send_task

    ip = request.client.host if request.client else "unknown"
    code = auth.issue_code(r, body.email, ip)
    try:
        send_task("notify.send_login_code", queue="notify", kwargs={"email": body.email, "code": code})
    except Exception:
        log.exception("Could not queue the sign-in email")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Could not send the code, try again shortly") from None
    return {"expires_in": auth.CODE_TTL}


@router.post("/verify", response_model=SessionOut)
def verify_code(body: CodeIn, request: Request, db: Session = DB, r=Depends(auth.get_redis)):
    if not auth.check_code(r, body.email, body.code):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Wrong or expired code")
    user, token, expires = auth.sign_in(db, body.email, request.headers.get("User-Agent"))
    return {"token": token, "expires_at": expires, "user": me_out(db, user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(session: AuthSession = Depends(auth.current_session), db: Session = DB):
    db.delete(session)
    db.commit()
