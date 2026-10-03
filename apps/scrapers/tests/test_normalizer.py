import pytest

from nts.normalizer import (
    classify_field,
    classify_kind,
    extract_bps,
    extract_locations,
    normalize_listing,
    parse_date,
    posts_from_text,
)


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("8th October 2026", "2026-10-08"),
        ("Thursday 15th October 2026", "2026-10-15"),
        ("27th September, 2026", "2026-09-27"),
        ("Friday, 30th October, 2026", "2026-10-30"),
        ("22nd  September 2026", "2026-09-22"),
        ("2026-09-28", "2026-09-28"),
        ("08.10.2026", "2026-10-08"),
        ("", None),
        ("to be announced", None),
    ],
)
def test_parse_date(raw, expected):
    assert parse_date(raw) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Deputy Director (Design) BPS-18", [18]),
        ("Computer Operator (BPS-12)", [12]),
        ("Junior Clerk B.P.S-11", [11]),
        ("Assistant (BS-16)", [16]),
        ("Inspector BPS 11 to 14", [11, 12, 13, 14]),
        ("Lecturer BPS-17 & BPS-18", [17, 18]),
        ("GAT-A (MS/ MPhil Program)", []),
        ("Fee: 750", []),
    ],
)
def test_extract_bps(text, expected):
    assert extract_bps(text) == expected


def test_classify_field():
    assert classify_field("Computer Operator") == "it"
    assert classify_field("Deputy Director (Design)") == "engineering"
    assert classify_field("Junior Clerk") == "clerical"
    assert classify_field("Charge Nurse") == "health"
    assert classify_field("Driver") == "support"


def test_classify_kind():
    assert classify_kind("Punjab Walled Cities and Heritage Areas Authority", ["Computer Operator (BPS-12)"]) == "job"
    assert classify_kind("Independent System & Market Operator (ISMO) (Exciting Job Opportunities)", []) == "job"
    assert classify_kind("Graduate Assessment Test (GAT Subject 2026-VI)", []) == "test"
    assert classify_kind("University of Balochistan (Admission Test)", []) == "admission"


def test_locations():
    provinces, cities = extract_locations("Walled City Of Lahore Authority", "University of Malakand, Chakdara Dir Lower")
    assert cities == ["Chakdara", "Dir", "Lahore", "Malakand"]
    assert provinces == ["Khyber Pakhtunkhwa", "Punjab"]


def test_posts_from_text():
    text = "Positions:\n1. Junior Clerk (BPS-11)\n2) Stenographer BPS-14\nFee Rs. 500\n1. Junior Clerk (BPS-11)"
    assert posts_from_text(text) == [{"name": "Junior Clerk (BPS-11)"}, {"name": "Stenographer BPS-14"}]


def _listing(**detail):
    return {
        "source": "nts",
        "listing_id": "portal-101334",
        "url": "https://portal.nts.org.pk/Alldetail/MTAxMzM0",
        "status": "open",
        "title": "Punjab Walled Cities and Heritage Areas Authority",
        "deadline_label": "Last Date of Application Form Submission",
        "deadline_raw": "28th September 2026",
        "detail": {
            "organization": "Punjab Walled Cities and Heritage Areas Authority",
            "department": "Walled City Of Lahore Authority",
            "project_code": "2609202",
            "last_date_raw": "2026-09-28",
            "announce_date_raw": "2026-09-11",
            "test_date_raw": "2026-10-12",
            "attachments": [],
            "posts": [
                {"name": "Computer Operator (BPS-12)", "mode": "Online", "fee": "750 + 10 Service charges",
                 "age_limit": "18 - 25 Years", "details": None, "raw": "x"},
            ],
            **detail,
        },
    }


def test_normalize_portal_listing():
    rec = normalize_listing(_listing())
    assert rec["kind"] == "job"
    assert rec["last_date"] == "2026-09-28"
    assert rec["test_date"] == "2026-10-12"
    assert rec["provinces"] == ["Punjab"]
    assert rec["needs_review"] is False
    v = rec["vacancies"][0]
    assert v["post_name"] == "Computer Operator"
    assert (v["bps"], v["field"], v["fee_pkr"], v["age_min"], v["age_max"]) == ([12], "it", 750, 18, 25)
    assert v["extracted_from"] == "portal_html"


