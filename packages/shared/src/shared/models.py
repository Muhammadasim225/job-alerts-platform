"""PostgreSQL schema.

Designed from the real normalized NTS records (apps/scrapers/data/normalized):

  listings      one advert/announcement on a source (NTS project), job or admission
  vacancies     posts of a job listing (BPS, seats, qualification, ...)
  programs      programmes of an admission/test listing (level, subjects, eligibility, ...)
  attachments   advert / syllabus / sample-paper files of a listing
  users         Telegram subscribers
  preferences   what a user wants to be alerted about
  alerts        every alert queued/sent, unique per (user, listing, type) so nothing is sent twice
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
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
    organization: Mapped[str | None] = mapped_column(Text)
    department: Mapped[str | None] = mapped_column(Text)
    project_code: Mapped[str | None] = mapped_column(String(40))

    last_date: Mapped[date | None] = mapped_column(Date, index=True)
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
    telegram_chat_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    name: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(5), default="en")  # en | ur
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)  # False after /stop

    preference: Mapped["Preference | None"] = relationship(
        back_populates="user", uselist=False, cascade="all, delete-orphan"
    )


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
    """One message to one user about one listing. The unique constraint is the
    guarantee against duplicate alerts, whatever the scheduler does."""

    __tablename__ = "alerts"
    __table_args__ = (UniqueConstraint("user_id", "listing_id", "alert_type", name="uq_alert_user_listing_type"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    listing_id: Mapped[int] = mapped_column(ForeignKey("listings.id", ondelete="CASCADE"), index=True)
    alert_type: Mapped[str] = mapped_column(String(20))  # new | deadline_reminder | updated
    matched_vacancy_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    matched_program_ids: Mapped[list[int]] = mapped_column(ARRAY(Integer), default=list)
    # pending -> sending (claimed by one sender) -> sent | failed; skipped = not sent on purpose
    status: Mapped[str] = mapped_column(String(10), default="pending", index=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    attempts: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
