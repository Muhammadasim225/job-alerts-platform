"""Public, read-only endpoints (website, SEO pages, partners)."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app import queries
from app.config import settings
from app.deps import DB
from app.schemas import Filters, ListingDetail, ListingSummary, Page, Stats, VacancyHit
from shared.models import Listing

router = APIRouter(prefix="/v1", tags=["public"])

# Data changes once a day (the daily scrape); let clients and proxies cache a little.
CACHE = "public, max-age=300"

Kind = Literal["job", "admission", "test", "unknown"]
Limit = Annotated[int, Query(ge=1, le=settings.max_page_size)]
Offset = Annotated[int, Query(ge=0, le=100_000)]
Bps = Annotated[int | None, Query(ge=1, le=22)]


def _filters(
    kind: Annotated[list[Kind] | None, Query(description="job, admission, test (repeat for several)")] = None,
    status: Literal["open", "closed", "any"] = "open",
    source: str | None = None,
    province: Annotated[list[str] | None, Query(description="e.g. Punjab (repeatable)")] = None,
    city: str | None = None,
    field: Annotated[list[str] | None, Query(description="post field, e.g. it, engineering, health")] = None,
    bps_min: Bps = None,
    bps_max: Bps = None,
    program_level: Annotated[list[str] | None, Query(description="admissions: BSN, MPhil, PhD, ...")] = None,
    q: Annotated[str | None, Query(max_length=100, description="text in title, organization or post names")] = None,
    closing_after: date | None = None,
    closing_before: date | None = None,
    include_expired: bool = False,
) -> queries.ListingFilters:
    if bps_min is not None and bps_max is not None and bps_min > bps_max:
        raise HTTPException(422, "bps_min must not be greater than bps_max")
    return queries.ListingFilters(
        kind=kind, status=None if status == "any" else status, source=source, province=province, city=city,
        field=field, bps_min=bps_min, bps_max=bps_max, program_level=program_level, q=q,
        closing_after=closing_after, closing_before=closing_before, include_expired=include_expired,
    )


Filt = Annotated[queries.ListingFilters, Depends(_filters)]


@router.get("/listings", response_model=Page[ListingSummary])
def list_listings(
    response: Response,
    f: Filt,
    db: Session = DB,
    sort: Literal["closing_soon", "newest", "closing_last"] = "closing_soon",
    limit: Limit = settings.default_page_size,
    offset: Offset = 0,
):
    """Listings (jobs, admissions, tests). Default: open and not past the last date, closing soonest first."""
    items, total = queries.search_listings(db, f, sort, limit, offset, date.today())
    response.headers["Cache-Control"] = CACHE
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _detail(db: Session, listing: Listing | None) -> dict:
    if listing is None:
        raise HTTPException(404, "Listing not found")
    today = date.today()
    agg = queries._post_aggregates(db, [listing.id])[listing.id]
    data = queries.summarize(listing, agg, today)
    data.update(
        department=listing.department,
        project_code=listing.project_code,
        announce_date=listing.announce_date,
        test_date=listing.test_date,
        advert_facts=listing.advert_facts or {},
        vacancies=listing.vacancies,
        programs=listing.programs,
        attachments=[a for a in listing.attachments if a.role != "other"],
        verified=listing.verified_at is not None,
        updated_at=listing.updated_at,
    )
    return data


def _load(db: Session, *where):
    return db.scalars(
        select(Listing)
        .where(*where)
        .options(selectinload(Listing.vacancies), selectinload(Listing.programs), selectinload(Listing.attachments))
    ).one_or_none()


@router.get("/listings/{listing_id}", response_model=ListingDetail)
def get_listing(listing_id: int, response: Response, db: Session = DB):
    """One listing with its posts / programmes, eligibility, test syllabus and advert files."""
    response.headers["Cache-Control"] = CACHE
    return _detail(db, _load(db, Listing.id == listing_id))


@router.get("/sources/{source}/listings/{external_id}", response_model=ListingDetail)
def get_listing_by_source_id(source: str, external_id: str, response: Response, db: Session = DB):
    """Same as above, addressed by the source's own id (e.g. nts / portal-101334)."""
    response.headers["Cache-Control"] = CACHE
    return _detail(db, _load(db, Listing.source == source, Listing.external_id == external_id))


@router.get("/vacancies", response_model=Page[VacancyHit])
def list_vacancies(
    response: Response,
    f: Filt,
    db: Session = DB,
    limit: Limit = settings.default_page_size,
    offset: Offset = 0,
):
    """Individual posts across all listings (e.g. every open BPS 11-16 IT post in Punjab)."""
    rows, total = queries.search_vacancies(db, f, limit, offset, date.today())
    items = [{**VacancyHit.model_validate({**_vacancy_dict(v), "listing": l}).model_dump()} for v, l in rows]
    response.headers["Cache-Control"] = CACHE
    return {"items": items, "total": total, "limit": limit, "offset": offset}


def _vacancy_dict(v) -> dict:
    return {c.key: getattr(v, c.key) for c in v.__mapper__.column_attrs}


@router.get("/stats", response_model=Stats)
def get_stats(response: Response, db: Session = DB):
    """Headline numbers: open listings by kind, open posts and seats, closing this week."""
    response.headers["Cache-Control"] = CACHE
    return queries.stats(db, date.today())


@router.get("/filters", response_model=Filters)
def get_filters(response: Response, db: Session = DB):
    """Values available for filtering open listings, with counts (for filter menus)."""
    response.headers["Cache-Control"] = CACHE
    return queries.facets(db, date.today())
