import fakeredis
import redis
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ratelimit import RateLimitMiddleware


def make_client(limit, client=None):
    app = FastAPI()
    app.add_middleware(RateLimitMiddleware, limit_per_minute=limit, redis_url="redis://unused", client=client)

    @app.get("/v1/listings")
    def listings():
        return {"ok": True}

    @app.get("/v1/internal/admin/overview")
    def internal():
        return {"ok": True}

    @app.get("/health")
    def health():
        return {"ok": True}

    return TestClient(app)


def test_limits_public_endpoints_per_client():
    c = make_client(3, fakeredis.FakeRedis())
    responses = [c.get("/v1/listings") for _ in range(4)]
    assert [r.status_code for r in responses] == [200, 200, 200, 429]
    assert responses[0].headers["X-RateLimit-Limit"] == "3"
    assert responses[2].headers["X-RateLimit-Remaining"] == "0"
    blocked = responses[3]
    assert 0 < int(blocked.headers["Retry-After"]) <= 60 and "Rate limit" in blocked.json()["detail"]


def test_internal_and_health_are_not_limited():
    c = make_client(1, fakeredis.FakeRedis())
    assert all(c.get("/v1/internal/admin/overview").status_code == 200 for _ in range(5))
    assert all(c.get("/health").status_code == 200 for _ in range(5))


def test_fails_open_when_redis_is_down():
    class Down(fakeredis.FakeRedis):
        def pipeline(self, *a, **k):
            raise redis.ConnectionError("down")

    c = make_client(1, Down())
    assert [c.get("/v1/listings").status_code for _ in range(3)] == [200, 200, 200]


def test_zero_disables():
    c = make_client(0, fakeredis.FakeRedis())
    assert all(c.get("/v1/listings").status_code == 200 for _ in range(10))
