"""The signed-in user: settings, preferences, matching jobs, alert inbox, push devices.

All endpoints need "Authorization: Bearer <token>" from /v1/auth/verify.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query, Request, status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app import queries
from app.auth import USER
from app.deps import DB
from app.schemas_account import Inbox, MarkRead, MatchOut, MeOut, MePatch, PushEndpoint, PushSubscriptionIn
from app.schemas_internal import PreferenceIn, PreferenceOut
from shared import notifications
from shared.matching import matches_for_user
from shared.models import Alert, Preference, PushSubscription, User
from shared.security import is_push_endpoint_allowed

router = APIRouter(prefix="/v1/me", tags=["account"])


def me_out(db: Session, user: User) -> dict:
    devices = db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
    return {
        **{c: getattr(user, c) for c in ("id", "email", "name", "language", "email_alerts", "push_alerts", "created_at")},
        "alerts_enabled": user.is_active,
        "push_devices": devices,
        "preference": PreferenceOut.model_validate(user.preference) if user.preference else None,
    }


@router.get("", response_model=MeOut)
def get_me(db: Session = DB, user: User = USER):
    return me_out(db, user)


@router.patch("", response_model=MeOut)
def update_me(body: MePatch, db: Session = DB, user: User = USER):
    sent = body.model_dump(exclude_unset=True)
    if "name" in sent:
        user.name = (body.name or "").strip() or None
    if body.language:
        user.language = body.language
    # Switching something off also cancels what is already queued for it
    if body.alerts_enabled is not None:
        if not body.alerts_enabled and user.is_active:
            notifications.skip_pending(db, user.id, "alerts switched off")
        user.is_active = body.alerts_enabled
    for flag, channel in (("email_alerts", "email"), ("push_alerts", "push")):
        value = getattr(body, flag)
        if value is None:
            continue
        if not value and getattr(user, flag):
            notifications.skip_pending(db, user.id, f"{channel} alerts switched off", channel=channel)
        setattr(user, flag, value)
    db.commit()
    db.refresh(user)
    return me_out(db, user)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
def delete_me(db: Session = DB, user: User = USER):
    """Delete the account and everything tied to it (preferences, inbox, sessions, devices)."""
    db.execute(delete(User).where(User.id == user.id))
    db.commit()


@router.put("/preferences", response_model=MeOut)
def set_preferences(body: PreferenceIn, db: Session = DB, user: User = USER):
    if user.preference is None:
        user.preference = Preference()
    for key, value in body.model_dump().items():
        setattr(user.preference, key, value)
    db.commit()
    db.refresh(user)
    return me_out(db, user)


@router.get("/matches", response_model=list[MatchOut])
def my_matches(limit: int = Query(20, ge=1, le=100), db: Session = DB, user: User = USER):
    """Open listings that suit the user right now, closing soonest first."""
    matches = matches_for_user(db, user)[:limit]
    summaries = queries.listing_summaries(db, [m.listing_id for m in matches])
    names = queries.post_names(db, [i for m in matches for i in m.vacancy_ids], [i for m in matches for i in m.program_ids])
    return [
        {"listing": summaries[m.listing_id], "matched_posts": queries.matched_names(names, m.vacancy_ids, m.program_ids)}
        for m in matches
    ]


@router.get("/alerts", response_model=Inbox)
def inbox(
    limit: int = Query(20, ge=1, le=100),
    before: int | None = Query(None, ge=1, description="id of the last item of the previous page"),
    unread_only: bool = False,
    db: Session = DB,
    user: User = USER,
):
    """The user's alerts, newest first (keyset pagination: stable while new alerts arrive)."""
    q = select(Alert).where(Alert.user_id == user.id, Alert.status != "skipped")
    if before:
        q = q.where(Alert.id < before)
    if unread_only:
        q = q.where(Alert.read_at.is_(None))
    rows = db.scalars(q.order_by(Alert.id.desc()).limit(limit + 1)).all()
    page, more = rows[:limit], len(rows) > limit
    summaries = queries.listing_summaries(db, list({a.listing_id for a in page}))
    names = queries.post_names(
        db, [i for a in page for i in a.matched_vacancy_ids], [i for a in page for i in a.matched_program_ids]
    )
    unread = db.scalar(
        select(func.count())
        .select_from(Alert)
        .where(Alert.user_id == user.id, Alert.status != "skipped", Alert.read_at.is_(None))
    )
    return {
        "items": [
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "created_at": a.created_at,
                "read": a.read_at is not None,
                "listing": summaries[a.listing_id],
                "matched_posts": queries.matched_names(names, a.matched_vacancy_ids, a.matched_program_ids),
            }
            for a in page
        ],
        "unread": unread,
        "next_before": page[-1].id if more else None,
    }


@router.post("/alerts/read", status_code=status.HTTP_204_NO_CONTENT)
def mark_read(body: MarkRead, db: Session = DB, user: User = USER):
    if not body.all and not body.ids:
        return
    q = update(Alert).where(Alert.user_id == user.id, Alert.read_at.is_(None))
    if not body.all:
        q = q.where(Alert.id.in_(body.ids))
    db.execute(q.values(read_at=datetime.now(UTC)))
    db.commit()


@router.post("/push-subscriptions", status_code=status.HTTP_201_CREATED)
def add_push_subscription(body: PushSubscriptionIn, request: Request, db: Session = DB, user: User = USER):
    """Register this browser for Web Push. Re-subscribing (or another account signing in
    on the same browser) updates the existing row: one endpoint, one owner."""
    if not is_push_endpoint_allowed(body.endpoint):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Not a supported push service endpoint")
    sub = db.scalar(select(PushSubscription).where(PushSubscription.endpoint == body.endpoint))
    if sub is None:
        if db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id)) >= 10:
            raise HTTPException(status.HTTP_409_CONFLICT, "Too many devices; remove one first")
        sub = PushSubscription(endpoint=body.endpoint)
        db.add(sub)
    sub.user_id, sub.p256dh, sub.auth = user.id, body.keys.p256dh, body.keys.auth
    sub.user_agent = (request.headers.get("User-Agent") or "")[:200]
    db.commit()
    return {
        "push_devices": db.scalar(select(func.count()).select_from(PushSubscription).where(PushSubscription.user_id == user.id))
    }


@router.delete("/push-subscriptions", status_code=status.HTTP_204_NO_CONTENT)
def remove_push_subscription(body: PushEndpoint, db: Session = DB, user: User = USER):
    db.execute(delete(PushSubscription).where(PushSubscription.user_id == user.id, PushSubscription.endpoint == body.endpoint))
    db.commit()
