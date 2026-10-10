"""Delivery end to end against Postgres, with fake transports."""

from datetime import UTC, date, datetime, timedelta

import pytest
from mailpool import PoolExhausted
from sqlalchemy import select

import service
from channels import GoneError, PermanentError
from shared.models import Alert, Delivery, Listing, PushSubscription, User, Vacancy

FCM = "https://fcm.googleapis.com/fcm/send/"


class FakeMailer:
    def __init__(self, error: Exception | None = None):
        self.sent, self.error = [], error

    def send(self, mail):
        if self.error:
            raise self.error
        self.sent.append(mail)


class FakePusher:
    """Behaviour per endpoint suffix: ok | gone | reject | down."""

    def __init__(self):
        self.sent = []

    def send(self, target, payload):
        kind = target.endpoint.rsplit("/", 1)[1]
        if kind == "gone":
            raise GoneError("410")
        if kind == "reject":
            raise PermanentError("413")
        if kind == "down":
            raise ConnectionError("push service unreachable")
        self.sent.append((target.endpoint, payload))


def _seed(db, devices=(), email_alerts=True, **user_kw) -> int:
    """One user with one pending (settled) alert for a job with two matched posts."""
    with db() as s:
        listing = Listing(
            source="nts",
            external_id="portal-1",
            url="https://portal.nts.org.pk/Alldetail/MQ==",
            status="open",
            kind="job",
            title="Walled City of Lahore Authority",
            last_date=date.today() + timedelta(days=5),
            vacancies=[Vacancy(position=1, post_name="Computer Operator"), Vacancy(position=2, post_name="Assistant")],
        )
        user = User(email="ali@example.com", email_verified_at=datetime.now(UTC), email_alerts=email_alerts, **user_kw)
        user.push_subscriptions = [PushSubscription(endpoint=FCM + d, p256dh="k", auth="a") for d in devices]
        s.add_all([listing, user])
        s.flush()
        s.add(
            Alert(
                user_id=user.id,
                listing_id=listing.id,
                alert_type="new",
                matched_vacancy_ids=[v.id for v in listing.vacancies],
                created_at=datetime.now(UTC) - timedelta(minutes=30),
            )
        )
        return user.id


def _deliveries(db) -> dict[str, Delivery]:
    with db() as s:
        return {d.channel: d for d in s.scalars(select(Delivery))}


def test_email_digest_is_sent_once(db):
    _seed(db)
    [did] = service.dispatch_due()
    mailer = FakeMailer()
    assert service.deliver(did, mailer, FakePusher) == "sent"
    assert service.deliver(did, mailer, FakePusher).startswith("not claimable")  # redelivered message
    [mail] = mailer.sent
    assert mail.to == "ali@example.com" and mail.subject == "New job: Walled City of Lahore Authority"
    assert "Computer Operator" in mail.text and "https://portal.nts.org.pk/Alldetail/MQ==" in mail.html
    assert mail.headers["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert _deliveries(db)["email"].status == "sent"


def test_temporary_email_error_is_retried_permanent_is_not(db):
    _seed(db)
    [did] = service.dispatch_due()
    assert service.deliver(did, FakeMailer(ConnectionError("smtp down")), FakePusher).startswith("error")
    d = _deliveries(db)["email"]
    assert d.status == "pending" and d.attempts == 1 and d.next_attempt_at > datetime.now(UTC)
    assert service.dispatch_due() == []  # backing off

    with db() as s:  # backoff over
        s.get(Delivery, did).next_attempt_at = datetime.now(UTC)
    assert service.dispatch_due() == [did]
    assert service.deliver(did, FakeMailer(PermanentError("550 no such user")), FakePusher).startswith("failed")
    assert _deliveries(db)["email"].status == "failed"


def test_full_email_pool_defers_without_using_an_attempt(db):
    _seed(db)
    [did] = service.dispatch_due()
    tomorrow = datetime.now(UTC) + timedelta(hours=6)
    outcome = service.deliver(did, FakeMailer(PoolExhausted("no email provider can send", tomorrow)), FakePusher)
    assert outcome.startswith("deferred")
    d = _deliveries(db)["email"]
    assert d.status == "pending" and d.attempts == 0 and d.next_attempt_at == tomorrow


def test_push_goes_to_every_device_and_drops_dead_ones(db):
    _seed(db, devices=("ok1", "gone", "reject", "ok2"), email_alerts=False)
    [did] = service.dispatch_due()
    pusher = FakePusher()
    assert service.deliver(did, FakeMailer(), lambda: pusher) == "sent"
    assert [e.rsplit("/", 1)[1] for e, _ in pusher.sent] == ["ok1", "ok2"]
    payload = pusher.sent[0][1]
    assert payload["title"] == "New job: Walled City of Lahore Authority" and payload["url"].endswith(
        "/listings/" + payload["url"].rsplit("/", 1)[1]
    )
    with db() as s:
        left = sorted(p.endpoint.rsplit("/", 1)[1] for p in s.scalars(select(PushSubscription)))
        assert left == ["ok1", "ok2", "reject"]  # the gone endpoint is removed
        assert all(p.last_success_at for p in s.scalars(select(PushSubscription)) if "ok" in p.endpoint)


def test_push_with_only_unreachable_devices_is_retried(db):
    _seed(db, devices=("down", "gone"), email_alerts=False)
    [did] = service.dispatch_due()
    assert service.deliver(did, FakeMailer(), FakePusher).startswith("error")
    assert _deliveries(db)["push"].status == "pending"
    with db() as s:
        assert [p.endpoint.rsplit("/", 1)[1] for p in s.scalars(select(PushSubscription))] == ["down"]


def test_push_with_no_reachable_device_is_skipped(db):
    _seed(db, devices=("gone",), email_alerts=False)
    [did] = service.dispatch_due()
    assert service.deliver(did, FakeMailer(), FakePusher) == "skipped: no reachable push device"
    assert _deliveries(db)["push"].status == "skipped"


def test_switched_off_after_dispatch_is_not_sent(db):
    user_id = _seed(db, devices=("ok",))
    ids = service.dispatch_due()
    assert len(ids) == 2
    with db() as s:
        user = s.get(User, user_id)
        user.email_alerts = False
    mailer, pusher = FakeMailer(), FakePusher()
    outcomes = sorted(service.deliver(i, mailer, lambda: pusher) for i in ids)
    assert outcomes == ["sent", "skipped: email alerts switched off"]
    assert mailer.sent == [] and len(pusher.sent) == 1


@pytest.mark.parametrize("error", [None, ConnectionError("x")])
def test_login_code_email(error):
    mailer = FakeMailer(error)
    if error:
        with pytest.raises(ConnectionError):  # Celery retries the task
            service.send_login_code("ali@example.com", "123456", mailer)
        return
    service.send_login_code("ali@example.com", "123456", mailer)
    [mail] = mailer.sent
    assert mail.subject.startswith("123456") and "123456" in mail.html and "123456" in mail.text


def test_housekeeping(db):
    assert service.housekeeping() == {"sessions": 0, "deliveries": 0}
