"""Query building for the public endpoints.

Everything goes through SQLAlchemy expressions (bound parameters, no string SQL).
A page of listings costs a fixed number of queries: one count, one page, one
aggregate over that page's posts (no per-row queries).
"""

from dataclasses import dataclass
from datetime import date, timedelta

from sqlalchemy import Select, and_, distinct, exists, func, or_, select
from sqlalchemy.orm import Session

from shared.models import Listing, Program, Vacancy

SORTS = {
    "closing_soon": (Listing.last_date.asc().nulls_last(), Listing.id.desc()),
    "newest": (Listing.first_seen_at.desc(), Listing.id.desc()),
    "closing_last": (Listing.last_date.desc().nulls_last(), Listing.id.desc()),
}


@dataclass
class ListingFilters:
    kind: list[str] | None = None
    status: str | None = "open"
    source: str | None = None
    province: list[str] | None = None
    city: str | None = None
    field: list[str] | None = None
    bps_min: int | None = None
    bps_max: int | None = None
    program_level: list[str] | None = None
    q: str | None = None
    closing_after: date | None = None
    closing_before: date | None = None
    include_expired: bool = False


def _like(term: str) -> str:
    """User text as a literal ILIKE pattern (%, _ and \\ escaped)."""
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _vacancy_conditions(f: ListingFilters) -> list:
    conds = []
    if f.field:
        conds.append(Vacancy.field.in_(f.field))
    if f.bps_min is not None or f.bps_max is not None:
        lo, hi = f.bps_min or 1, f.bps_max or 22
        conds.append(and_(Vacancy.bps_min.is_not(None), Vacancy.bps_min <= hi, Vacancy.bps_max >= lo))
    return conds


def apply_listing_filters(stmt: Select, f: ListingFilters, today: date) -> Select:
    if f.status:
        stmt = stmt.where(Listing.status == f.status)
    if f.kind:
        stmt = stmt.where(Listing.kind.in_(f.kind))
    if f.source:
        stmt = stmt.where(Listing.source == f.source)
    if f.province:
        stmt = stmt.where(Listing.provinces.overlap(f.province))
    if f.city:
        stmt = stmt.where(Listing.cities.any(f.city))
    if not f.include_expired:
        stmt = stmt.where(or_(Listing.last_date.is_(None), Listing.last_date >= today))
    if f.closing_after:
        stmt = stmt.where(Listing.last_date >= f.closing_after)
    if f.closing_before:
        stmt = stmt.where(Listing.last_date <= f.closing_before)
    vconds = _vacancy_conditions(f)
    if vconds:
        stmt = stmt.where(exists().where(Vacancy.listing_id == Listing.id, *vconds))
    if f.program_level:
        stmt = stmt.where(exists().where(Program.listing_id == Listing.id, Program.level.in_(f.program_level)))
    if f.q and f.q.strip():
        pattern = _like(f.q.strip())
        stmt = stmt.where(
            or_(
                Listing.title.ilike(pattern, escape="\\"),
                Listing.organization.ilike(pattern, escape="\\"),
                Listing.department.ilike(pattern, escape="\\"),
                exists().where(Vacancy.listing_id == Listing.id, Vacancy.post_name.ilike(pattern, escape="\\")),
                exists().where(Program.listing_id == Listing.id, Program.name.ilike(pattern, escape="\\")),
            )
        )
    return stmt


def _post_aggregates(session: Session, listing_ids: list[int]) -> dict[int, dict]:
    """posts_count / seats / BPS range / fields for a page of listings, in two queries."""
    if not listing_ids:
        return {}
    agg = {i: {"posts_count": 0, "total_seats": None, "bps_min": None, "bps_max": None, "fields": []} for i in listing_ids}
    rows = session.execute(
        select(
            Vacancy.listing_id,
            func.count(Vacancy.id),
            func.sum(Vacancy.total_posts),
            func.min(Vacancy.bps_min),
            func.max(Vacancy.bps_max),
            func.array_remove(func.array_agg(distinct(Vacancy.field)), None),
        )
        .where(Vacancy.listing_id.in_(listing_ids))
        .group_by(Vacancy.listing_id)
    ).all()
    for lid, n, seats, lo, hi, fields in rows:
        agg[lid].update(posts_count=n, total_seats=seats, bps_min=lo, bps_max=hi, fields=sorted(fields or []))
    for lid, n in session.execute(
        select(Program.listing_id, func.count(Program.id)).where(Program.listing_id.in_(listing_ids)).group_by(Program.listing_id)
    ).all():
        agg[lid]["posts_count"] += n
    return agg


