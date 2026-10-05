"""Models for the internal API (back office) and the shared preference schema.
Inputs are validated strictly: anything a client sends ends up in matching rules or
user messages."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas import ListingSummary

KINDS = ("job", "admission", "test")
FIELDS = ("it", "engineering", "health", "education", "legal", "finance", "security", "clerical", "support", "admin")
PROVINCES = ("Punjab", "Sindh", "Khyber Pakhtunkhwa", "Balochistan", "Islamabad", "Gilgit-Baltistan", "Azad Kashmir")
LEVELS = ("PhD", "MPhil", "MS", "Pharm-D", "MBBS/BDS", "BSN", "BS", "Diploma", "Certificate / course", "Test")


class PreferenceIn(BaseModel):
    """Empty list / null = any."""

    kinds: list[Literal["job", "admission", "test"]] = Field(default_factory=lambda: ["job"], min_length=1)
    fields: list[Literal[FIELDS]] = []  # type: ignore[valid-type]
    provinces: list[Literal[PROVINCES]] = []  # type: ignore[valid-type]
    program_levels: list[Literal[LEVELS]] = []  # type: ignore[valid-type]
    keywords: list[str] = Field(default_factory=list, max_length=10)
    bps_min: int | None = Field(default=None, ge=1, le=22)
    bps_max: int | None = Field(default=None, ge=1, le=22)
    age: int | None = Field(default=None, ge=14, le=70)
    max_experience_years: int | None = Field(default=None, ge=0, le=40)

    @field_validator("keywords")
    @classmethod
    def clean_keywords(cls, v: list[str]) -> list[str]:
        out = []
        for k in v:
            k = " ".join(k.split())[:40]
            if len(k) >= 2 and k.lower() not in (x.lower() for x in out):
                out.append(k)
        return out

    @model_validator(mode="after")
    def bps_order(self):
        if self.bps_min is not None and self.bps_max is not None and self.bps_min > self.bps_max:
            raise ValueError("bps_min must not be greater than bps_max")
        return self


class PreferenceOut(PreferenceIn):
    model_config = ConfigDict(from_attributes=True)


class AlertOut(BaseModel):
    id: int
    user_id: int
    alert_type: str
    status: str
    listing: ListingSummary
    matched_posts: list[str]
    created_at: datetime
    sent_at: datetime | None


class ReviewItem(BaseModel):
    listing: ListingSummary
    review_reasons: list[str]


class Overview(BaseModel):
    users: int
    active_users: int
    listings_needing_review: int
    alerts_by_status: dict[str, int]
    deliveries_by_status: dict[str, int]  # "email:sent": 120, "push:failed": 2, ...


class TaskQueued(BaseModel):
    task_id: str
    task: str
