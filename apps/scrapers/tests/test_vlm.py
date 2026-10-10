"""deAPI client against a fake HTTP session (no network, no key needed)."""

import pytest
from PIL import Image

import config
from nts import deapi_keys, vlm
from nts.tables import markup_to_text, rows_from_tables, tables_from_markup

WCLA_VLM_OUTPUT = """PUNJAB WALLED CITIES AND HERITAGE AREAS AUTHORITY
SITUATIONS VACANT
<table>
<tr><th>Sr. No.</th><th>Name of the Post</th><th>BPS</th><th>No. of Posts</th><th>Qualification and Experience</th></tr>
<tr><td>1</td><td>Deputy Director (Design)</td><td>18</td><td>1</td><td>(i) BSc (Civil Engineering) from a University recognized by HEC, and (ii) having five years relevant experience</td></tr>
<tr><td>2</td><td>Computer Operator</td><td>12</td><td>2</td><td>Intermediate + MS Office / ICS and With 40 wpm speed on computer.</td></tr>
<tr><td></td><td></td><td></td><td>3</td><td></td></tr>
</table>
AGE LIMIT: For Post in Sr No 1 is 26 to 40"""


class Resp:
    def __init__(self, body, status=200):
        self._body, self.status_code, self.text = body, status, str(body)

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.posted = []

    def post(self, url, **kw):
        self.posted.append((url, kw["data"]))
        return Resp({"data": {"request_id": "req-1"}})

    def get(self, url, **kw):
        status = self.statuses.pop(0)
        return Resp({"data": {"status": status, "result": WCLA_VLM_OUTPUT if status == "done" else None}})


@pytest.fixture
def configured(monkeypatch, tmp_path):
    import fakeredis

    from nts import dedup

    # Never touch the real local Redis: its pause flag / budget would leak into tests
    monkeypatch.setattr(dedup, "get_redis", lambda r=fakeredis.FakeRedis(decode_responses=True): r)
    monkeypatch.setattr(config, "DEAPI_API_KEYS", ["test-key"])
    monkeypatch.setattr(config, "VLM_CACHE_DIR", tmp_path / "vlm")
    monkeypatch.setattr(vlm, "_take_budget", lambda: True)
    monkeypatch.setattr(vlm, "POLL_SECONDS", 0)


def test_ocr_polls_until_done_and_caches(configured):
    img = Image.new("RGB", (300, 200), "white")
    session = FakeSession(["pending", "processing", "done"])
    assert vlm.ocr_image(img, session=session) == WCLA_VLM_OUTPUT
    url, data = session.posted[0]
    assert url.endswith("/api/v2/images/ocr") and data["model"] == "Nanonets_Ocr_S_F16"
    # Same image again: served from cache, no second (paid) request
    assert vlm.ocr_image(img, session=FakeSession([])) == WCLA_VLM_OUTPUT


def test_job_error_raises(configured):
    with pytest.raises(vlm.VlmError):
        vlm.ocr_image(Image.new("RGB", (10, 10)), session=FakeSession(["error"]))


def test_unconfigured_is_off(monkeypatch):
    monkeypatch.setattr(config, "DEAPI_API_KEYS", [])
    assert not vlm.vlm_available()


def test_vlm_html_table_becomes_posts():
    tables = tables_from_markup(WCLA_VLM_OUTPUT)
    rows = rows_from_tables(tables)
    assert [r["name"] for r in rows] == ["Deputy Director (Design)", "Computer Operator"]
    assert rows[1]["total_posts"] == 2 and rows[1]["details"] == "BPS-12"
    assert "Civil Engineering" in rows[0]["qualification"]
    text = markup_to_text(WCLA_VLM_OUTPUT)
    assert "Computer Operator | 12 | 2" in text and "<td>" not in text


def test_rowspan_and_markdown_tables():
    html = """<table><tr><th>Name of Post</th><th>No. of Positions</th><th>Age Limit</th></tr>
    <tr><td>Engineer-II</td><td rowspan="2">60</td><td>30 Years</td></tr>
    <tr><td>Engineer-I</td><td>28 Years</td></tr></table>"""
    rows = rows_from_tables(tables_from_markup(html))
    assert [(r["name"], r["total_posts"], r["age_limit"]) for r in rows] == [
        ("Engineer-II", 60, "30 Years"),
        ("Engineer-I", 60, "28 Years"),
    ]
    md = "| Programs | Eligibility Criteria |\n|---|---|\n| Generic BSN (04 years) | FSc Pre-Medical 50% |\n"
    assert rows_from_tables(tables_from_markup(md)) == [
        {"name": "Generic BSN (04 years)", "qualification": "FSc Pre-Medical 50%"}
    ]