def summarize(listing: Listing, agg: dict, today: date) -> dict:
    data = {
        c: getattr(listing, c)
        for c in (
            "id",
            "source",
            "external_id",
            "url",
            "status",
            "kind",
            "title",
            "organization",
            "last_date",
            "provinces",
            "cities",
            "first_seen_at",
        )
    }
    data["is_expired"] = bool(listing.last_date and listing.last_date < today)
    data["days_left"] = (listing.last_date - today).days if listing.last_date and not data["is_expired"] else None
    data["registration_open"] = (listing.advert_facts or {}).get("registration_open")
    data.update(agg)
    return data


def search_listings(session: Session, f: ListingFilters, sort: str, limit: int, offset: int, today: date):
    base = apply_listing_filters(select(Listing), f, today)
    total = session.scalar(select(func.count()).select_from(base.order_by(None).subquery()))
    listings = session.scalars(base.order_by(*SORTS[sort]).limit(limit).offset(offset)).all()
    agg = _post_aggregates(session, [l.id for l in listings])
    return [summarize(l, agg[l.id], today) for l in listings], total


def search_vacancies(session: Session, f: ListingFilters, limit: int, offset: int, today: date):
    """Posts (not listings) matching the filters, earliest deadline first."""
    stmt = select(Vacancy, Listing).join(Listing, Listing.id == Vacancy.listing_id)
    # Listing-level filters only; post-level ones (field, BPS, text) apply to each post itself
    listing_only = ListingFilters(**{**f.__dict__, "field": None, "bps_min": None, "bps_max": None, "q": None})
    stmt = apply_listing_filters(stmt, listing_only, today)
    for cond in _vacancy_conditions(f):
        stmt = stmt.where(cond)
    if f.q and f.q.strip():
        pattern = _like(f.q.strip())
        stmt = stmt.where(or_(Vacancy.post_name.ilike(pattern, escape="\\"), Listing.title.ilike(pattern, escape="\\")))
    total = session.scalar(select(func.count()).select_from(stmt.order_by(None).subquery()))
    rows = session.execute(
        stmt.order_by(Listing.last_date.asc().nulls_last(), Listing.id, Vacancy.position).limit(limit).offset(offset)
    ).all()
    agg = _post_aggregates(session, list({l.id for _, l in rows}))
    return [(v, summarize(l, agg[l.id], today)) for v, l in rows], total


def stats(session: Session, today: date) -> dict:
    live = and_(Listing.status == "open", or_(Listing.last_date.is_(None), Listing.last_date >= today))
    by_kind = dict(session.execute(select(Listing.kind, func.count()).where(live).group_by(Listing.kind)).all())
    posts, seats = session.execute(
        select(func.count(Vacancy.id), func.coalesce(func.sum(Vacancy.total_posts), 0))
        .join(Listing, Listing.id == Vacancy.listing_id)
        .where(live)
    ).one()
    closing = session.scalar(
        select(func.count()).select_from(Listing).where(live, Listing.last_date <= today + timedelta(days=7))
    )
    return {
        "open_listings": by_kind,
        "open_posts": posts,
        "open_seats": seats,
        "closing_in_7_days": closing,
        "last_scraped_at": session.scalar(select(func.max(Listing.scraped_at))),
    }


def facets(session: Session, today: date) -> dict:
    live = and_(Listing.status == "open", or_(Listing.last_date.is_(None), Listing.last_date >= today))

    def rows(stmt):
        return [{"value": v, "count": c} for v, c in session.execute(stmt).all() if v]

    prov = func.unnest(Listing.provinces).label("p")
    city = func.unnest(Listing.cities).label("c")
    return {
        "kinds": rows(select(Listing.kind, func.count()).where(live).group_by(Listing.kind).order_by(func.count().desc())),
        "provinces": rows(select(prov, func.count()).where(live).group_by(prov).order_by(func.count().desc())),
        "cities": rows(select(city, func.count()).where(live).group_by(city).order_by(func.count().desc())),
        "fields": rows(
            select(Vacancy.field, func.count(distinct(Listing.id)))
            .join(Listing, Listing.id == Vacancy.listing_id)
            .where(live)
            .group_by(Vacancy.field)
            .order_by(func.count(distinct(Listing.id)).desc())
        ),
        "program_levels": rows(
            select(Program.level, func.count(distinct(Listing.id)))
            .join(Listing, Listing.id == Program.listing_id)
            .where(live)
            .group_by(Program.level)
            .order_by(func.count(distinct(Listing.id)).desc())
        ),
    }
