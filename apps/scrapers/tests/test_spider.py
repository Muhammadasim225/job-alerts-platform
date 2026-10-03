from pathlib import Path

import pytest
from scrapy.http import HtmlResponse

from nts.common import listing_id_from_url
from nts.spider import parse_legacy_detail, parse_listing_page, parse_portal_detail

FIXTURES = Path(__file__).parent / "fixtures"


def response(name: str, url: str) -> HtmlResponse:
    return HtmlResponse(url=url, body=(FIXTURES / name).read_bytes(), encoding="utf-8")


@pytest.fixture(scope="module")
def listings():
    return parse_listing_page(response("nts_listing.html", "https://www.nts.org.pk/new/projectsnew.php"))


def test_listing_page_finds_open_and_closed(listings):
    assert len(listings) == 20
    assert sum(1 for x in listings if x["status"] == "open") == 15
    assert sum(1 for x in listings if x["status"] == "closed") == 5


def test_listing_fields(listings):
    ismo = next(x for x in listings if x["listing_id"] == "legacy-06_26-ISMO_June2026_Online")
    assert ismo["title"] == "Independent System & Market Operator (ISMO) (Exciting Job Opportunities)"
    assert ismo["deadline_raw"] == "8th October 2026"
    assert ismo["deadline_label"] == "Last Date of Application Form Submission"
    assert ismo["detail_kind"] == "legacy"

    wcla = next(x for x in listings if x["listing_id"] == "portal-101334")
    assert wcla["url"] == "https://portal.nts.org.pk/Alldetail/MTAxMzM0"
    assert wcla["detail_kind"] == "portal"


def test_listing_ids_are_unique(listings):
    ids = [x["listing_id"] for x in listings]
    assert len(ids) == len(set(ids))


def test_listing_id_from_url():
    assert listing_id_from_url("https://portal.nts.org.pk/Alldetail/MTAxMDU2") == "portal-101056"
    assert (
        listing_id_from_url("https://nts.org.pk/Test&Products/Announced/09_26/NTS_Sep_2026/NTS.php")
        == "legacy-09_26-NTS_Sep_2026"
    )
    assert listing_id_from_url("https://example.com/x").startswith("url-")


def test_portal_job_detail():
    d = parse_portal_detail(response("nts_portal_detail.html", "https://portal.nts.org.pk/Alldetail/MTAxMzM0"))
    assert d["organization"] == "Punjab Walled Cities and Heritage Areas Authority"
    assert d["department"] == "Walled City Of Lahore Authority"
    assert d["project_code"] == "2609202"
    assert (d["last_date_raw"], d["announce_date_raw"], d["test_date_raw"]) == ("2026-09-28", "2026-09-11", "2026-10-12")
    assert d["attachments"] == [
        {"name": "Advertisement", "url": "https://portal.nts.org.pk/uploads/projects/1789111784_WCLA%20ad.jpg"}
    ]
    assert [p["name"] for p in d["posts"]] == ["Deputy Director (Design) BPS-18", "Computer Operator (BPS-12)"]
    assert d["posts"][1] | {"raw": None} == {
        "name": "Computer Operator (BPS-12)",
        "mode": "Online",
        "total_posts": None,
        "fee": "750 + 10 Service charges",
        "age_limit": "18 - 25 Years",
        "details": None,
        "raw": None,
    }


def test_portal_admission_detail():
    d = parse_portal_detail(response("nts_portal_admission.html", "https://portal.nts.org.pk/Alldetail/MTAxMzY0"))
    assert d["last_date_raw"] == "2026-10-05"
    assert len(d["posts"]) == 10
    assert d["posts"][0]["details"] == "MS/ MPhil Programs (1. Management Studies)"
    assert d["attachments"][0]["url"].endswith("UOM%20Updated%20advertisement%2025,9,2026.jpeg")


def test_legacy_detail():
    d = parse_legacy_detail(
        response("nts_legacy_detail.html", "https://nts.org.pk/Test&Products/Announced/06_26/ISMO_June2026_Online/ISMO.php")
    )
    assert d["last_date_raw"] == "8th October 2026"
    assert d["attachments"] == [
        {"name": "Advertisement", "url": "https://nts.org.pk/Test&Products/Announced/06_26/ISMO_June2026_Online/ISMO_Ad.pdf"}
    ]


def test_snapshot_ignores_cloudflare_email_tokens(tmp_path, monkeypatch):
    import config
    from nts.spider import save_snapshot

    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(config, "RAW_HTML_DIR", tmp_path / "raw" / "html")
    a = b'<a href="/cdn-cgi/l/email-protection#85f4f0"><span data-cfemail="376642">x</span></a>'
    b = b'<a href="/cdn-cgi/l/email-protection#bacbcf"><span data-cfemail="104165">x</span></a>'
    assert save_snapshot("portal-1", a) == save_snapshot("portal-1", b)
    assert save_snapshot("portal-1", a) != save_snapshot("portal-1", b"<p>changed</p>")


def test_parse_posts_with_total_post_field():
    from nts.spider import parse_posts

    [p] = parse_posts("Post Name: Doctor of Pharmacy (Pharm. D) (Online) Apply Now Total Post: 1 Fee: 5300 + 10 Service charges")
    assert (p["name"], p["mode"], p["total_posts"], p["fee"]) == ("Doctor of Pharmacy (Pharm. D)", "Online", 1, "5300 + 10 Service charges")