def test_table_split_across_strips_is_merged():
    strip1 = "<table><tr><th>Name of Post</th><th>BPS</th><th>No. of Posts</th></tr><tr><td>Clerk</td><td>11</td><td>3</td></tr></table>"
    strip2 = "<table><tr><td>Driver</td><td>4</td><td>2</td></tr></table>"
    rows = rows_from_tables(tables_from_markup(strip1 + "\n" + strip2))
    assert [(r["name"], r["details"], r["total_posts"]) for r in rows] == [("Clerk", "BPS-11", 3), ("Driver", "BPS-4", 2)]


def test_tall_image_split_into_strips_on_blank_rows():
    from PIL import ImageDraw

    img = Image.new("RGB", (1000, 2000), "white")
    d = ImageDraw.Draw(img)
    for y in range(0, 2000, 40):  # a text-like line every 40 px, 20 px tall
        d.rectangle((50, y, 950, y + 20), fill="black")
    strips = vlm.split_strips(img)
    assert len(strips) >= 3
    assert all(s.height <= vlm.MAX_STRIP_HEIGHT for s in strips)
    assert sum(s.height for s in strips) == 2000
    # every cut lands in a gap between "lines", never through one
    top = 0
    for s in strips[:-1]:
        top += s.height
        assert top % 40 > 20


def test_too_large_strip_is_halved_and_retried(configured, monkeypatch):
    calls = []

    def fake_one(image, session):
        calls.append(image.height)
        if image.height > 300:
            raise vlm.InputTooLarge("too much text")
        return f"part{len(calls)}"

    monkeypatch.setattr(vlm, "_ocr_one", fake_one)
    out = vlm.ocr_image(Image.new("RGB", (800, 600), "white"))
    assert calls[0] == 600 and all(h <= 300 for h in calls[1:])
    assert out.count("part") == 2


def test_429_is_waited_out(configured, monkeypatch):
    monkeypatch.setattr(vlm.time, "sleep", lambda s: None)
    responses = [Resp({}, 429), Resp({}, 429), Resp({"ok": True}, 200)]
    resp = vlm._rate_limited(lambda k: responses.pop(0), deapi_keys.keys()[0])
    assert resp.status_code == 200


def test_image_descriptions_dropped():
    raw = "<img>A person in a blue uniform is standing next to a signboard.</img>\nOPEN SESSION 2026-27\nAge Limit: 14-35 Years"
    text = markup_to_text(raw)
    assert "uniform" not in text and "Age Limit: 14-35 Years" in text
    from nts.advert_info import registration_open

    assert registration_open(text)


def test_merge_keeps_vlm_and_adds_missed_badges():
    from nts.parser import merge_ocr_texts

    vlm_text = "How to Apply\nAge 16 to 25 years"
    tess = "9 NASTP Kharian\nAge 16 to 25 years\nMerit Based\nScholarship\n‘5 bs : BSsc¢2 8 NWO"
    out = merge_ocr_texts(vlm_text, tess)
    assert out.startswith("How to Apply\nAge 16 to 25 years")
    assert "NASTP Kharian" in out and "Merit Based" in out and "Scholarship" in out
    assert out.count("Age 16 to 25 years") == 1 and "BSsc" not in out


class HeaderResp(Resp):
    def __init__(self, body, status, headers):
        super().__init__(body, status)
        self.headers = headers


def test_daily_quota_pauses_vlm_without_waiting(configured, monkeypatch):
    import fakeredis

    from nts import dedup

    r = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(dedup, "get_redis", lambda: r)
    slept = []
    monkeypatch.setattr(vlm.time, "sleep", lambda s: slept.append(s))
    reset = vlm.time.time() + 3600
    daily = HeaderResp(
        {},
        429,
        {
            "X-RateLimit-Type": "daily",
            "X-RateLimit-Daily-Remaining": "0",
            "X-RateLimit-Daily-Reset": str(reset),
            "X-RateLimit-Daily-Limit": "50",
        },
    )
    with pytest.raises(deapi_keys.KeyExhausted):
        vlm._rate_limited(lambda k: daily, deapi_keys.keys()[0])
    assert slept == []  # no waiting on a daily limit
    assert vlm.paused_until() == pytest.approx(reset)
    # Paused: new images are refused at once, before any HTTP call
    with pytest.raises(vlm.QuotaExhausted):
        vlm._ocr_one(Image.new("RGB", (50, 50), "red"), session=None)


def test_poll_schedule_backs_off():
    d = vlm._poll_delays()
    first = [next(d) for _ in range(6)]
    assert first[0] == 8 and first[1] < first[2] < first[3] and max(first) <= 30
