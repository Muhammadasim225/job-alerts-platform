"""Fixed vocabularies the website filters on: education levels and gender.

Both are read from free text (qualification lines and advert facts), which is often
OCR output, so the patterns are forgiving and the result is only a hint: the job page
always tells users to confirm on the official advert.
"""

import re

# Lowest to highest. A post "needs" the lowest level its qualification line accepts.
EDUCATION_LEVELS = ("middle", "matric", "intermediate", "diploma", "bachelor", "master", "doctorate")

_EDUCATION_PATTERNS: dict[str, re.Pattern] = {
    "middle": re.compile(r"\b(?:middle|primary|8th\s+class|literate)\b", re.I),
    "matric": re.compile(r"\b(?:matric\w*|s\.?s\.?c|secondary\s+school\s+certificate)\b", re.I),
    "intermediate": re.compile(
        r"\b(?:intermediate|f\.?\s?sc|f\.?\s?a|i\.?\s?com|i\.?c\.?s|h\.?s\.?s\.?c|higher\s+secondary|12\s*years)\b", re.I
    ),
    "diploma": re.compile(r"\b(?:diploma|d\.?a\.?e|certificate\s+course)\b", re.I),
    # Short forms that are also ordinary words ("be", "ma", "ms", "ca") only count in
    # capitals or with dots, so "must be" or "MS Office" are not degrees.
    "bachelor": re.compile(
        r"\b(?:bachelor\w*|graduat\w*|b\.?\s?sc\w*|b\.?s\.?c?n|(?-i:BS)|b\.\s?a\b|(?-i:BA)|b\.?\s?com|bba|bcs|b\.\s?e\b|"
        r"(?-i:BE)|b\.?\s?tech|mbbs|bds|pharm\.?\s?-?d|ll\.?\s?b|dvm|14\s*years|16\s*years|four\s*\(?0?4\)?\s*years?)\b",
        re.I,
    ),
    "master": re.compile(
        r"\b(?:master\w*|m\.?\s?sc|m\.\s?a\b|(?-i:MA)|mba|mcs|m\.?\s?com|(?-i:MS)(?!\s*(?:office|word|excel))|fcps|mcps|"
        r"(?-i:CA)|acca|acma)\b",
        re.I,
    ),
    "doctorate": re.compile(r"\b(?:ph\.?\s?d|doctorate|m\.?\s?phil)\b", re.I),
}


def education_levels(*texts: str | None) -> list[str]:
    """Every level mentioned in the texts, ordered lowest first."""
    text = " ".join(t for t in texts if t)
    if not text:
        return []
    return [level for level in EDUCATION_LEVELS if _EDUCATION_PATTERNS[level].search(text)]


def minimum_education(levels: list[str]) -> str | None:
    """The lowest level a post accepts, i.e. what a candidate needs at least."""
    ranked = [lvl for lvl in EDUCATION_LEVELS if lvl in levels]
    return ranked[0] if ranked else None


GENDERS = ("any", "male", "female")


def gender_eligibility(value: str | None) -> str | None:
    """Normalize the advert's gender fact: both/any/all -> any; None when unknown."""
    if not value:
        return None
    v = value.strip().lower()
    if v in {"both", "any", "all", "male/female", "male & female", "male and female"}:
        return "any"
    if v.startswith("female") or v in {"women", "woman", "f"}:
        return "female"
    if v.startswith("male") or v in {"men", "man", "m"}:
        return "male"
    return None
