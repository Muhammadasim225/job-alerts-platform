"""Snippets below are real OCR output from NTS adverts (Sep 2026)."""

from nts.advert_info import (
    advert_deadline,
    age_range,
    benefits,
    conducted_by,
    duration,
    eligibility,
    extract_facts,
    gender,
    registration_open,
    session,
)

VISIONARY = """VISIONARY
INSTITUTE OF NURSING
REGISTRATION
OPEN:
SESSION: 2026-27
GENERIC
DEGREE
PROGRAM
(04 YEARS)
ELIGIBILITY CRITERIA
~ FSc Pre-Medical
(Minimum 50%).
Open Merit
Gender Ratio as per Policy
Age Limit: 14-35 Years
TEST CONDUCTED BY
0370-2463331
Sukkur Cooperative Housing Society"""

NASTP = """AIRCRAFT MAINTENANCE LICENSING PROGRAM
Dreaming of a career in aviation? Enroll in our 2nd Batch of
EASA-approved Part-147 Basic Course (2 years) in Category
� Visit NTS website www.nts.org.pk and apply online. Last
date to apply is 4" October 2026
* Minimum education FSc / A-Levels or equivalent
� Age 16 to 25 years
� Both Male and Female candidates are eligible to apply
Free
Accomodation for selected
students
Merit Based
Scholarship"""

UOM = """ADMISSIONS FOR GRADUATE PROGRAMS FOR FALL 2026
MPhil Program
by the University, securing a minimum score of 50% in GAT-General and 60% in GAT-Subject,
_Applications Deadline:
_ October 05%, 2026"""


def test_visionary_banner():
    f = extract_facts(VISIONARY)
    assert f["registration_open"] is True
    assert f["session"] == "2026-27"
    assert f["duration"] == "4 years"
    assert (f["age_min"], f["age_max"]) == (14, 35)
    assert f["eligibility"] == [{"text": "FSc Pre-Medical (Minimum 50%).", "min_percent": 50}]
    assert "merit_based" in f["benefits"]


def test_nastp_banner():
    f = extract_facts(NASTP)
    assert f["duration"] == "2 years"
    assert f["advert_last_date"] == "2026-10-04"
    assert (f["age_min"], f["age_max"]) == (16, 25)
    assert f["gender"] == "both"
    assert f["eligibility"][0]["text"].startswith("Minimum education FSc / A-Levels")
    assert {"free_accommodation", "scholarship", "merit_based", "international_certification"} <= set(f["benefits"])


def test_uom_banner():
    assert session(UOM) == "Fall 2026"
    assert registration_open(UOM) is False  # "Admissions for ..." is not "admissions open"
    assert advert_deadline(UOM) == "2026-10-05"
    assert conducted_by(UOM) == "NTS (GAT)"


def test_small_extractors():
    assert registration_open("ADMISSIONS OPEN 2026") is True
    assert registration_open("Applications are invited from suitable candidates") is True
    assert session("call 0370-2463331") is None
    assert age_range("Age Limit: 14-40 years") == (14, 40)
    assert gender("Female candidates only") == "female"
    assert duration("Community Midwife (CMW)\n18 months Diploma Program") == "18 months"
    assert duration("Minimum 5 Years experience") is None
    assert benefits("100% Scholarships Available on Diploma Programs") == ["scholarship"]
    assert eligibility("Matrix (either Art or Science) with 40% marks.")[0]["min_percent"] == 40


def test_score_requirements_and_quality():
    from nts.advert_info import score_requirements, text_quality

    assert score_requirements(UOM) == [{"test": "GAT-General", "min_percent": 50}, {"test": "GAT-Subject", "min_percent": 60}]
    assert text_quality("FSC (Pre-Medical) with 45% marks minimum (Physics, Chemistry & Biology)") == 1.0
    assert text_quality("‘5 bs : BSsc¢2 8  BENAZIRBHUTTO NWO") < 0.8
    assert eligibility("~ FSc Pre-Medical\n% (Minimum 50%)\n‘5 bs : BSsc¢2 8 BENAZIRBHUTTO NWO") == [
        {"text": "FSc Pre-Medical (Minimum 50%)", "min_percent": 50}
    ]


def test_ocr_noise_tolerance():
    from nts.advert_info import score_requirements
    from nts.tables import cell_items

    assert score_requirements("securing a minimum score of 50% a ; in GAT-General and 60% in GAT-Subject") == [
        {"test": "GAT-General", "min_percent": 50},
        {"test": "GAT-Subject", "min_percent": 60},
    ]
    assert duration("Certified Nursing Assistant (CNA) (02 vears Diploma Program)") == "2 years"
    assert eligibility("~ FSc Pre-Medical\nOpen Merit\n% (Minimum 50%)")[0]["text"] == "FSc Pre-Medical (Minimum 50%)"
    assert cell_items("¢ Matrix (either Art or Science) with 40% marks. e Age Limit: 14-40 years") == [
        "Matrix (either Art or Science) with 40% marks",
        "Age Limit: 14-40 years",
    ]


def test_score_requirement_with_neighbour_column_junk():
    from nts.advert_info import score_requirements

    assert score_requirements("securing a minimum score of 50% Se 3 in GAT-General and 60% in GAT-Subject")[0] == {
        "test": "GAT-General",
        "min_percent": 50,
    }
