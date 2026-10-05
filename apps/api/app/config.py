"""API settings from the environment (repo-root .env via docker compose)."""

import os
from dataclasses import dataclass, field


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in (value or "").split(",") if v.strip()]


@dataclass(frozen=True)
class Settings:
    database_url: str = field(default_factory=lambda: os.getenv("DATABASE_URL", ""))
    redis_url: str = field(default_factory=lambda: os.getenv("REDIS_URL", "redis://localhost:6379/0"))
    # Internal endpoints (users, alerts, admin) need this in the X-API-Key header.
    # Empty = internal endpoints are disabled (never open by accident).
    internal_api_key: str = field(default_factory=lambda: os.getenv("INTERNAL_API_KEY", ""))
    cors_origins: list[str] = field(default_factory=lambda: _csv(os.getenv("CORS_ORIGINS", "http://localhost:3000")))
    # Public /v1 requests per client IP per minute (0 disables)
    rate_limit_per_minute: int = field(default_factory=lambda: int(os.getenv("RATE_LIMIT_PER_MINUTE", "120")))
    # Signs login codes and email links. Empty = sign-in is disabled.
    app_secret: str = field(default_factory=lambda: os.getenv("APP_SECRET", ""))
    session_days: int = field(default_factory=lambda: int(os.getenv("SESSION_DAYS", "60")))
    # Web Push application server key (public half), handed to browsers
    vapid_public_key: str = field(default_factory=lambda: os.getenv("VAPID_PUBLIC_KEY", ""))
    default_page_size: int = 20
    max_page_size: int = 100


settings = Settings()