def test_normalize_falls_back_to_advert_text_and_flags_review():
    rec = normalize_listing(_listing(posts=[]), parsed_docs=[{"path": "a.pdf", "method": "text", "text": "Junior Clerk BPS-11"}])
    assert rec["vacancies"][0]["bps"] == [11]
    assert rec["vacancies"][0]["extracted_from"] == "advert_text"
    assert rec["needs_review"] is True


def test_normalize_flags_mismatched_deadline():
    rec = normalize_listing(_listing(last_date_raw="2026-09-30"))
    assert rec["last_date"] == "2026-09-30"
    assert any("differs" in r for r in rec["review_reasons"])


def test_post_name_keeps_other_brackets():
    from nts.normalizer import normalize_post

    assert normalize_post({"name": "Deputy Director (Design) BPS-18"}, "portal_html")["post_name"] == "Deputy Director (Design)"
    assert normalize_post({"name": "Computer Operator (BPS-12)"}, "portal_html")["post_name"] == "Computer Operator"
    assert normalize_post({"name": "GAT-A (MS/ MPhil Program)"}, "portal_html")["post_name"] == "GAT-A (MS/ MPhil Program)"


def test_field_keywords_match_whole_words_only():
    assert classify_field("National Aptitude Test") is None
    assert classify_field("EST Teacher") == "education"


def test_admission_title_wins_over_post_word():
    title = "City Institute of Health Sciences (Admissions Test for Generic BS Nursing / Post RN BSN Degree Programs)"
    assert classify_kind(title, ["Generic BSN", "Post RN BSN"]) == "admission"


def test_locations_ignore_nts_address_in_advert():
    doc = {"path": "a.jpg", "method": "ocr", "text": "Apply via NTS, Islamabad\nPosts at Lahore office"}
    rec = normalize_listing(_listing(organization="Some Authority", department=None), parsed_docs=[doc])
    assert rec["title"] == "Punjab Walled Cities and Heritage Areas Authority"
    assert rec["provinces"] == ["Punjab"]  # from the title, advert not needed
    rec = normalize_listing({**_listing(organization="X", department=None), "title": "Some Authority"}, parsed_docs=[doc])
    assert rec["provinces"] == ["Punjab"] and rec["cities"] == ["Lahore"]


def test_ocr_advert_does_not_flag_review_when_portal_has_posts():
    rec = normalize_listing(_listing(), parsed_docs=[{"path": "a.jpg", "method": "ocr", "text": "whatever"}])
    assert rec["needs_review"] is False


def test_stale_tentative_test_date_is_dropped():
    rec = normalize_listing(_listing(last_date_raw="2026-10-04", test_date_raw="2026-09-18"))
    assert rec["last_date"] == "2026-10-04" and rec["test_date"] is None


@pytest.mark.parametrize(
    "text, years",
    [
        ("Minimum 05 years of post-qualification relevant experience", 5),
        ("Minimum 2-Years of Post-Qualification relevant Experience", 2),
        ("Candidates with relevant experience will be preferred", 0),
        ("Five years relevant experience", 5),
        (None, None),
    ],
)
def test_experience_years(text, years):
    from nts.normalizer import experience_years

    assert experience_years(text) == years


def test_portal_posts_enriched_from_advert_table():
    table = [
        {"name": "Deputy Director (Design)", "total_posts": 1,
         "qualification": "(i) BSc (Civil Engineering) from a University recognized by HEC, and (ii) having five years relevant experience"},
        {"name": "Computer Operator", "total_posts": 2, "qualification": "Intermediate + MS Office / ICS and With 40 wpm speed on computer."},
    ]
    listing = _listing(posts=[
        {"name": "Deputy Director (Design) BPS-18", "mode": "Online", "fee": "750", "age_limit": "26 - 40 Years", "details": None, "raw": "a"},
        {"name": "Computer Operator (BPS-12)", "mode": "Online", "fee": "750", "age_limit": "18 - 25 Years", "details": None, "raw": "b"},
    ])
    rec = normalize_listing(listing, table_posts=table)
    dd, co = rec["vacancies"]
    assert (dd["bps"], dd["total_posts"], dd["experience_years_min"]) == ([18], 1, 5)
    assert "Civil Engineering" in dd["qualification"]
    assert (co["bps"], co["total_posts"], co["experience_years_min"]) == ([12], 2, None)
    assert co["extracted_from"] == "portal_html" and rec["needs_review"] is False


