from shared.matching import queue_alerts_for_listing
from shared.models import Listing


def test_internal_requires_key(client):
    assert client.get("/v1/internal/admin/overview").status_code == 401
    assert client.get("/v1/internal/admin/overview", headers={"X-API-Key": "wrong"}).status_code == 401


def test_user_lifecycle_and_matches(internal):
    r = internal.put("/v1/internal/users/777", json={"name": "Ahmad", "language": "ur"})
    assert r.status_code == 200 and r.json()["preference"]["kinds"] == ["job"]

    prefs = {"kinds": ["job"], "fields": ["it"], "provinces": ["Punjab"], "age": 22, "keywords": [" Computer ", "computer"]}
    r = internal.put("/v1/internal/users/777/preferences", json=prefs)
    assert r.status_code == 200 and r.json()["preference"]["keywords"] == ["Computer"]

    matches = internal.get("/v1/internal/users/777/matches").json()
    assert [(m["listing"]["external_id"], m["matched_posts"]) for m in matches] == [("portal-101334", ["Computer Operator"])]

    assert internal.post("/v1/internal/users/777/unsubscribe").json()["is_active"] is False
    assert internal.post("/v1/internal/users/777/resubscribe").json()["is_active"] is True
    assert internal.get("/v1/internal/users/123456").status_code == 404


def test_preferences_are_validated(internal):
    internal.put("/v1/internal/users/778", json={})
    bad = [
        {"kinds": []},
        {"kinds": ["jobs"]},
        {"fields": ["astronaut"]},
        {"provinces": ["Mars"]},
        {"bps_min": 25},
        {"bps_min": 18, "bps_max": 11},
        {"age": 5},
        {"keywords": ["x"] * 11},
    ]
    for body in bad:
        assert internal.put("/v1/internal/users/778/preferences", json=body).status_code == 422, body


def test_alert_outbox_flow(internal, db):
    internal.put("/v1/internal/users/779", json={"name": "IT"})
    internal.put("/v1/internal/users/779/preferences", json={"kinds": ["job"], "fields": ["it"]})
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    assert queue_alerts_for_listing(db, wcla.id) == 1

    claimed = internal.post("/v1/internal/alerts/claim").json()
    assert len(claimed) == 1
    a = claimed[0]
    assert a["telegram_chat_id"] == 779 and a["matched_posts"] == ["Computer Operator"]
    assert a["listing"]["external_id"] == "portal-101334" and a["status"] == "sending"
    assert internal.post("/v1/internal/alerts/claim").json() == []  # nothing left to hand out

    assert internal.post(f"/v1/internal/alerts/{a['id']}/sent").status_code == 204
    assert internal.get("/v1/internal/alerts", params={"status": "sent"}).json()[0]["id"] == a["id"]
    assert internal.post("/v1/internal/alerts/999999/sent").status_code == 404


def test_unsubscribe_skips_pending_alerts(internal, db):
    internal.put("/v1/internal/users/780", json={})
    internal.put("/v1/internal/users/780/preferences", json={"kinds": ["job"]})
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    queue_alerts_for_listing(db, wcla.id)
    internal.post("/v1/internal/users/780/unsubscribe")
    assert internal.post("/v1/internal/alerts/claim").json() == []
    assert internal.get("/v1/internal/admin/overview").json()["alerts_by_status"]["skipped"] == 1


def test_review_queue_and_verify(internal, db):
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    wcla.needs_review, wcla.review_reasons = True, ["posts read from OCR"]
    db.flush()
    queue = internal.get("/v1/internal/admin/review-queue").json()
    assert queue[0]["listing"]["external_id"] == "portal-101334" and queue[0]["review_reasons"] == ["posts read from OCR"]
    assert internal.post(f"/v1/internal/admin/listings/{wcla.id}/verify").status_code == 204
    assert internal.get("/v1/internal/admin/review-queue").json() == []


def test_trigger_scrape_uses_scrape_queue(internal, monkeypatch):
    sent = {}

    def fake_send(name, queue, kwargs=None):
        sent.update(name=name, queue=queue, kwargs=kwargs)
        return "task-123"

    import app.tasks_client

    monkeypatch.setattr(app.tasks_client, "send_task", fake_send)
    r = internal.post("/v1/internal/admin/scrape", params={"force": True})
    assert r.status_code == 202 and r.json()["task_id"] == "task-123"
    assert sent == {"name": "tasks.scrape_nts", "queue": "scrape", "kwargs": {"force": True}}
