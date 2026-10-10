"""PostgreSQL schema.

Designed from the real normalized NTS records (apps/scrapers/data/normalized):

  listings      one advert/announcement on a source (NTS project), job or admission
  vacancies     posts of a job listing (BPS, seats, qualification, ...)
  programs      programmes of an admission/test listing (level, subjects, eligibility, ...)
  attachments   advert / syllabus / sample-paper files of a listing
  users         website accounts (email login), with their notification switches
  auth_sessions login sessions (only a hash of the token is stored)
  push_subscriptions  browser Web Push endpoints, several per user (phone, laptop)
  preferences   what a user wants to be alerted about
  alerts        every match for a user (their in-app inbox), unique per (user, listing, type)
  deliveries    one notification (email digest / push) carrying a batch of alerts, with retries
  organizations canonical employers / commissions / testing bodies (hubs /org/{slug})
  hub_slugs     the city, province, region and field hubs of the website (/jobs/{slug})
  deadline_changes  every change of a listing's last date ("deadline extended" banners)
  saved_listings    listings a user saved for a last-date reminder
  listing_events    transactional outbox of listing changes (page refresh, alerts, caches)
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Listing(TimestampMixin, Base):
    __tablename__ = "listings"
    __table_args__ = (UniqueConstraint("source", "external_id", name="uq_listing_source_external_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(20), index=True)  # "nts" (later "ppsc", "fpsc")
    external_id: Mapped[str] = mapped_column(String(120))  # e.g. "portal-101334"
    url: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(10), index=True)  # open | closed
    kind: Mapped[str] = mapped_column(String(12), index=True)  # job | admission | test | unknown
    title: Mapped[str] = mapped_column(Text)
    organization: Mapped[str | None] = mapped_column(Text)  # as the source wrote it
    organization_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id", ondelete="SET NULL"), index=True)
    department: Mapped[str | None] = mapped_column(Text)
    project_code: Mapped[str | None] = mapped_column(String(40))
    # URL: /jobs/{slug}-{id}; rebuilt on every update, old slugs redirect by id
    slug: Mapped[str | None] = mapped_column(String(100))
    apply_url: Mapped[str | None] = mapped_column(Text)  # official online-apply page, when known

    last_date: Mapped[date | None] = mapped_column(Date, index=True)
    last_date_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # with time (PKT), when known
    announce_date: Mapped[date | None] = mapped_column(Date)
    test_date: Mapped[date | None] = mapped_column(Date)  # tentative

    provinces: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    cities: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)

    advert_facts: Mapped[dict] = mapped_column(JSONB, default=dict)  # registration_open, session, eligibility, ...
    test_syllabus: Mapped[dict] = mapped_column(JSONB, default=dict)  # post -> [{subject, weight_percent}]

    needs_review: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_reasons: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    # A human has checked the record against the source (launch checklist: 50 spot checks)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    raw_html_path: Mapped[str | None] = mapped_column(Text)
    parsed_text_path: Mapped[str | None] = mapped_column(Text)
    scraped_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    normalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    vacancies: Mapped[list["Vacancy"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="Vacancy.position"
    )
    programs: Mapped[list["Program"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", order_by="Program.position"
    )
    attachments: Mapped[list["Attachment"]] = relationship(back_populates="listing", cascade="all, delete-orphan")
    org: Mapped["Organization | None"] = relationship()

    @property
    def is_expired(self) -> bool:
        return bool(self.last_date and self.last_date < date.today())


class Vacancy(Base):
    __tablename__ = "vacancies"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)  # order on the advert

    post_name: Mapped[str] = mapped_column(Text)
    post_name_raw: Mapped[str | None] = mapped_column(Text)
    bps: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    bps_min: Mapped[int | None] = mapped_column(Integer, index=True)
    bps_max: Mapped[int | None] = mapped_column(Integer, index=True)
    field: Mapped[str | None] = mapped_column(String(30), index=True)
    total_posts: Mapped[int | None] = mapped_column(Integer)
    total_posts_shared: Mapped[bool] = mapped_column(Boolean, default=False)
    fee_pkr: Mapped[int | None] = mapped_column(Integer)
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)
    qualification: Mapped[str | None] = mapped_column(Text)
    # Levels named in the qualification (shared.taxonomy), lowest first; a filter hint only
    education_levels: Mapped[list[str]] = mapped_column(ARRAY(String(20)), default=list, server_default="{}")
    gender: Mapped[str | None] = mapped_column(String(10))  # any | male | female; None = not stated
    experience: Mapped[str | None] = mapped_column(Text)
    experience_years_min: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str | None] = mapped_column(String(20))
    details: Mapped[str | None] = mapped_column(Text)
    test_syllabus: Mapped[list] = mapped_column(JSONB, default=list)
    extracted_from: Mapped[str | None] = mapped_column(String(20))  # portal_html | advert_table | advert_text

    listing: Mapped[Listing] = relationship(back_populates="vacancies")


class Program(Base):
    __tablename__ = "programs"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer)

    name: Mapped[str] = mapped_column(Text)
    level: Mapped[str | None] = mapped_column(String(30), index=True)  # BSN | MPhil | PhD | Diploma | ...
    subjects: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    duration: Mapped[str | None] = mapped_column(String(30))
    eligibility: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    age_min: Mapped[int | None] = mapped_column(Integer)
    age_max: Mapped[int | None] = mapped_column(Integer)
    fee_pkr: Mapped[int | None] = mapped_column(Integer)
    mode: Mapped[str | None] = mapped_column(String(20))
    details: Mapped[str | None] = mapped_column(Text)
    via_nts: Mapped[bool] = mapped_column(Boolean, default=True)
    test_syllabus: Mapped[list] = mapped_column(JSONB, default=list)
    extracted_from: Mapped[str | None] = mapped_column(String(20))

    listing: Mapped[Listing] = relationship(back_populates="programs")


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (UniqueConstraint("listing_id", "url", name="uq_attachment_listing_url"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    name: Mapped[str | None] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    path: Mapped[str | None] = mapped_column(Text)  # relative to the scraper DATA_DIR
    role: Mapped[str | None] = mapped_column(String(20))  # advert | syllabus | sample_paper | other
    content_type: Mapped[str | None] = mapped_column(String(100))
    sha256: Mapped[str | None] = mapped_column(String(64))
    size: Mapped[int | None] = mapped_column(Integer)

    listing: Mapped[Listing] = relationship(back_populates="attachments")


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)  # always stored lower-case
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(5), default="en")  # en | ur
    # Master switch: False = no new alerts are matched for this user at all
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    # Channel switches; alerts still land in the website inbox when both are off
    email_alerts: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    push_alerts: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    preference: Mapped["Preference | None"] = relationship(back_populates="user", uselist=False, cascade="all, delete-orphan")
    push_subscriptions: Mapped[list["PushSubscription"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )


class AuthSession(Base):
    """A login. The client holds a random token; only its SHA-256 is stored, so a
    database leak does not hand out working sessions."""

    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)


class PushSubscription(Base):
    """A browser's Web Push endpoint (from PushManager.subscribe on the website)."""

    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(String(200))
    auth: Mapped[str] = mapped_column(String(100))
    user_agent: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="push_subscriptions")


