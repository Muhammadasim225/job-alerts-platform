from shared.matching import queue_alerts_for_listing
from shared.models import Listing, Preference, User


def test_internal_requires_key(client):
    assert client.get("/v1/internal/admin/overview").status_code == 401
    assert client.get("/v1/internal/admin/overview", headers={"X-API-Key": "wrong"}).status_code == 401


def test_overview_and_alert_list(internal, db):
    user = User(email="it@example.com", preference=Preference(kinds=["job"], fields=["it"]))
    db.add(user)
    db.flush()
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    assert queue_alerts_for_listing(db, wcla.id) == 1

    [a] = internal.get("/v1/internal/alerts", params={"status": "pending"}).json()
    assert a["user_id"] == user.id and a["matched_posts"] == ["Computer Operator"]
    assert a["listing"]["external_id"] == "portal-101334"
    assert internal.get("/v1/internal/alerts", params={"status": "sent"}).json() == []
    assert internal.get("/v1/internal/alerts", params={"status": "bogus"}).status_code == 422

    o = internal.get("/v1/internal/admin/overview").json()
    assert o["users"] == 1 and o["active_users"] == 1 and o["alerts_by_status"] == {"pending": 1}
    assert o["deliveries_by_status"] == {}


def test_review_queue_and_verify(internal, db):
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    wcla.needs_review, wcla.review_reasons = True, ["posts read from OCR"]
    db.flush()
    queue = internal.get("/v1/internal/admin/review-queue").json()
    assert queue[0]["listing"]["external_id"] == "portal-101334" and queue[0]["review_reasons"] == ["posts read from OCR"]
    assert internal.post(f"/v1/internal/admin/listings/{wcla.id}/verify").status_code == 204
    assert internal.get("/v1/internal/admin/review-queue").json() == []


def test_trigger_scrape_uses_scrape_queue(internal, sent_tasks):
    r = internal.post("/v1/internal/admin/scrape", params={"force": True})
    assert r.status_code == 202 and r.json()["task_id"] == "t-1"
    assert sent_tasks == [("tasks.scrape_nts", "scrape", {"force": True})]
