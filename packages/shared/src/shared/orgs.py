"""Organization names: clean the free text a source gives us and find the canonical
organization (registry rows in the `organizations` table).

NTS writes headings such as
  "National Institute of Cardiovascular Diseases (NICVD) (Career Opportunities)"
  "Vacancy Announcement (College-Of-Ophthalmology-...-KEMU/MAYO Hospital Lahore)"
  "Lareb Mustafa Institute of Nursing, Gambat (BSN (Generic) 4 Year Degree Program 2026-27)"
We strip the advert descriptor, keep the employer, and pull out an acronym when the
heading states one. Matching is by normalized alias; an unknown employer becomes a new
registry row, so hubs and titles never depend on a hand-made list being complete.
"""

import re
from dataclasses import dataclass

from shared.slugs import slugify

# A parenthesised or dash-separated tail that describes the advert, not the employer
_DESCRIPTOR = re.compile(
    r"career|job|vacanc|opportunit|announcement|position|recruit|hiring|admission|test\b|program|degree|"
    r"class of|session|fall|spring|course|appointment|contract|walk.?in|interview|department\)?$",
    re.I,
)
_TRAILING_DESCRIPTOR = re.compile(
    r"\s*[-,]?\s*(?:(?:exciting\s+)?(?:career|job)s?\s+opportunit\w*|vacanc\w*\s+announcement|jobs?\s+\d{4})\s*$", re.I
)
_INLINE_ADMISSION = re.compile(
    r"(?:[\s,&]+(?:BS|MS|M\.?\s?Phil|Ph\.?\s?D|BSN|and))*[\s,]+(?:admissions?|entry\s+test)\b.*$", re.I
)
_CLASS_OF = re.compile(r"\s+class\s+of\s+\d{4}\b.*$", re.I)
_INSTITUTION = re.compile(
    r"\b(?:university|college|institute|authority|department|company|corporation|board|hospital|commission|"
    r"ministry|directorate|limited|agency|council|bank|service)\b",
    re.I,
)
_LEADING_DESCRIPTOR = re.compile(r"^(?:vacancy|vacancies|job|jobs|career)\s+(?:announcement|opportunities)\b", re.I)
_ACRONYM = re.compile(r"^[A-Z][A-Z&]{1,9}$")


@dataclass(frozen=True)
class OrgName:
    name: str  # cleaned full name
    short_name: str | None  # acronym when the source states one (NICVD, ISMO)


def _strip_trailing_groups(text: str) -> tuple[str, list[str]]:
    """Remove trailing balanced (...) groups; return the rest and the groups' contents."""
    groups: list[str] = []
    text = text.strip()
    while text.endswith(")"):
        depth, i = 0, len(text) - 1
        while i >= 0:
            depth += {")": 1, "(": -1}.get(text[i], 0)
            if depth == 0:
                break
            i -= 1
        if i < 0:
            break
        groups.insert(0, text[i + 1 : -1].strip())
        text = text[:i].rstrip(" ,-")
    return text, groups


def clean_org_name(raw: str | None) -> OrgName | None:
    if not raw or not raw.strip():
        return None
    text = re.sub(r"\s+", " ", raw).strip()
    text = _TRAILING_DESCRIPTOR.sub("", text)  # "... (GEPCO) Career Opportunities"
    base, groups = _strip_trailing_groups(text)

    # "Vacancy Announcement (Real Employer ...)": the employer is inside the brackets
    if _LEADING_DESCRIPTOR.match(base) and groups:
        base, groups = groups[0], groups[1:]
        base = re.sub(r"[-_]+", " ", base)

    # "Employer - Vacant Position" / "SPL-Security Papers Limited- Non-Management Positions"
    # "University of Malakand, Chakdara Dir Lower MS, MPhil & PhD Admission Test",
    # "... University, Islamabad Class of 2031 Admission Test"
    parts = [_INLINE_ADMISSION.sub("", _CLASS_OF.sub("", p)).strip(" ,") for p in re.split(r"\s+-\s+|-\s+(?=[A-Z])", base)]
    parts = [p for p in parts if p]
    # "Doctor of Pharmacy Pharm. D - Shifa College ...": the employer is the institution part
    institution = next((p for p in parts if _INSTITUTION.search(p)), None)
    if institution and len(parts) > 1:
        parts = [institution]
    while len(parts) > 1 and _DESCRIPTOR.search(parts[-1]):
        parts.pop()
    base = " - ".join(parts)

    short = next((g for g in groups if _ACRONYM.match(g)), None)
    m = re.match(r"^([A-Z][A-Z&]{1,9})\s*-\s*(.+)$", base)  # "SPL-Security Papers Limited"
    if m and not short:
        short, base = m.group(1), m.group(2)
    base = base.strip(" ,-")
    return OrgName(name=base, short_name=short) if base else None


def normalize_alias(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def org_slug(org: OrgName) -> str:
    return slugify(org.short_name or org.name, 60)
