"""LastBell API.

  /v1/...            public, read-only: listings, posts, stats (website, SEO pages, partners)
  /v1/auth/...       sign-in by emailed code -> session token
  /v1/me/...         Bearer token: the user's settings, preferences, matches, inbox, push devices
  /v1/internal/...   X-API-Key: back office (overview, review queue, alerts, trigger a scrape)
  /health            readiness (Postgres + Redis), /health/live liveness
  /docs              interactive OpenAPI docs

Run: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from app.config import settings
from app.observability import RequestContextMiddleware, init_sentry, setup_logging
from app.ratelimit import RateLimitMiddleware
from app.routers import auth, health, internal, links, me, public


def create_app() -> FastAPI:
    setup_logging()
    init_sentry()
    app = FastAPI(
        title="LastBell API",
        version="1.0.0",
        description="Pakistan government job and admission listings (NTS first), consolidated from official sources.",
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(RateLimitMiddleware, limit_per_minute=settings.rate_limit_per_minute, redis_url=settings.redis_url)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID", "X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset", "Retry-After"],
    )
    # Added last = outermost: every response (incl. 429 and 500) gets a request id and an access log line
    app.add_middleware(RequestContextMiddleware)

    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(auth.router)
    app.include_router(me.router)
    app.include_router(links.router)
    app.include_router(internal.router)
    return app


app = create_app()