def test_uom_programs_with_subjects_from_portal_details():
    from nts.normalizer import build_programs

    posts = [
        {"name": "GAT-C (MS/ MPhil Program)", "fee": "1300 + 10 Service charges",
         "details": "MS/ MPhil Programs (1. Pharmacy 2. Mathematics 3. Biotechnology 4. Geology 5. Computer Science)"},
        {"name": "Mathematics (PhD Program)", "fee": "1300 + 10 Service charges", "details": None},
    ]
    programs, _ = build_programs(posts, [], {}, "University of Malakand MS, MPhil & PhD Admission Test (Fall 2026-I)")
    mphil, phd = programs
    assert mphil["level"] == "MPhil" and mphil["subjects"] == ["Pharmacy", "Mathematics", "Biotechnology", "Geology", "Computer Science"]
    assert phd["level"] == "PhD" and phd["subjects"] == ["Mathematics"] and phd["fee_pkr"] == 1300


def test_cihs_portal_programs_merged_with_advert_table():
    from nts.normalizer import build_programs

    posts = [{"name": "Generic BSN", "fee": "2500 + 10 Service charges", "age_limit": "14 - 35 Years", "details": None}]
    table = [
        {"name": "Generic BSN (04 years Degree Program) Morning & Evening", "qualification": "« (Pre-Medical) with 50% marks. « Age Limit: 14-35 years."},
        {"name": "Community Midwife (CMW) 18 months Diploma Program", "qualification": "¢ Matrix (either Art or Science) with 40% marks. ¢ Age Limit: 14-40 years"},
    ]
    programs, reasons = build_programs(posts, table, {}, "City Institute of Health Sciences")
    bsn, cmw = programs
    assert bsn["via_nts"] and bsn["level"] == "BSN" and bsn["duration"] == "4 years"
    assert bsn["eligibility"] == ["(Pre-Medical) with 50% marks"] and (bsn["age_min"], bsn["age_max"]) == (14, 35)
    assert not cmw["via_nts"] and cmw["level"] == "Diploma" and cmw["duration"] == "18 months" and cmw["age_max"] == 40
    assert reasons == ["1 programme(s) were read from the advert table (OCR)"]


def test_banner_only_admission_uses_banner_facts():
    from nts.normalizer import build_programs

    facts = {"eligibility": [{"text": "FSc Pre-Medical (Minimum 50%)", "min_percent": 50}], "age_min": 14, "age_max": 35, "duration": "4 years"}
    [p], reasons = build_programs([], [], facts, "Visionary Institute, Sukkur (BSN (Generic) 4 Year Degree Program 2026-27)")
    assert p["name"] == "BSN (Generic) 4 Year Degree Program 2026-27"
    assert p["level"] == "BSN" and p["duration"] == "4 years" and p["eligibility"] == ["FSc Pre-Medical (Minimum 50%)"]
    assert (p["age_min"], p["age_max"]) == (14, 35) and reasons


def test_sample_papers_are_not_read_as_adverts():
    from tasks import is_advert_file

    assert is_advert_file({"name": "Advertisement", "path": "raw/attachments/x/1790938582_Job_Advertisement.pdf"})
    assert not is_advert_file({"name": "Sample Paper", "path": "raw/attachments/x/1790938619_SAMPLE_PAPER.pdf"})
    assert not is_advert_file({"name": "Syllabus", "path": "raw/attachments/x/syllabus.pdf"})


def test_syllabus_attached_to_posts():
    syllabus = {"Computer Operator": [{"subject": "Fundamentals of IT", "weight_percent": 20}]}
    rec = normalize_listing(_listing(), syllabus=syllabus)
    assert rec["vacancies"][0]["test_syllabus"] == [{"subject": "Fundamentals of IT", "weight_percent": 20}]
    assert rec["test_syllabus"] == syllabus


def test_attachment_roles():
    from tasks import attachment_role

    assert attachment_role({"name": "Advertisement", "path": "x/WCLA_ad.jpg"}) == "advert"
    assert attachment_role({"name": "Content Weightages", "path": "x/ContentWeightages.docx"}) == "syllabus"
    assert attachment_role({"name": "Sample Paper", "path": "x/SAMPLE_PAPER.pdf"}) == "sample_paper"
    assert attachment_role({"name": "Fee Challan", "path": "x/challan.pdf"}) == "other"


def test_admission_title_wins_over_pbs_programme():
    title = "City Institute of Health Sciences (Admissions Test for Various Diploma Programs)"
    assert classify_kind(title, ["PBS (01 Years Program) (Cardiac Care Unit)"]) == "admission"
