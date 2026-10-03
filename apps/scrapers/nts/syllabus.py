"""Test syllabus per post from "Content Weightages" style attachments.

NTS often adds a Word/PDF file next to the advert:

    Sr. No. | Designation of the Post | Criteria and Subject Division | Subject % Weight
    1       | Computer Operator       | As per Advertisement          | 100%
            |                         | Verbal Reasoning              | 10%
            |                         | Fundamentals of IT            | 20%
            |                         | Skill Test                    |
            |                         | English Typing Speed (40 w.p.m.)

The post name appears once; the following rows belong to it until the next post.
"""

import re

_POST_HEADER_RE = re.compile(r"post|designation|position|name", re.I)
_SUBJECT_HEADER_RE = re.compile(r"subject|criteria|content|topic|division|area", re.I)
_WEIGHT_HEADER_RE = re.compile(r"weight|%|marks|percent", re.I)
_SKIP_SUBJECT_RE = re.compile(r"^as per (the )?advert", re.I)


def _find_header(table: list[list[str]]) -> tuple[int, int, int, int] | None:
    """(header_row, post_col, subject_col, weight_col)."""
    for i, row in enumerate(table[:3]):
        post = next((j for j, c in enumerate(row) if _POST_HEADER_RE.search(c or "") and not re.search(r"sr\.?\s*no", c, re.I)), None)
        weight = next((j for j, c in enumerate(row) if _WEIGHT_HEADER_RE.search(c or "") and j != post), None)
        subject = next(
            (j for j, c in enumerate(row) if _SUBJECT_HEADER_RE.search(c or "") and j not in (post, weight)), None
        )
        if post is not None and subject is not None:
            return i, post, subject, weight if weight is not None else -1
    return None


def extract_test_syllabus(tables: list[list[list[str]]]) -> dict[str, list[dict]]:
    """{post name: [{"subject": "Verbal Reasoning", "weight_percent": 10}, ...]}"""
    out: dict[str, list[dict]] = {}
    for table in tables:
        header = _find_header(table)
        if header is None:
            continue
        h, post_col, subject_col, weight_col = header
        current = None
        for row in table[h + 1 :]:
            cell = lambda j: (row[j] if 0 <= j < len(row) else "").strip()  # noqa: E731
            if cell(post_col):
                current = " ".join(cell(post_col).split())
                out.setdefault(current, [])
            subject = " ".join(cell(subject_col).split())
            if not current or not subject or _SKIP_SUBJECT_RE.match(subject):
                continue
            m = re.search(r"(\d{1,3})\s*%?", cell(weight_col)) if weight_col >= 0 else None
            out[current].append({"subject": subject, "weight_percent": int(m.group(1)) if m else None})
    return {k: v for k, v in out.items() if v}
