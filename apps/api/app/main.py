"""SarkariAlert API.

  /v1/...            public, read-only: listings, posts, stats (website, SEO pages, partners)
  /v1/internal/...   X-API-Key: users & preferences, alert queue, admin (bot, back office)
  /health            readiness (Postgres + Redis), /health/live liveness
  /docs              interactive OpenAPI docs

Run: uvicorn app.main:app --host 0.0.0.0 --port 8000
"""

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.routers import health, internal, public

log = logging.getLogger("api")


def create_app() -> FastAPI:
    app = FastAPI(
        title="SarkariAlert API",
        version="1.0.0",
        description="Pakistan government job and admission listings (NTS first), consolidated from official sources.",
    )
    app.add_middleware(GZipMiddleware, minimum_size=1000)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):  # noqa: ARG001
        # Never leak stack traces or SQL to clients; the details go to the logs / Sentry.
        log.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    app.include_router(health.router)
    app.include_router(public.router)
    app.include_router(internal.router)
    return app


app = create_app()
