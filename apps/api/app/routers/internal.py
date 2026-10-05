"""Internal endpoints (X-API-Key): back office and operations.

Used by an admin panel and scripts; never by the public website. Website users
manage their own account through /v1/auth and /v1/me.
"""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import queries
from app.deps import DB, INTERNAL
from app.schemas_internal import AlertOut, Overview, ReviewItem, TaskQueued
from shared.models import Alert, Delivery, Listing, User

router = APIRouter(prefix="/v1/internal", tags=["internal"], dependencies=INTERNAL)


@router.get("/alerts", response_model=list[AlertOut])
def list_alerts(
    status: str | None = Query(None, pattern="^(pending|sent|skipped)$"),
    limit: int = Query(50, ge=1, le=200),
    db: Session = DB,
):
    """Recent alerts (matches), newest first."""
    q = select(Alert).order_by(Alert.id.desc()).limit(limit)
    if status:
        q = q.where(Alert.status == status)
    rows = db.scalars(q).all()
    summaries = queries.listing_summaries(db, list({a.listing_id for a in rows}))
    names = queries.post_names(
        db, [i for a in rows for i in a.matched_vacancy_ids], [i for a in rows for i in a.matched_program_ids]
    )
    return [
        {
            "id": a.id,
            "user_id": a.user_id,
            "alert_type": a.alert_type,
            "status": a.status,
            "listing": summaries[a.listing_id],
            "matched_posts": queries.matched_names(names, a.matched_vacancy_ids, a.matched_program_ids),
            "created_at": a.created_at,
            "sent_at": a.sent_at,
        }
        for a in rows
    ]


# --- back office -----------------------------------------------------------------


@router.get("/admin/overview", response_model=Overview)
def overview(db: Session = DB):
    return {
        "users": db.scalar(select(func.count()).select_from(User)),
        "active_users": db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True))),
        "listings_needing_review": db.scalar(
            select(func.count()).select_from(Listing).where(Listing.needs_review.is_(True), Listing.verified_at.is_(None))
        ),
        "alerts_by_status": dict(db.execute(select(Alert.status, func.count()).group_by(Alert.status)).all()),
        "deliveries_by_status": {
            f"{channel}:{status}": n
            for channel, status, n in db.execute(
                select(Delivery.channel, Delivery.status, func.count()).group_by(Delivery.channel, Delivery.status)
            ).all()
        },
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
    summaries = queries.listing_summaries(db, [l.id for l in rows])
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
