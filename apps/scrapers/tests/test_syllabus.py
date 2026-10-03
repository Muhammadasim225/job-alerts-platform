from pathlib import Path

from nts.parser import parse_file
from nts.syllabus import extract_test_syllabus

FIXTURE = Path(__file__).parent / "fixtures" / "wcla_content_weightages.docx"


def test_wcla_content_weightages_docx():
    doc = parse_file(FIXTURE.resolve())
    assert doc.kind == "docx" and doc.method == "text"
    syllabus = extract_test_syllabus(doc.tables)
    assert list(syllabus) == ["Deputy Director (Design)", "Computer Operator"]
    dd = syllabus["Deputy Director (Design)"]
    assert dd[0] == {"subject": "Verbal Reasoning", "weight_percent": 10}
    assert {"subject": "Descriptive (Essay Writing)", "weight_percent": 30} in dd
    assert sum(s["weight_percent"] for s in dd) == 100
    co = syllabus["Computer Operator"]
    assert {"subject": "Fundamentals of IT", "weight_percent": 20} in co
    assert {"subject": "English Typing Speed (40 w.p.m.)", "weight_percent": None} in co