class Preference(TimestampMixin, Base):
    """Empty list / None means "any" for that filter."""

    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)

    kinds: Mapped[list[str]] = mapped_column(ARRAY(String), default=lambda: ["job"])  # job | admission | test
    bps_min: Mapped[int | None] = mapped_column(Integer)
    bps_max: Mapped[int | None] = mapped_column(Integer)
    fields: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # it | engineering | health | ...
    provinces: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)
    age: Mapped[int | None] = mapped_column(Integer)  # the user's age, checked against age limits
    max_experience_years: Mapped[int | None] = mapped_column(Integer)  # 0 = fresh graduate
    program_levels: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # for admissions
    keywords: Mapped[list[str]] = mapped_column(ARRAY(String), default=list)  # e.g. ["computer", "nurse"]

    user: Mapped[User] = relationship(back_populates="preference")


class Alert(Base):
    """One match of one listing for one user: an entry in the user's inbox on the
    website. The unique constraint is the guarantee against duplicate alerts,
    whatever the scheduler does.

    status: pending (not yet notified) -> sent (handed to the user's channels as part
    of a Delivery) | skipped (user switched alerts off before it went out)."""

    __tablename__ = "alerts"
    __table_args__ = (
        # One alert per user, listing, type and deadline. The deadline is only set for
        # reminder / extension alerts, so a reminder for the new last date can go out
        # after an extension; NULLS NOT DISTINCT keeps "new" alerts (deadline NULL) unique.
        UniqueConstraint(
            "user_id",
            "listing_id",
            "alert_type",
            "deadline",
            name="uq_alert_user_listing_type_deadline",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_alerts_user_created", "user_id", "created_at"),  # the inbox, newest first
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(20))  # new | deadline_reminder | deadline_extended | updated
    deadline: Mapped[date | None] = mapped_column(Date)  # the last date a reminder / extension is about
    matched_vacancy_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    matched_program_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    read_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Delivery(Base):
    """One notification on one channel (an email digest, a push) carrying a batch of a
    user's alerts. Sent by the notifier; retried with backoff until MAX_ATTEMPTS.

    status: pending -> sending (claimed by one notifier) -> sent | failed | skipped"""

    __tablename__ = "deliveries"
    __table_args__ = (Index("ix_deliveries_due", "status", "next_attempt_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    channel: Mapped[str] = mapped_column(String(10))  # email | push
    alert_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    status: Mapped[str] = mapped_column(String(10), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Organization(TimestampMixin, Base):
    """A canonical employer, commission or testing body. Curated rows come from
    shared.reference; the rest are created when a listing names a new employer."""

    __tablename__ = "organizations"
    __table_args__ = (Index("ix_organizations_aliases", "aliases", postgresql_using="gin"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    name: Mapped[str] = mapped_column(Text)
    short_name: Mapped[str | None] = mapped_column(String(40))
    kind: Mapped[str] = mapped_column(String(20), default="org")  # commission | testing | force | org | university
    # Normalized spellings that resolve to this row (shared.orgs.normalize_alias)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    official_url: Mapped[str | None] = mapped_column(Text)
    curated: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class HubSlug(Base):
    """A location or field hub page (/jobs/{slug}). `matches` are the raw values in
    listings.provinces / listings.cities / vacancies.field that belong to it."""

    __tablename__ = "hub_slugs"

    slug: Mapped[str] = mapped_column(String(80), primary_key=True)
    kind: Mapped[str] = mapped_column(String(20))  # province | region | city | field
    label: Mapped[str] = mapped_column(Text)
    matches: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    province: Mapped[str | None] = mapped_column(Text)
    nearby: Mapped[list[str]] = mapped_column(ARRAY(String(80)), default=list, server_default="{}")


class DeadlineChange(Base):
    """A listing's last date changed (usually an extension notice)."""

    __tablename__ = "deadline_changes"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    old_date: Mapped[date | None] = mapped_column(Date)
    new_date: Mapped[date | None] = mapped_column(Date)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SavedListing(Base):
    """A listing the user saved ("Reminder lagayein"); one row per user and listing."""

    __tablename__ = "saved_listings"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", name="uq_saved_user_listing"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    remind: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ListingEvent(Base):
    """Transactional outbox: written in the same transaction as the listing change,
    consumed once (FOR UPDATE SKIP LOCKED) to refresh pages, queue alerts and drop
    caches. type: created | deadline_changed | closed | reopened | updated."""

    __tablename__ = "listing_events"
    __table_args__ = (Index("ix_listing_events_unprocessed", "id", postgresql_where="processed_at IS NULL"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    type: Mapped[str] = mapped_column(String(20))
    payload: Mapped[dict] = mapped_column(JSONB, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_error: Mapped[str | None] = mapped_column(Text)
