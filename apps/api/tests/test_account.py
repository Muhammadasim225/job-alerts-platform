"""Website accounts: sign-in by emailed code, settings, preferences, inbox, push devices."""

from datetime import UTC, datetime, timedelta

from conftest import sign_in

from shared import notifications
from shared.matching import queue_alerts_for_listing
from shared.models import Alert, AuthSession, Delivery, Listing, PushSubscription, User
from shared.security import sign

FCM = "https://fcm.googleapis.com/fcm/send/abc123"
KEYS = {
    "p256dh": "BNcRdreALRFXTkOOUHK1EtK2wtaz5Ry4YfYCA_0QTpQtUbVlUls0VJXg7A8u-Ts1XbjhazAkj7I99e8QcYP7DkM",
    "auth": "tBHItJI5svbpez7KI4CCXg",
}


# --- sign-in ---------------------------------------------------------------------


def test_sign_in_creates_account(client, sent_tasks):
    first = sign_in(client, sent_tasks, "Ali@Example.com ")
    assert first["user"]["email"] == "ali@example.com" and first["user"]["preference"]["kinds"] == ["job"]
    name, queue, kwargs = sent_tasks[0]
    assert (name, queue, kwargs["email"]) == ("notify.send_login_code", "notify", "ali@example.com")


def test_second_sign_in_reuses_the_account(client, sent_tasks, fake_redis, db):
    first = sign_in(client, sent_tasks, "ali@example.com")
    fake_redis.flushall()  # a minute later, on another device
    second = sign_in(client, sent_tasks, "ali@example.com")
    assert first["user"]["id"] == second["user"]["id"] and first["token"] != second["token"]
    assert db.query(User).count() == 1 and db.query(AuthSession).count() == 2


def test_wrong_and_reused_codes(client, sent_tasks, fake_redis):
    client.post("/v1/auth/code", json={"email": "sara@example.com"})
    code = sent_tasks[-1][2]["code"]
    wrong = "000000" if code != "000000" else "111111"
    assert client.post("/v1/auth/verify", json={"email": "sara@example.com", "code": wrong}).status_code == 400
    assert client.post("/v1/auth/verify", json={"email": "other@example.com", "code": code}).status_code == 400
    assert client.post("/v1/auth/verify", json={"email": "sara@example.com", "code": code}).status_code == 200
    # single use
    assert client.post("/v1/auth/verify", json={"email": "sara@example.com", "code": code}).status_code == 400


def test_code_is_burned_after_too_many_guesses(client, sent_tasks):
    client.post("/v1/auth/code", json={"email": "brute@example.com"})
    code = sent_tasks[-1][2]["code"]
    wrong = "000000" if code != "000000" else "111111"
    for _ in range(5):
        client.post("/v1/auth/verify", json={"email": "brute@example.com", "code": wrong})
    r = client.post("/v1/auth/verify", json={"email": "brute@example.com", "code": code})
    assert r.status_code == 429  # even the right code is refused now


def test_code_requests_are_throttled_per_address_and_ip(client, fake_redis):
    assert client.post("/v1/auth/code", json={"email": "x@example.com"}).status_code == 202
    r = client.post("/v1/auth/code", json={"email": "x@example.com"})
    assert r.status_code == 429 and r.headers["Retry-After"] == "60"
    for i in range(30):
        last = client.post("/v1/auth/code", json={"email": f"spray{i}@example.com"})
    assert last.status_code == 429  # one IP spraying many addresses


def test_bad_input(client):
    assert client.post("/v1/auth/code", json={"email": "not-an-email"}).status_code == 422
    assert client.post("/v1/auth/verify", json={"email": "a@example.com", "code": "12ab56"}).status_code == 422


def test_me_requires_a_valid_session(client, db, user_client):
    token = user_client.headers.pop("Authorization")
    assert client.get("/v1/me").status_code == 401
    assert client.get("/v1/me", headers={"Authorization": "Bearer nope"}).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": token}).status_code == 200

    db.query(AuthSession).update({"expires_at": datetime.now(UTC) - timedelta(seconds=1)})
    db.flush()
    assert client.get("/v1/me", headers={"Authorization": token}).status_code == 401


def test_logout_ends_only_this_session(client, sent_tasks, fake_redis):
    a = sign_in(client, sent_tasks, "two@example.com")["token"]
    fake_redis.flushall()  # a minute later, on another device
    b = sign_in(client, sent_tasks, "two@example.com")["token"]
    assert client.post("/v1/auth/logout", headers={"Authorization": f"Bearer {a}"}).status_code == 204
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {a}"}).status_code == 401
    assert client.get("/v1/me", headers={"Authorization": f"Bearer {b}"}).status_code == 200


def test_sign_in_disabled_without_secret(client, monkeypatch):
    import app.auth
    from app.config import Settings

    monkeypatch.setattr(app.auth, "settings", Settings(app_secret=""))
    assert client.post("/v1/auth/code", json={"email": "a@example.com"}).status_code == 503


# --- settings & preferences -----------------------------------------------------------


def test_preferences_and_matches(user_client):
    prefs = {"kinds": ["job"], "fields": ["it"], "provinces": ["Punjab"], "age": 22, "keywords": [" Computer ", "computer"]}
    r = user_client.put("/v1/me/preferences", json=prefs)
    assert r.status_code == 200 and r.json()["preference"]["keywords"] == ["Computer"]
    matches = user_client.get("/v1/me/matches").json()
    assert [(m["listing"]["external_id"], m["matched_posts"]) for m in matches] == [("portal-101334", ["Computer Operator"])]


