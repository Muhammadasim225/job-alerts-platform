"""Pure parsing for the website fields: organization names, slugs, education, gender.
Inputs are real NTS headings and qualification lines (OCR noise included)."""

from datetime import date

import pytest

from shared.orgs import clean_org_name, normalize_alias, org_slug
from shared.slugs import listing_slug, slugify, split_listing_path_slug
from shared.taxonomy import education_levels, gender_eligibility, minimum_education


@pytest.mark.parametrize(
    ("raw", "name", "short"),
    [
        (
            "National Institute of Cardiovascular Diseases (NICVD) (Career Opportunities)",
            "National Institute of Cardiovascular Diseases",
            "NICVD",
        ),
        (
            "Independent System & Market Operator (ISMO) (Exciting Job Opportunities)",
            "Independent System & Market Operator",
            "ISMO",
        ),
        ("Gujranwala Electric Power Company (GEPCO) Career Opportunities", "Gujranwala Electric Power Company", "GEPCO"),
        ("SPL-Security Papers Limited- Non-Management Positions", "Security Papers Limited", "SPL"),
        (
            "Maryam Nawaz Sharif Medical College Mianwali - Vacant Position (Specialized Healthcare & Medical Education "
            "Department)",
            "Maryam Nawaz Sharif Medical College Mianwali",
            None,
        ),
        (
            "Lareb Mustafa Institute of Nursing, Gambat (BSN (Generic) 4 Year Degree Program 2026-27)",
            "Lareb Mustafa Institute of Nursing, Gambat",
            None,
        ),
        (
            "University of Malakand, Chakdara Dir Lower MS, MPhil & PhD Admission Test (Fall 2026-I)",
            "University of Malakand, Chakdara Dir Lower",
            None,
        ),
        (
            "Doctor of Pharmacy Pharm. D - Shifa College of Pharmaceutical Sciences, Shifa Tameer-e-Millat University, "
            "Islamabad Class of 2031 Admission Test",
            "Shifa College of Pharmaceutical Sciences, Shifa Tameer-e-Millat University, Islamabad",
            None,
        ),
        (
            "Vacancy Announcement (College-Of-Ophthalmology-&-Allied-Vision-Sciences-Lahore-KEMU/MAYO Hospital Lahore)",
            "College Of Ophthalmology & Allied Vision Sciences Lahore KEMU/MAYO Hospital Lahore",
            None,
        ),
        ("National Testing Service - Pakistan (Job Opportunities)", "National Testing Service", None),
    ],
)
def test_clean_org_name(raw, name, short):
    org = clean_org_name(raw)
    assert (org.name, org.short_name) == (name, short)


def test_clean_org_name_empty():
    assert clean_org_name(None) is None and clean_org_name("  ") is None


def test_org_slug_prefers_short_name():
    assert org_slug(clean_org_name("National Institute of Cardiovascular Diseases (NICVD) (Career Opportunities)")) == "nicvd"
    assert normalize_alias("Join Pak-Army!") == "join pak army"


def test_slugify():
    assert slugify("College Of Ophthalmology & Allied Vision") == "college-of-ophthalmology-and-allied-vision"
    assert slugify("Ünïcödé — Test") == "unicode-test"
    assert len(slugify("word " * 40)) <= 80 and not slugify("word " * 40).endswith("-")


def test_listing_slug_by_kind():
    assert listing_slug(kind="job", org="NICVD", city="Karachi", when=date(2026, 10, 5)) == "nicvd-karachi-jobs-oct-2026"
    assert listing_slug(kind="admission", org="AIOU", city=None, when=date(2027, 2, 1)) == "aiou-admission-2027"
    # the city is not repeated when the organization already names it
    assert (
        listing_slug(kind="admission", org="Lareb Mustafa Institute of Nursing, Gambat", city="Gambat", when=None)
        == "lareb-mustafa-institute-of-nursing-gambat-admission"
    )
    assert listing_slug(kind="job", org=None, city=None, when=None, title="") == "jobs"


def test_listing_path_slug_round_trip():
    assert split_listing_path_slug("nicvd-karachi-jobs-oct-2026-9") == ("nicvd-karachi-jobs-oct-2026", 9)
    assert split_listing_path_slug("karachi") is None
    assert split_listing_path_slug("hyderabad-sindh") is None


@pytest.mark.parametrize(
    ("text", "levels", "minimum"),
    [
        ("Intermediate + MS Office / ICS and With 40 wpm speed", ["intermediate"], "intermediate"),
        ("Candidate must be Matriculation qualified with Diploma in relevant field", ["matric", "diploma"], "matric"),
        ("Minimum Four (04) Years Bachelor degree or Master degree in Finance or CA", ["bachelor", "master"], "bachelor"),
        ("FCPS Interventional Radiology / Equivalent", ["master"], "master"),
        ("B.ScN (Generic) / Post RN B.ScN / Diploma in General Nursing", ["diploma", "bachelor"], "diploma"),
        ("F.Sc. (Pre-Medical) with Diploma / Training", ["intermediate", "diploma"], "intermediate"),
        ("BS-MT (Surgical Technology) with 02 years experience", ["bachelor"], "bachelor"),
        ("PhD in Physics", ["doctorate"], "doctorate"),
        ("from an institution tecognized the Boord", [], None),
    ],
)
def test_education_levels(text, levels, minimum):
    assert education_levels(text) == levels
    assert minimum_education(education_levels(text)) == minimum


def test_gender_eligibility():
    assert gender_eligibility("both") == "any"
    assert gender_eligibility("Female only") == "female"
    assert gender_eligibility("Male") == "male"
    assert gender_eligibility(None) is None and gender_eligibility("unclear") is None
