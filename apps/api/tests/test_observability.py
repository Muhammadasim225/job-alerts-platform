import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.observability import RequestContextMiddleware


def make_app():
    app = FastAPI()
    app.add_middleware(RequestContextMiddleware)

    @app.get("/v1/ok")
    def ok():
        return {"ok": True}

    return app


def test_request_id_generated_and_returned(caplog):
    c = TestClient(make_app())
    with caplog.at_level(logging.INFO, logger="api.access"):
        r = c.get("/v1/ok")
    rid = r.headers["X-Request-ID"]
    assert len(rid) == 32
    line = next(rec for rec in caplog.records if rec.name == "api.access")
    assert "path=/v1/ok status=200 duration_ms=" in line.getMessage()


def test_client_request_id_kept_only_if_safe():
    c = TestClient(make_app())
    assert c.get("/v1/ok", headers={"X-Request-ID": "abc-123-XYZ"}).headers["X-Request-ID"] == "abc-123-XYZ"
    unsafe = c.get("/v1/ok", headers={"X-Request-ID": "x\r\nSet-Cookie: a"}).headers["X-Request-ID"]
    assert unsafe != "x\r\nSet-Cookie: a" and len(unsafe) == 32


def test_full_app_500_includes_request_id(client, monkeypatch):
    import app.queries

    def boom(*a, **k):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(app.queries, "stats", boom)
    from fastapi.testclient import TestClient as TC

    from app.main import app as real_app

    r = TC(real_app, raise_server_exceptions=False).get("/v1/stats")
    assert r.status_code == 500 and r.json()["detail"] == "Internal server error"
    assert r.json()["request_id"] == r.headers["X-Request-ID"]
    assert "db exploded" not in r.text
