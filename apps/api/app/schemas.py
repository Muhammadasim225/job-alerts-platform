"""Response / request models: the API contract for the website, bot and partners.

Internal-only columns (local file paths, raw snapshots, review notes) are never in
public responses.
"""

from datetime import date, datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class Page(BaseModel, Generic[T]):
    items: list[T]
    total: int
    limit: int
    offset: int


class SyllabusItem(BaseModel):
    subject: str
    weight_percent: int | None = None


class VacancyOut(ORM):
    id: int
    position: int
    post_name: str
    bps: list[int]
    bps_min: int | None
    bps_max: int | None
    field: str | None
    total_posts: int | None
    total_posts_shared: bool
    fee_pkr: int | None
    age_min: int | None
    age_max: int | None
    qualification: str | None
    experience: str | None
    experience_years_min: int | None
    mode: str | None
    test_syllabus: list[SyllabusItem]


class ProgramOut(ORM):
    id: int
    position: int
    name: str
    level: str | None
    subjects: list[str]
    duration: str | None
    eligibility: list[str]
    age_min: int | None
    age_max: int | None
    fee_pkr: int | None
    mode: str | None
    via_nts: bool
    test_syllabus: list[SyllabusItem]


class AttachmentOut(ORM):
    name: str | None
    url: str
    role: str | None
    content_type: str | None


class ListingSummary(ORM):
    id: int
    source: str
    external_id: str
    url: str
    status: str
    kind: str
    title: str
    organization: str | None
    last_date: date | None
    days_left: int | None = None
    is_expired: bool
    provinces: list[str]
    cities: list[str]
    posts_count: int = 0  # vacancies (jobs) or programmes (admissions/tests)
    total_seats: int | None = None
    bps_min: int | None = None
    bps_max: int | None = None
    fields: list[str] = []
    registration_open: bool | None = None
    first_seen_at: datetime


class ListingDetail(ListingSummary):
    department: str | None
    project_code: str | None
    announce_date: date | None
    test_date: date | None = Field(description="Tentative; NTS often changes it")
    advert_facts: dict
    vacancies: list[VacancyOut]
    programs: list[ProgramOut]
    attachments: list[AttachmentOut]
    verified: bool
    updated_at: datetime


class VacancyHit(VacancyOut):
    """A post with the listing it belongs to (post search)."""

    listing: ListingSummary


class Stats(BaseModel):
    open_listings: dict[str, int]
    open_posts: int
    open_seats: int
    closing_in_7_days: int
    last_scraped_at: datetime | None


class FacetValue(BaseModel):
    value: str
    count: int


class Filters(BaseModel):
    kinds: list[FacetValue]
    provinces: list[FacetValue]
    cities: list[FacetValue]
    fields: list[FacetValue]
    program_levels: list[FacetValue]
