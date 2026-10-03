"""Match listings to user preferences and queue alerts.

Rules (an empty preference list / None means "any"):

  listing   open, not past its last date, kind in preference.kinds
  location  listing provinces overlap preference.provinces; a listing with no known
            province (national / not stated) matches everyone
  job post  BPS range overlaps the preferred range (posts without a BPS, e.g. company
            grades, are kept); field in preference.fields OR a keyword in the post
            name / qualification; user's age inside the post's age limits; required
            experience <= the user's experience
  programme level in preference.program_levels, keyword in name/subjects, age limits

Unknown values on a post never exclude it: missing an alert is worse than an extra one.
Alerts are inserted with ON CONFLICT DO NOTHING on (user, listing, type), so running
the matcher again can never queue the same alert twice.
"""

from dataclasses import dataclass, field
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, selectinload

from shared.models import Alert, Listing, Preference, Program, User, Vacancy


@dataclass
class Match:
    listing_id: int
    vacancy_ids: list[int] = field(default_factory=list)
    program_ids: list[int] = field(default_factory=list)


def _keyword_hit(keywords: list[str], *texts: str | None) -> bool:
    blob = " ".join(t for t in texts if t).lower()
    return any(k.strip().lower() in blob for k in keywords if k and k.strip())


def _age_ok(age: int | None, age_min: int | None, age_max: int | None) -> bool:
    if age is None:
        return True
    if age_min is not None and age < age_min:
        return False
    if age_max is not None and age > age_max:
        return False
    return True


def listing_is_live(listing: Listing, today: date | None = None) -> bool:
    today = today or date.today()
    return listing.status == "open" and not (listing.last_date and listing.last_date < today)


def location_ok(listing: Listing, pref: Preference) -> bool:
    if not pref.provinces or not listing.provinces:
        return True
    return bool(set(listing.provinces) & set(pref.provinces))


def vacancy_matches(v: Vacancy, pref: Preference) -> bool:
    if v.bps_min is not None:
        lo, hi = pref.bps_min or 1, pref.bps_max or 22
        if v.bps_max is not None and v.bps_max < lo or v.bps_min > hi:
            return False
    if pref.fields or pref.keywords:
        field_hit = bool(pref.fields) and v.field in pref.fields
        keyword_hit = bool(pref.keywords) and _keyword_hit(pref.keywords, v.post_name, v.qualification)
        if not (field_hit or keyword_hit):
            return False
    if not _age_ok(pref.age, v.age_min, v.age_max):
        return False
    if (
        pref.max_experience_years is not None
        and v.experience_years_min is not None
        and v.experience_years_min > pref.max_experience_years
    ):
        return False
    return True


def program_matches(p: Program, pref: Preference) -> bool:
    if pref.program_levels and p.level not in pref.program_levels:
        return False
    if pref.keywords and not _keyword_hit(pref.keywords, p.name, " ".join(p.subjects or [])):
        return False
    return _age_ok(pref.age, p.age_min, p.age_max)


def match_listing(listing: Listing, pref: Preference, today: date | None = None) -> Match | None:
    """The posts/programmes of this listing that suit this preference, or None."""
    if not listing_is_live(listing, today) or listing.kind not in (pref.kinds or ["job"]):
        return None
    if not location_ok(listing, pref):
        return None

    if listing.kind == "job":
        if not listing.vacancies:
            # Posts could not be extracted: alert only if the user filters nothing that
            # needs them, or the title carries a keyword
            if pref.fields or (pref.keywords and not _keyword_hit(pref.keywords, listing.title)):
                return None
            return Match(listing.id)
        ids = [v.id for v in listing.vacancies if vacancy_matches(v, pref)]
        return Match(listing.id, vacancy_ids=ids) if ids else None

    if not listing.programs:
        if pref.keywords and not _keyword_hit(pref.keywords, listing.title):
            return None
        return Match(listing.id)
    ids = [p.id for p in listing.programs if program_matches(p, pref)]
    return Match(listing.id, program_ids=ids) if ids else None


def _active_users(session: Session):
    return session.scalars(select(User).where(User.is_active.is_(True)).options(selectinload(User.preference))).all()


def _load_listing(session: Session, listing_id: int) -> Listing:
    return session.scalars(
        select(Listing).where(Listing.id == listing_id).options(selectinload(Listing.vacancies), selectinload(Listing.programs))
    ).one()


def queue_alerts_for_listing(session: Session, listing_id: int, alert_type: str = "new", today: date | None = None) -> int:
    """Queue alerts for every active user this listing matches. Returns how many
    new alerts were queued (existing ones are left untouched)."""
    listing = _load_listing(session, listing_id)
    queued = 0
    for user in _active_users(session):
        if user.preference is None:
            continue
        m = match_listing(listing, user.preference, today)
        if m is None:
            continue
        result = session.execute(
            insert(Alert)
            .values(
                user_id=user.id,
                listing_id=listing.id,
                alert_type=alert_type,
                matched_vacancy_ids=m.vacancy_ids,
                matched_program_ids=m.program_ids,
                status="pending",
            )
            .on_conflict_do_nothing(constraint="uq_alert_user_listing_type")
            .returning(Alert.id)
        )
        queued += len(result.all())  # rows actually inserted (not the conflicts)
    session.flush()
    return queued


def matches_for_user(session: Session, user: User, today: date | None = None) -> list[Match]:
    """All live listings that suit a user (for "show me current jobs" in the bot)."""
    if user.preference is None:
        return []
    today = today or date.today()
    listings = session.scalars(
        select(Listing)
        .where(Listing.status == "open", (Listing.last_date.is_(None)) | (Listing.last_date >= today))
        .options(selectinload(Listing.vacancies), selectinload(Listing.programs))
        .order_by(Listing.last_date.asc().nulls_last())
    ).all()
    return [m for l in listings if (m := match_listing(l, user.preference, today))]


def queue_deadline_reminders(session: Session, days_before: int = 2, today: date | None = None) -> int:
    """Second alert N days before the last date, for users who got the first one
    (the "missed deadline" pain point). Idempotent like every other alert."""
    today = today or date.today()
    target = today + timedelta(days=days_before)
    rows = session.execute(
        select(Alert.user_id, Alert.listing_id, Alert.matched_vacancy_ids, Alert.matched_program_ids)
        .join(Listing, Listing.id == Alert.listing_id)
        .join(User, User.id == Alert.user_id)
        .where(
            Alert.alert_type == "new",
            Alert.status == "sent",
            Listing.status == "open",
            Listing.last_date == target,
            User.is_active.is_(True),
        )
    ).all()
    queued = 0
    for user_id, listing_id, vacancy_ids, program_ids in rows:
        result = session.execute(
            insert(Alert)
            .values(
                user_id=user_id,
                listing_id=listing_id,
                alert_type="deadline_reminder",
                matched_vacancy_ids=vacancy_ids,
                matched_program_ids=program_ids,
                status="pending",
            )
            .on_conflict_do_nothing(constraint="uq_alert_user_listing_type")
            .returning(Alert.id)
        )
        queued += len(result.all())  # rows actually inserted (not the conflicts)
    session.flush()
    return queued