def test_preferences_are_validated(user_client):
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
        assert user_client.put("/v1/me/preferences", json=body).status_code == 422, body


def test_switching_channels_off_cancels_queued_notifications(user_client, db):
    user = db.query(User).filter_by(email="ali@example.com").one()
    db.add(PushSubscription(user_id=user.id, endpoint=FCM, **KEYS))
    _queue_and_dispatch(db, user)
    assert {d.channel: d.status for d in db.query(Delivery)} == {"email": "pending", "push": "pending"}

    r = user_client.patch("/v1/me", json={"email_alerts": False, "name": "  Ali  ", "language": "ur"})
    me = r.json()
    assert (me["email_alerts"], me["push_alerts"], me["name"], me["language"]) == (False, True, "Ali", "ur")
    assert {d.channel: d.status for d in db.query(Delivery)} == {"email": "skipped", "push": "pending"}

    assert user_client.patch("/v1/me", json={"alerts_enabled": False}).json()["alerts_enabled"] is False
    assert {d.status for d in db.query(Delivery)} == {"skipped"}
    assert user_client.patch("/v1/me", json={}).status_code == 200  # nothing sent, nothing changed


def test_delete_account_removes_everything(user_client, db):
    user_id = user_client.me["id"]
    assert user_client.delete("/v1/me").status_code == 204
    assert db.get(User, user_id) is None and db.query(AuthSession).count() == 0
    assert user_client.get("/v1/me").status_code == 401


# --- inbox --------------------------------------------------------------------------


def _queue_and_dispatch(db, user):
    user.preference.kinds = ["job", "admission"]
    db.flush()
    for listing in db.query(Listing).filter_by(status="open"):
        queue_alerts_for_listing(db, listing.id)
    db.query(Alert).update({"created_at": datetime.now(UTC) - timedelta(hours=2)})
    return notifications.dispatch(db)


def test_inbox_pagination_and_read_state(user_client, db):
    user = db.query(User).filter_by(email="ali@example.com").one()
    _queue_and_dispatch(db, user)

    page1 = user_client.get("/v1/me/alerts", params={"limit": 1}).json()
    assert page1["unread"] == 2 and len(page1["items"]) == 1 and page1["next_before"]
    page2 = user_client.get("/v1/me/alerts", params={"limit": 1, "before": page1["next_before"]}).json()
    assert page2["next_before"] is None
    ids = {page1["items"][0]["id"], page2["items"][0]["id"]}
    assert len(ids) == 2
    assert {i["listing"]["kind"] for i in page1["items"] + page2["items"]} == {"job", "admission"}

    assert user_client.post("/v1/me/alerts/read", json={"ids": [page1["items"][0]["id"]]}).status_code == 204
    assert user_client.get("/v1/me/alerts").json()["unread"] == 1
    assert len(user_client.get("/v1/me/alerts", params={"unread_only": True}).json()["items"]) == 1
    user_client.post("/v1/me/alerts/read", json={"all": True})
    assert user_client.get("/v1/me/alerts").json()["unread"] == 0


def test_inbox_shows_only_own_alerts(user_client, db, client):
    other = User(email="other@example.com")
    db.add(other)
    db.flush()
    wcla = db.query(Listing).filter_by(external_id="portal-101334").one()
    db.add(Alert(user_id=other.id, listing_id=wcla.id, alert_type="new", status="sent"))
    db.flush()
    assert user_client.get("/v1/me/alerts").json()["items"] == []
    other_alert = db.query(Alert).filter_by(user_id=other.id).one()
    user_client.post("/v1/me/alerts/read", json={"ids": [other_alert.id]})
    db.refresh(other_alert)
    assert other_alert.read_at is None  # cannot touch someone else's inbox


# --- push & email links --------------------------------------------------------------------


def test_push_subscription_lifecycle(user_client, db):
    assert user_client.get("/v1/push/public-key").json() == {"public_key": "BTestPublicKey"}
    sub = {"endpoint": FCM, "keys": KEYS}
    assert user_client.post("/v1/me/push-subscriptions", json=sub).json() == {"push_devices": 1}
    assert user_client.post("/v1/me/push-subscriptions", json=sub).json() == {"push_devices": 1}  # idempotent
    assert user_client.get("/v1/me").json()["push_devices"] == 1
    assert user_client.request("DELETE", "/v1/me/push-subscriptions", json={"endpoint": FCM}).status_code == 204
    assert user_client.get("/v1/me").json()["push_devices"] == 0


def test_push_endpoint_must_be_a_real_push_service(user_client):
    for endpoint in ("https://evil.example/x", "http://fcm.googleapis.com/x", "https://redis:6379/"):
        r = user_client.post("/v1/me/push-subscriptions", json={"endpoint": endpoint, "keys": KEYS})
        assert r.status_code == 422, endpoint
    r = user_client.post("/v1/me/push-subscriptions", json={"endpoint": FCM, "keys": {"p256dh": "<script>", "auth": "x"}})
    assert r.status_code == 422


def test_one_click_email_unsubscribe(client, db):
    user = User(email="mail@example.com")
    db.add(user)
    db.flush()
    token = sign({"uid": user.id}, "unsubscribe", 3600)
    assert client.post("/v1/email/unsubscribe", params={"token": token}).json() == {"email_alerts": False}
    db.refresh(user)
    assert user.email_alerts is False
    assert client.post("/v1/email/unsubscribe", params={"token": token + "x"}).status_code == 400
    login = sign({"uid": user.id}, "login", 3600)  # a token for something else
    assert client.post("/v1/email/unsubscribe", params={"token": login}).status_code == 400
