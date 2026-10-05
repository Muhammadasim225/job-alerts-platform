import time

from shared import security

SECRET = "s3cret"


def test_signed_token_round_trip_and_tampering():
    token = security.sign({"uid": 7}, "unsubscribe", 60, secret=SECRET)
    assert security.verify(token, "unsubscribe", secret=SECRET)["uid"] == 7
    assert security.verify(token, "login", secret=SECRET) is None  # other purpose
    assert security.verify(token, "unsubscribe", secret="other") is None  # other key
    body, mac = token.split(".")
    forged = security.sign({"uid": 8}, "unsubscribe", 60, secret=SECRET).split(".")[0]
    assert security.verify(f"{forged}.{mac}", "unsubscribe", secret=SECRET) is None
    for junk in ("", "abc", "a.b", "..", token + "x"):
        assert security.verify(junk, "unsubscribe", secret=SECRET) is None


def test_signed_token_expires(monkeypatch):
    token = security.sign({"uid": 1}, "unsubscribe", 10, secret=SECRET)
    now = time.time()
    monkeypatch.setattr(security.time, "time", lambda: now + 11)
    assert security.verify(token, "unsubscribe", secret=SECRET) is None


def test_push_endpoint_allowlist():
    ok = [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://web.push.apple.com/QF2",
        "https://wns2-par02p.notify.windows.com/w/?token=x",
    ]
    bad = [
        "http://fcm.googleapis.com/fcm/send/abc",  # not https
        "https://fcm.googleapis.com.evil.com/x",
        "https://evilfcm.googleapis.com.attacker.io/x",
        "https://redis:6379/",
        "https://169.254.169.254/latest/meta-data",
        "https://fcm.googleapis.com:8443/x",
        "not a url",
    ]
    assert all(security.is_push_endpoint_allowed(u) for u in ok)
    assert not any(security.is_push_endpoint_allowed(u) for u in bad)
