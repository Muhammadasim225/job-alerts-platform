"""Per-client rate limiting for the public API, shared through Redis.

Fixed one-minute windows per client IP: `INCR rl:<ip>:<minute>` (+ EXPIRE), so every
API worker and every API server counts against the same budget.

- applies to the public /v1 endpoints only; /v1/internal is API-key protected and
  /health must stay reachable for monitors
- fails open: if Redis is unreachable, requests are served (and a warning logged)
  rather than taking the whole API down with it
- standard headers on every limited response: X-RateLimit-Limit / -Remaining / -Reset,
  and Retry-After on 429

Client IP is request.client.host. Behind a reverse proxy, run uvicorn with
--proxy-headers and FORWARDED_ALLOW_IPS set to the proxy's address, so the real
client IP is used and X-Forwarded-For cannot be spoofed by clients.
"""

import logging
import time
from functools import lru_cache

import redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

log = logging.getLogger("api.ratelimit")

WINDOW_SECONDS = 60


@lru_cache(maxsize=4)
def _redis(url: str) -> redis.Redis:
    return redis.Redis.from_url(url, socket_timeout=0.5, socket_connect_timeout=0.5)


def is_limited_path(path: str) -> bool:
    return path.startswith("/v1/") and not path.startswith("/v1/internal/")


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, limit_per_minute: int, redis_url: str, client=None):
        super().__init__(app)
        self.limit = limit_per_minute
        self.redis_url = redis_url
        self._client = client  # injectable for tests

    def _count(self, key: str) -> int | None:
        try:
            r = self._client or _redis(self.redis_url)
            pipe = r.pipeline()
            pipe.incr(key)
            pipe.expire(key, WINDOW_SECONDS + 5)
            return int(pipe.execute()[0])
        except redis.RedisError as exc:
            log.warning("Rate limiter unavailable, allowing request: %s", exc)
            return None

    async def dispatch(self, request: Request, call_next) -> Response:
        if self.limit <= 0 or not is_limited_path(request.url.path):
            return await call_next(request)

        now = int(time.time())
        window = now - now % WINDOW_SECONDS
        reset_in = window + WINDOW_SECONDS - now
        ip = request.client.host if request.client else "unknown"
        count = self._count(f"rl:{ip}:{window}")
        if count is None:  # fail open
            return await call_next(request)

        headers = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.limit - count)),
            "X-RateLimit-Reset": str(reset_in),
        }
        if count > self.limit:
            return JSONResponse(
                status_code=429,
                content={"detail": f"Rate limit exceeded: {self.limit} requests per minute"},
                headers={**headers, "Retry-After": str(reset_in)},
            )
        response = await call_next(request)
        response.headers.update(headers)
        return response
