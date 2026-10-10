"""Write normalized scraper records into the database.

A record is the JSON the scraper's normalizer produces (one per listing). Upserts
are keyed on (source, external_id); a listing's posts/programmes/attachments are
replaced as a whole on every update, since the advert is the source of truth.
"""

from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from shared.models import Attachment, Listing, Organization, Program, Vacancy
from shared.orgs import clean_org_name, normalize_alias, org_slug
from shared.slugs import listing_slug
from shared.taxonomy import education_levels, gender_eligibility

# Fields whose change makes an update worth telling users about
SIGNIFICANT_FIELDS = ("status", "last_date", "kind")


@dataclass
class UpsertResult:
    listing: Listing
    is_new: bool
    changed_fields: list[str]


def _date(value) -> date | None:
    if not value:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def _dt(value) -> datetime | None:
    if not value:
        return None
    return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))


def _vacancy(i: int, v: dict) -> Vacancy:
    return Vacancy(
        position=i,
        post_name=v.get("post_name") or v.get("post_name_raw") or "",
        post_name_raw=v.get("post_name_raw"),
        bps=v.get("bps") or [],
        bps_min=v.get("bps_min"),
        bps_max=v.get("bps_max"),
        field=v.get("field"),
        total_posts=v.get("total_posts"),
        total_posts_shared=bool(v.get("total_posts_shared")),
        fee_pkr=v.get("fee_pkr"),
        age_min=v.get("age_min"),
        age_max=v.get("age_max"),
        qualification=v.get("qualification"),
        experience=v.get("experience"),
        experience_years_min=v.get("experience_years_min"),
        mode=v.get("mode"),
        details=v.get("details"),
        test_syllabus=v.get("test_syllabus") or [],
        extracted_from=v.get("extracted_from"),
    )


def _program(i: int, p: dict) -> Program:
    return Program(
        position=i,
        name=p.get("name") or "",
        level=p.get("level"),
        subjects=p.get("subjects") or [],
        duration=p.get("duration"),
        eligibility=p.get("eligibility") or [],
        age_min=p.get("age_min"),
        age_max=p.get("age_max"),
        fee_pkr=p.get("fee_pkr"),
        mode=p.get("mode"),
        details=p.get("details"),
        via_nts=p.get("via_nts", True),
        test_syllabus=p.get("test_syllabus") or [],
        extracted_from=p.get("extracted_from"),
    )


def _attachment(a: dict) -> Attachment:
    return Attachment(
        name=a.get("name"),
        url=a["url"],
        path=a.get("path"),
        role=a.get("role"),
        content_type=a.get("content_type"),
        sha256=a.get("sha256"),
        size=a.get("size"),
    )


def upsert_listing(session: Session, record: dict) -> UpsertResult:
    """Insert or update one normalized record. Does not commit."""
    listing = session.scalar(
        select(Listing).where(Listing.source == record["source"], Listing.external_id == record["listing_id"])
    )
    is_new = listing is None
    if is_new:
        listing = Listing(source=record["source"], external_id=record["listing_id"])
        session.add(listing)

    new_values = {
        "url": record["url"],
        "status": record["status"],
        "kind": record.get("kind") or "unknown",
        "title": record.get("title") or "",
        "organization": record.get("organization"),
        "department": record.get("department"),
        "project_code": record.get("project_code"),
        "last_date": _date(record.get("last_date")),
        "announce_date": _date(record.get("announce_date")),
        "test_date": _date(record.get("test_date")),
        "provinces": record.get("provinces") or [],
        "cities": record.get("cities") or [],
        "advert_facts": record.get("advert_facts") or {},
        "test_syllabus": record.get("test_syllabus") or {},
        "needs_review": bool(record.get("needs_review")),
        "review_reasons": record.get("review_reasons") or [],
        "raw_html_path": record.get("raw_html_path"),
        "parsed_text_path": record.get("parsed_text_path"),
        "scraped_at": _dt(record.get("scraped_at")),
        "normalized_at": _dt(record.get("normalized_at")),
    }
    changed = [] if is_new else [f for f in SIGNIFICANT_FIELDS if getattr(listing, f) != new_values[f]]
    for key, value in new_values.items():
        setattr(listing, key, value)

    if not is_new:
        # Delete the old rows before inserting their replacements, or the unique
        # (listing_id, url) constraint on attachments trips over the same file.
        listing.vacancies.clear()
        listing.programs.clear()
        listing.attachments.clear()
        session.flush()

    listing.vacancies = [_vacancy(i, v) for i, v in enumerate(record.get("vacancies") or [], 1)]
    listing.programs = [_program(i, p) for i, p in enumerate(record.get("programs") or [], 1)]
    seen_urls: set[str] = set()
    attachments = []
    for a in record.get("attachments") or []:
        if a.get("url") and a["url"] not in seen_urls:
            seen_urls.add(a["url"])
            attachments.append(_attachment(a))
    listing.attachments = attachments
    if record.get("apply_url"):
        listing.apply_url = record["apply_url"]
    if record.get("last_date_at"):
        listing.last_date_at = _dt(record["last_date_at"])

    session.flush()
    enrich_listing(session, listing)
    return UpsertResult(listing=listing, is_new=is_new, changed_fields=changed)


