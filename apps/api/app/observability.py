"""Logging, request IDs, timing and Sentry for the API.

Every request gets an ID (the client's X-Request-ID if it sent a sane one, else a new
one). It is returned in the X-Request-ID response header, put on every log line of
that request, and attached to Sentry events, so a user's error report can be traced
to the exact log lines.

Access log, one line per request (logfmt, easy to grep and to ship to a log service):
    method=GET path=/v1/listings status=200 duration_ms=12.4 request_id=...
Requests slower than SLOW_REQUEST_MS are logged at WARNING.
"""

import logging
import os
import re
import time
import uuid
from contextvars import ContextVar

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")
log = logging.getLogger("api.access")

SLOW_REQUEST_MS = float(os.getenv("SLOW_REQUEST_MS", "1000"))
_SAFE_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def setup_logging() -> None:
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    handler = logging.StreamHandler()
    handler.addFilter(RequestIdFilter())
    handler.setFormatter(
        logging.Formatter("%(asctime)s level=%(levelname)s logger=%(name)s request_id=%(request_id)s %(message)s")
    )
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # uvicorn's own access log would duplicate ours
    logging.getLogger("uvicorn.access").disabled = True


def init_sentry() -> bool:
    dsn = os.getenv("SENTRY_DSN")
    if not dsn:
        return False
    import sentry_sdk

    sentry_sdk.init(
        dsn=dsn,
        environment=os.getenv("SENTRY_ENVIRONMENT", "development"),
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.0")),
        send_default_pii=False,  # no IPs / headers / bodies of users in Sentry
    )
    return True


class RequestContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        incoming = request.headers.get("X-Request-ID", "")
        rid = incoming if _SAFE_ID.match(incoming) else uuid.uuid4().hex
        token = request_id_var.set(rid)
        try:
            import sentry_sdk

            sentry_sdk.set_tag("request_id", rid)
        except ImportError:
            pass
        start = time.perf_counter()
        status = 500
        try:
            try:
                response = await call_next(request)
            except Exception as exc:
                # Unhandled error: log + report it here, inside the request context, so the
                # 500 still carries the request id (Starlette's own error handler runs outside
                # every middleware). No details leak to the client.
                logging.getLogger("api").exception("Unhandled error on %s %s", request.method, request.url.path)
                try:
                    import sentry_sdk

                    sentry_sdk.capture_exception(exc)
                except ImportError:
                    pass
                response = JSONResponse(status_code=500, content={"detail": "Internal server error", "request_id": rid})
            status = response.status_code
            response.headers["X-Request-ID"] = rid
            return response
        finally:
            ms = (time.perf_counter() - start) * 1000
            level = logging.WARNING if ms >= SLOW_REQUEST_MS else logging.INFO
            if request.url.path not in ("/health", "/health/live") or status >= 500:
                log.log(level, "method=%s path=%s status=%s duration_ms=%.1f", request.method, request.url.path, status, ms)
            request_id_var.reset(token)
