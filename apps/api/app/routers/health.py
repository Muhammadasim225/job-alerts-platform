"""Liveness / readiness for Docker and uptime monitors (UptimeRobot)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text

from app.auth import get_redis
from app.deps import DB

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict:
    """The process is up (no dependencies checked)."""
    return {"status": "ok"}


@router.get("/health")
def ready(response: Response, db=DB, r=Depends(get_redis)) -> dict:
    """Ready to serve: Postgres and Redis reachable. 503 if either is down."""
    checks = {}
    try:
        db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as exc:
        checks["database"] = f"error: {type(exc).__name__}"
    try:
        r.ping()  # shared client with 2 s connect/read timeouts, no new pool per check
        checks["redis"] = "ok"
    except Exception as exc:
        checks["redis"] = f"error: {type(exc).__name__}"
    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "ok" if healthy else "degraded", "checks": checks}
