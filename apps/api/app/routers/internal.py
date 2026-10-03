"""Internal endpoints (X-API-Key): users & preferences, the alert outbox, back office.

Used by the Telegram bot (Phase 5) and an admin panel; never by the public website.
"""

from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import queries
from app.deps import DB, INTERNAL
from app.schemas_internal import (
    AlertFailure,
    AlertOut,
    MatchOut,
    Overview,
    PreferenceIn,
    ReviewItem,
    TaskQueued,
    UserIn,
    UserOut,
)
from shared import alerts as outbox
from shared.matching import matches_for_user
from shared.models import Alert, Listing, Preference, Program, User, Vacancy

router = APIRouter(prefix="/v1/internal", tags=["internal"], dependencies=INTERNAL)


# --- helpers -----------------------------------------------------------------


def _user(db: Session, chat_id: int) -> User:
    user = db.scalar(select(User).where(User.telegram_chat_id == chat_id))
    if user is None:
        raise HTTPException(404, "User not found")
    return user


def _summaries(db: Session, listing_ids: list[int]) -> dict[int, dict]:
    today = date.today()
    listings = db.scalars(select(Listing).where(Listing.id.in_(listing_ids))).all() if listing_ids else []
    agg = queries._post_aggregates(db, [l.id for l in listings])
    return {l.id: queries.summarize(l, agg[l.id], today) for l in listings}


def _post_names(db: Session, vacancy_ids: list[int], program_ids: list[int]) -> dict[tuple[str, int], str]:
    names = {}
    if vacancy_ids:
        names.update(
            {("v", i): n for i, n in db.execute(select(Vacancy.id, Vacancy.post_name).where(Vacancy.id.in_(vacancy_ids)))}
        )
    if program_ids:
        names.update({("p", i): n for i, n in db.execute(select(Program.id, Program.name).where(Program.id.in_(program_ids)))})
    return names


def _alerts_out(db: Session, rows: list[Alert]) -> list[dict]:
    users = {u.id: u for u in db.scalars(select(User).where(User.id.in_({a.user_id for a in rows})))} if rows else {}
    summaries = _summaries(db, list({a.listing_id for a in rows}))
    names = _post_names(db, [i for a in rows for i in a.matched_vacancy_ids], [i for a in rows for i in a.matched_program_ids])
    out = []
    for a in rows:
        posts = [names[("v", i)] for i in a.matched_vacancy_ids if ("v", i) in names]
        posts += [names[("p", i)] for i in a.matched_program_ids if ("p", i) in names]
        out.append(
            {
                "id": a.id,
                "alert_type": a.alert_type,
                "status": a.status,
                "attempts": a.attempts,
                "telegram_chat_id": users[a.user_id].telegram_chat_id,
                "language": users[a.user_id].language,
                "listing": summaries[a.listing_id],
                "matched_posts": posts,
                "created_at": a.created_at,
            }
        )
    return out


# --- users & preferences -------------------------------------------------------


@router.put("/users/{chat_id}", response_model=UserOut)
def upsert_user(chat_id: int, body: UserIn, db: Session = DB):
    """Create the user on /start (or update name/language). New users get default preferences."""
    user = db.scalar(select(User).where(User.telegram_chat_id == chat_id))
    if user is None:
        user = User(telegram_chat_id=chat_id, preference=Preference())
        db.add(user)
    user.name, user.language, user.is_active = body.name, body.language, True
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{chat_id}", response_model=UserOut)
def get_user(chat_id: int, db: Session = DB):
    return _user(db, chat_id)


@router.put("/users/{chat_id}/preferences", response_model=UserOut)
def set_preferences(chat_id: int, body: PreferenceIn, db: Session = DB):
    user = _user(db, chat_id)
    if user.preference is None:
        user.preference = Preference()
    for key, value in body.model_dump().items():
        setattr(user.preference, key, value)
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{chat_id}/unsubscribe", response_model=UserOut)
def unsubscribe(chat_id: int, db: Session = DB):
    """/stop: no more alerts; pending ones are skipped. History is kept."""
    user = _user(db, chat_id)
    user.is_active = False
    db.execute(
        Alert.__table__.update()
        .where(Alert.user_id == user.id, Alert.status.in_(("pending", "sending")))
        .values(status="skipped", error="user unsubscribed")
    )
    db.commit()
    db.refresh(user)
    return user


