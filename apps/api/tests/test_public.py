def test_list_defaults_to_open_and_live(client):
    r = client.get("/v1/listings")
    assert r.status_code == 200
    body = r.json()
    ids = [i["external_id"] for i in body["items"]]
    assert body["total"] == 2 and "old-closed" not in ids
    assert ids == ["portal-101334", "portal-101364"]  # closing soonest first
    job = body["items"][0]
    assert job["posts_count"] == 2 and job["total_seats"] == 3 and (job["bps_min"], job["bps_max"]) == (12, 18)
    assert job["days_left"] == 5 and r.headers["cache-control"].startswith("public")


def test_filters(client):
    assert client.get("/v1/listings", params={"kind": "admission"}).json()["total"] == 1
    assert client.get("/v1/listings", params={"province": "Sindh"}).json()["total"] == 0
    assert client.get("/v1/listings", params={"field": "it"}).json()["total"] == 1
    assert client.get("/v1/listings", params={"bps_min": 19}).json()["total"] == 0
    assert client.get("/v1/listings", params={"program_level": "PhD"}).json()["total"] == 1
    assert client.get("/v1/listings", params={"status": "any", "include_expired": True}).json()["total"] == 3


def test_text_search_is_literal(client):
    assert client.get("/v1/listings", params={"q": "computer operator"}).json()["total"] == 1
    assert client.get("/v1/listings", params={"q": "%"}).json()["total"] == 0
    assert client.get("/v1/listings", params={"q": "' OR 1=1 --"}).json()["total"] == 0


def test_validation_errors(client):
    assert client.get("/v1/listings", params={"bps_min": 20, "bps_max": 5}).status_code == 422
    assert client.get("/v1/listings", params={"limit": 1000}).status_code == 422
    assert client.get("/v1/listings", params={"kind": "nonsense"}).status_code == 422


def test_pagination(client):
    page = client.get("/v1/listings", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 2 and len(page["items"]) == 1 and page["items"][0]["external_id"] == "portal-101364"


def test_detail_by_source_id_hides_internal_fields(client):
    r = client.get("/v1/sources/nts/listings/portal-101334")
    assert r.status_code == 200
    d = r.json()
    assert [v["post_name"] for v in d["vacancies"]] == ["Deputy Director (Design)", "Computer Operator"]
    assert {"subject": "Fundamentals of IT", "weight_percent": 20} in d["vacancies"][1]["test_syllabus"]
    assert {a["role"] for a in d["attachments"]} == {"advert", "syllabus"}
    text = r.text
    assert "raw_html_path" not in text and "review_reasons" not in text and "raw/attachments" not in text
    assert client.get(f"/v1/listings/{d['id']}").json()["external_id"] == "portal-101334"
    assert client.get("/v1/listings/99999999").status_code == 404


def test_vacancy_search(client):
    r = client.get("/v1/vacancies", params={"field": "it"}).json()
    assert r["total"] == 1 and r["items"][0]["post_name"] == "Computer Operator"
    assert r["items"][0]["listing"]["external_id"] == "portal-101334"
    assert client.get("/v1/vacancies", params={"bps_min": 16, "bps_max": 20}).json()["items"][0]["post_name"] == "Deputy Director (Design)"


def test_stats_and_filters(client):
    s = client.get("/v1/stats").json()
    assert s["open_listings"] == {"job": 1, "admission": 1} and s["open_posts"] == 2 and s["open_seats"] == 3
    f = client.get("/v1/filters").json()
    assert {x["value"] for x in f["kinds"]} == {"job", "admission"}
    assert {"value": "Punjab", "count": 1} in f["provinces"]


def test_health(client):
    assert client.get("/health/live").json() == {"status": "ok"}
