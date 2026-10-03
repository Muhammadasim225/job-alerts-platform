import shutil
from pathlib import Path

import pytest

import config
from nts.tables import clean_post_name, extract_post_table


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("Engineer-ll (Electrical/ Electronics)", "Engineer-II (Electrical/Electronics)"),
        ("Analvst-l (HR)", "Analyst-I (HR)"),
        ("Analyst-Il ( Legal )", "Analyst-II (Legal)"),
        ("Senior Engineer", "Senior Engineer"),
    ],
)
def test_clean_post_name(raw, expected):
    assert clean_post_name(raw) == expected


ISMO_PDF = next((config.ATTACHMENTS_DIR / "legacy-06_26-ISMO_June2026_Online").glob("*.pdf"), None) if (
    config.ATTACHMENTS_DIR / "legacy-06_26-ISMO_June2026_Online"
).exists() else None


@pytest.mark.skipif(not shutil.which("tesseract") or ISMO_PDF is None, reason="needs tesseract and the ISMO advert (run in Docker)")
def test_ismo_positions_table():
    posts = extract_post_table(str(ISMO_PDF))
    names = [p["name"] for p in posts]
    assert len(posts) == 26
    assert names[0] == "Senior Engineer" and posts[0]["total_posts"] == 29
    assert "Assistant Manager (Sales Tax)" in names
    assert names[-1] == "Medical Officer" and posts[-1]["total_posts"] == 1
    eng2, eng1 = posts[names.index("Engineer-II (Electrical/Electronics)")], posts[names.index("Engineer-I (Electrical/Electronics)")]
    assert eng2["total_posts"] == eng1["total_posts"] == 60 and eng1["total_posts_shared"]
    # The single "35 years" cell covers all ten senior posts
    assert all("35" in p["age_limit"] for p in posts[:10])
    assert "05 years" in posts[0]["experience"]
    assert "Electrical" in posts[0]["qualification"] and "PEC" in posts[0]["qualification"]
    assert "preferred" in eng1["experience"].lower()


def test_clean_cell_text():
    from nts.tables import clean_cell_text

    assert clean_cell_text("Minimum 05 years of post- qualification\nrelevant experience") == "Minimum 05 years of post-qualification relevant experience"
    assert clean_cell_text("HRM from _ HEC- recognized university") == "HRM from HEC-recognized university"