@router.post("/users/{chat_id}/resubscribe", response_model=UserOut)
def resubscribe(chat_id: int, db: Session = DB):
    user = _user(db, chat_id)
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user


@router.get("/users/{chat_id}/matches", response_model=list[MatchOut])
def user_matches(chat_id: int, limit: int = Query(20, ge=1, le=100), db: Session = DB):
    """Live listings that suit the user right now (for "show me current jobs")."""
    user = _user(db, chat_id)
    matches = matches_for_user(db, user)[:limit]
    summaries = _summaries(db, [m.listing_id for m in matches])
    names = _post_names(db, [i for m in matches for i in m.vacancy_ids], [i for m in matches for i in m.program_ids])
    return [
        {
            "listing": summaries[m.listing_id],
            "matched_posts": [names[("v", i)] for i in m.vacancy_ids] + [names[("p", i)] for i in m.program_ids],
        }
        for m in matches
    ]


# --- alert outbox (for senders) --------------------------------------------------


@router.post("/alerts/claim", response_model=list[AlertOut])
def claim_alerts(limit: int = Query(50, ge=1, le=200), db: Session = DB):
    """Hand out pending alerts to this sender; safe with several senders at once."""
    rows = outbox.claim_pending(db, limit)
    out = _alerts_out(db, rows)
    db.commit()
    return out


@router.post("/alerts/{alert_id}/sent", status_code=204)
def alert_sent(alert_id: int, db: Session = DB):
    try:
        outbox.mark_sent(db, alert_id)
    except LookupError:
        raise HTTPException(404, "Alert not found") from None
    db.commit()


@router.post("/alerts/{alert_id}/failed", status_code=204)
def alert_failed(alert_id: int, body: AlertFailure, db: Session = DB):
    try:
        outbox.mark_failed(db, alert_id, body.error, body.permanent)
    except LookupError:
        raise HTTPException(404, "Alert not found") from None
    db.commit()


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    status: str | None = Query(None, pattern="^(pending|sending|sent|failed|skipped)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = DB,
):
    q = select(Alert).order_by(Alert.created_at.desc()).limit(limit)
    if status:
        q = q.where(Alert.status == status)
    return _alerts_out(db, db.scalars(q).all())


# --- back office -----------------------------------------------------------------


@router.get("/admin/overview", response_model=Overview)
def overview(db: Session = DB):
    return {
        "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))),
        "listings_needing_review": db.scalar(
            select(func.count()).select_from(Listing).where(Listing.needs_review.is_(True), Listing.verified_at.is_(None))
        ),
        "alerts_by_status": dict(db.execute(select(Alert.status, func.count()).group_by(Alert.status)).all()),
    }


@router.get("/admin/review-queue", response_model=list[ReviewItem])
def review_queue(limit: int = Query(50, ge=1, le=200), db: Session = DB):
    """Listings the pipeline flagged and nobody has verified yet, closing soonest first."""
    rows = db.scalars(
        select(Listing)
        .where(Listing.needs_review.is_(True), Listing.verified_at.is_(None))
        .order_by(Listing.last_date.asc().nulls_last())
        .limit(limit)
    ).all()
    summaries = _summaries(db, [l.id for l in rows])
    return [{"listing": summaries[l.id], "review_reasons": l.review_reasons} for l in rows]


@router.post("/admin/listings/{listing_id}/verify", status_code=204)
def verify_listing(listing_id: int, db: Session = DB):
    """A human checked the record against the source (launch checklist: 50 spot checks)."""
    listing = db.get(Listing, listing_id)
    if listing is None:
        raise HTTPException(404, "Listing not found")
    listing.verified_at = datetime.now(UTC)
    db.commit()


@router.post("/admin/scrape", response_model=TaskQueued, status_code=202)
def trigger_scrape(force: bool = False):
    """Queue an NTS run now (normally Beat does this daily). The worker's Redis lock
    prevents a second run while one is in progress."""
    from app.tasks_client import send_task

    task_id = send_task("tasks.scrape_nts", queue="scrape", kwargs={"force": force})
    return {"task_id": task_id, "task": "tasks.scrape_nts"}