def resolve_organization(session: Session, raw: str | None, *, kind: str, source: str) -> Organization | None:
    """The canonical organization for a source's organization text, created if new.

    Safe under concurrent workers: a new row is inserted with ON CONFLICT DO NOTHING
    and re-read, so two workers storing the same new employer end up on one row."""
    if kind == "test" and source == "nts":  # GAT, NAT, ...: NTS runs the test itself
        return session.scalar(select(Organization).where(Organization.slug == "nts"))
    org = clean_org_name(raw)
    if org is None:
        return None
    keys = sorted({normalize_alias(org.name), *([normalize_alias(org.short_name)] if org.short_name else [])})
    found = session.scalar(
        select(Organization)
        .where(Organization.aliases.overlap(keys))
        .order_by(Organization.curated.desc(), Organization.id)
        .limit(1)
    )
    if found:
        return found

    base = org_slug(org) or "org"
    for n in range(1, 20):
        slug = base if n == 1 else f"{base}-{n}"
        new_id = session.scalar(
            insert(Organization)
            .values(slug=slug, name=org.name, short_name=org.short_name, kind="org", aliases=keys)
            .on_conflict_do_nothing(index_elements=["slug"])
            .returning(Organization.id)
        )
        if new_id is not None:
            return session.get(Organization, new_id)
        taken = session.scalar(select(Organization).where(Organization.slug == slug))
        if taken is not None and set(keys) & set(taken.aliases):  # same employer, stored meanwhile
            return taken
    return None


def enrich_listing(session: Session, listing: Listing) -> None:
    """Derive the website fields from the stored data: organization, slug, and each
    post's education levels and gender. Idempotent; used on every upsert and to
    backfill rows stored before these fields existed. Does not commit."""
    org = resolve_organization(session, listing.organization, kind=listing.kind, source=listing.source)
    listing.organization_id = org.id if org else None
    when = listing.announce_date or listing.last_date or (listing.first_seen_at.date() if listing.first_seen_at else None)
    listing.slug = listing_slug(
        kind=listing.kind,
        org=(org.short_name or org.name) if org else None,
        city=listing.cities[0] if listing.cities else None,
        when=when,
        title=listing.title,
    )
    gender = gender_eligibility((listing.advert_facts or {}).get("gender"))
    for v in listing.vacancies:
        v.education_levels = education_levels(v.qualification)
        v.gender = gender
    session.flush()


def backfill_listings(session: Session) -> int:
    """Enrich every listing that has no slug yet (rows stored before data model v2)."""
    listings = session.scalars(select(Listing).where(Listing.slug.is_(None))).all()
    for listing in listings:
        enrich_listing(session, listing)
    return len(listings)
