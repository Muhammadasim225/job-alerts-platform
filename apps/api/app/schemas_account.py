"""Models for the signed-in user's endpoints (/v1/auth, /v1/me) and push/email links."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas import ListingSummary
from app.schemas_internal import PreferenceOut


class EmailIn(BaseModel):
    email: EmailStr

    @field_validator("email")
    @classmethod
    def lower(cls, v: str) -> str:
        return v.strip().lower()


class CodeIn(EmailIn):
    code: str = Field(pattern=r"^\d{6}$")


class CodeSent(BaseModel):
    sent: bool = True
    expires_in: int


class SessionOut(BaseModel):
    token: str  # shown once; send as "Authorization: Bearer <token>"
    expires_at: datetime
    user: "MeOut"


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None
    language: str
    alerts_enabled: bool  # master switch (is_active)
    email_alerts: bool
    push_alerts: bool
    push_devices: int = 0
    created_at: datetime
    preference: PreferenceOut | None


class MePatch(BaseModel):
    """Only the fields sent are changed."""

    name: str | None = Field(default=None, max_length=100)
    language: Literal["en", "ur"] | None = None
    alerts_enabled: bool | None = None
    email_alerts: bool | None = None
    push_alerts: bool | None = None


class MatchOut(BaseModel):
    listing: ListingSummary
    matched_posts: list[str]


class InboxItem(BaseModel):
    id: int
    alert_type: str  # new | deadline_reminder | updated
    created_at: datetime
    read: bool
    listing: ListingSummary
    matched_posts: list[str]


class Inbox(BaseModel):
    items: list[InboxItem]
    unread: int
    next_before: int | None  # pass as ?before= for the next (older) page


class MarkRead(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=200)
    all: bool = False


class PushKeys(BaseModel):
    p256dh: str = Field(min_length=20, max_length=200, pattern=r"^[A-Za-z0-9_\-=]+$")
    auth: str = Field(min_length=8, max_length=100, pattern=r"^[A-Za-z0-9_\-=]+$")


class PushSubscriptionIn(BaseModel):
    """The JSON of a browser PushSubscription (subscription.toJSON())."""

    endpoint: str = Field(max_length=2000)
    keys: PushKeys


class PushEndpoint(BaseModel):
    endpoint: str = Field(max_length=2000)


class PushKey(BaseModel):
    public_key: str


class EmailPrefsOut(BaseModel):
    email_alerts: bool


SessionOut.model_rebuild()
