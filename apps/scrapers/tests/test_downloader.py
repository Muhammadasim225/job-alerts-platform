import fakeredis
import pytest

from nts import dedup, downloader

URL = "https://nts.org.pk/Test&Products/Announced/06_26/ISMO_June2026_Online/ISMO_Ad.pdf"


class FakeResponse:
    def __init__(self, headers):
        self.headers = headers

    def raise_for_status(self):
        pass


class FakeSession:
    def __init__(self):
        self.headers_for_head = {}
        self.calls = 0

    def head(self, url, **kwargs):
        self.calls += 1
        return FakeResponse(self.headers_for_head)


@pytest.fixture
def session(monkeypatch):
    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(dedup, "get_redis", lambda: r)
    s = FakeSession()
    monkeypatch.setattr(downloader, "_get_session", lambda: s)
    return s


def test_never_downloaded_file_is_not_checked(session):
    assert downloader.remote_file_changed(URL) is False
    assert session.calls == 0


def test_replaced_file_is_detected(session):
    dedup.remember_file(URL, "sha-old")
    dedup.remember_file_meta(URL, {"etag": '"a1"', "last_modified": "Thu, 24 Sep 2026 07:13:25 GMT", "length": "4099296"})

    session.headers_for_head = {"ETag": '"a1"', "Last-Modified": "Thu, 24 Sep 2026 07:13:25 GMT", "Content-Length": "4099296"}
    assert downloader.remote_file_changed(URL) is False

    # Corrigendum uploaded under the same name
    session.headers_for_head = {"ETag": '"b2"', "Last-Modified": "Mon, 28 Sep 2026 09:00:00 GMT", "Content-Length": "4100000"}
    assert downloader.remote_file_changed(URL) is True


def test_old_downloads_get_a_baseline_instead_of_a_false_alarm(session):
    dedup.remember_file(URL, "sha-old")  # downloaded before headers were recorded
    session.headers_for_head = {"ETag": '"a1"', "Content-Length": "10"}
    assert downloader.remote_file_changed(URL) is False
    assert dedup.known_file_meta(URL) == {"etag": '"a1"', "length": "10"}
    session.headers_for_head = {"ETag": '"b2"', "Content-Length": "10"}
    assert downloader.remote_file_changed(URL) is True


def test_failed_head_counts_as_unchanged(session, monkeypatch):
    import requests

    dedup.remember_file(URL, "sha-old")
    dedup.remember_file_meta(URL, {"etag": '"a1"'})

    def boom(url, **kwargs):
        raise requests.ConnectionError("down")

    monkeypatch.setattr(session, "head", boom)
    assert downloader.remote_file_changed(URL) is False
