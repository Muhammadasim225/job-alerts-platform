"""Pull the important facts out of an advert's text, whatever its design.

Designed banners (admissions, training courses) rarely have a table; the facts
sit in badges and bullet lists: "REGISTRATION OPEN", "SESSION 2026-27",
"(04 YEARS)", "FSc Pre-Medical (Minimum 50%)", "Age Limit: 14-35 Years",
"Free accommodation", "Test conducted by NTS". Each extractor below looks for
one kind of fact anywhere in the OCR text, so it works regardless of layout.

Everything returned here is a best-effort reading of OCR text; the pipeline
marks such records for review.
"""

import re

# --- status / intake -----------------------------------------------------------

_OPEN_RE = re.compile(
    r"\b(registration|registrations|admissions?|enrol+ment|applications?)\b[\s:!-]*(?:are\s+|is\s+|now\s+)?(open|invited)\b",
    re.I,
)
_SESSION_RE = re.compile(r"\b(?:session|batch|academic year|intake)?\s*[:\-]?\s*(20\d\d)\s*[-–/]\s*(20)?(\d\d)\b", re.I)
_TERM_RE = re.compile(r"\b(fall|spring|summer|winter|autumn)\s*[-–]?\s*(20\d\d)\b", re.I)


def registration_open(text: str) -> bool:
    flat = " ".join(text.split())
    if _OPEN_RE.search(flat):
        return True
    # Banners split the badge over two lines: "REGISTRATION" / "OPEN"
    if re.search(r"\b(registration|admissions?)\b\W{0,20}\bopen\b", flat, re.I):
        return True
    # badge read as "OPEN SESSION 2026-27" / "NOW OPEN"
    return bool(re.search(r"\bopen\W{0,5}session\b|\bnow\s+open\b", flat, re.I))


def session(text: str) -> str | None:
    m = _TERM_RE.search(text)
    if m:
        return f"{m.group(1).title()} {m.group(2)}"
    for m in _SESSION_RE.finditer(text):
        start, end = int(m.group(1)), int(m.group(3))
        if (start % 100) + 1 == end:  # 2026-27, not a phone number or a date range
            return f"{start}-{end:02d}"
    return None


# --- people ----------------------------------------------------------------------

_AGE_RE = re.compile(
    r"\bage(?:\s*limit)?\b[^0-9\n]{0,25}(\d{2})\s*(?:-|–|to)\s*(\d{2})\s*(?:years?|yrs?)?", re.I
)
_AGE_MAX_RE = re.compile(r"\b(?:upper\s+)?age(?:\s*limit)?\b[^0-9\n]{0,20}(?:up\s*to|max(?:imum)?)\s*(\d{2})", re.I)


def age_range(text: str) -> tuple[int | None, int | None]:
    m = _AGE_RE.search(text)
    if m:
        lo, hi = int(m.group(1)), int(m.group(2))
        if 10 <= lo < hi <= 70:
            return lo, hi
    m = _AGE_MAX_RE.search(text)
    if m:
        return None, int(m.group(1))
    return None, None


def gender(text: str) -> str | None:
    t = text.lower()
    if re.search(r"both\s+male\s+(and|&)\s+female|male\s*/\s*female|male\s+and\s+female", t):
        return "both"
    if re.search(r"\b(female|women|girls?)\s+(only|candidates only)\b|\bonly\s+(female|women|girls?)\b", t):
        return "female"
    if re.search(r"\b(male|boys?)\s+only\b|\bonly\s+(male|boys?)\b", t):
        return "male"
    return None


# --- education ---------------------------------------------------------------------

EDUCATION_RE = re.compile(
    r"\b(F\.?\s?Sc|F\.?\s?A\b|I\.?\s?Com|I\.?C\.?S|Intermediate|Matric(?:ulation)?|Matrix|SSC|HSSC|A[- ]?Levels?|O[- ]?Levels?|"
    r"B\.?\s?Sc|B\.?\s?A\b|B\.?\s?Com|BS\b|Bachelor'?s?|Master'?s?|M\.?\s?Sc|M\.?\s?A\b|MBA|MBBS|BDS|Pharm\.?\s?D|"
    r"DAE|Diploma|Pre[- ]?Medical|Pre[- ]?Engineering|PNC\s+licen[cs]e|Registered Nurse|Graduat(?:e|ion))",
    re.I,
)
_PERCENT_RE = re.compile(r"(\d{2})\s*%")
_BULLET_RE = re.compile(r"^[\s•·*+~=>\-–—°®©¢e«»]{0,3}\s*(?=[A-Z(])")


_GOOD_TOKEN_RE = re.compile(r"^[(\[]?(?:[A-Za-z][A-Za-z.'&/-]{0,13}|\d{1,3}(?:[-–]\d{1,3})?(?:%|st|nd|rd|th)?|[&/+%-])[)\],.:;%]*$")


def text_quality(line: str) -> float:
    """Share of tokens that look like real words/numbers (OCR of logos and photos
    produces 'BSsc¢2', 'CDEPEECEEENSEEE', 'PPPS')."""
    tokens = line.split()
    if not tokens:
        return 0.0
    good = 0
    for tok in tokens:
        core = tok.strip("()[],.:;%")
        if not _GOOD_TOKEN_RE.match(tok):
            continue
        if core.isalpha() and len(core) >= 4 and (
            not re.search(r"[aeiouyAEIOUY]", core) or re.search(r"[^aeiouyAEIOUY]{5,}", core) or re.search(r"(.)\1\1", core)
        ):
            continue
        if re.search(r"[a-z][A-Z]{2,}|[A-Z]{3,}[a-z]", core):  # "WHISIEOLEYy"
            continue
        good += 1
    return good / len(tokens)


def _clean_line(line: str) -> str:
    line = _BULLET_RE.sub("", line.strip())
    line = re.sub(r"\s+", " ", line)
    return line.strip(" -|_*~•·")


def eligibility(text: str) -> list[dict]:
    """Education requirements: [{"text": "FSc Pre-Medical (Minimum 50%)", "min_percent": 50}]."""
    lines = [l for l in text.splitlines() if l.strip()]
    out, seen = [], set()
    for i, raw in enumerate(lines):
        line = _clean_line(raw)
        if len(line) < 4 or len(line) > 160 or not EDUCATION_RE.search(line) or text_quality(line) < 0.8:
            continue
        # "FSc Pre-Medical" followed by "(Minimum 50%)" on the next line (OCR may
        # prefix a stray glyph: "% (Minimum 50%)")
        if not _PERCENT_RE.search(line):
            for nxt in lines[i + 1 : i + 4]:
                m = re.match(r"^[^\w(]{0,3}(\(?\s*(?:min(?:imum)?\.?)?\s*\d{2}\s*%\)?\.?)\s*$", nxt.strip(), re.I)
                if m:
                    line = f"{line} {m.group(1)}"
                    break
        key = re.sub(r"[^a-z0-9%]+", "", line.lower())
        if key in seen:
            continue
        seen.add(key)
        pct = _PERCENT_RE.search(line)
        out.append({"text": line, "min_percent": int(pct.group(1)) if pct else None})
    return out


# --- programme / course -----------------------------------------------------------

_DURATION_RE = re.compile(r"\(?\s*(\d{1,2})\s*[-]?\s*(years?|yrs?|vears?|yeas?|months?)\s*\)?", re.I)


_PROGRAM_WORD_RE = re.compile(r"\b(program(me)?s?|degree|course|diploma|certificate|batch|BSN|BS|MS|MPhil|PhD)\b", re.I)


def duration(text: str) -> str | None:
    """'(04 YEARS)' -> '4 years'; '18 months Diploma' -> '18 months'.

    Only a duration on (or right after) a line about the programme counts, so
    "5 Years experience" or "within 30 days" elsewhere on the advert is ignored."""
    lines = [l for l in text.splitlines() if l.strip()]
    m = None
    for i, line in enumerate(lines):
        if not _PROGRAM_WORD_RE.search(line) or re.search(r"\b(experience|age)\b", line, re.I):
            continue
        for candidate in (line, lines[i + 1] if i + 1 < len(lines) else ""):
            m = _DURATION_RE.search(candidate)
            if m:
                break
        if m:
            break
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2).lower()
    unit = "months" if unit.startswith("m") else "years"
    if n == 1:
        unit = unit[:-1]
    return f"{n} {unit}"


# --- deadline / test ---------------------------------------------------------------

_DEADLINE_RE = re.compile(
    r"(?:last\s+date|deadline|closing\s+date|apply\s+(?:by|before))[^0-9A-Za-z]{0,40}(?:\w+\s){0,6}?"
    r"((?:\d{1,2}(?:st|nd|rd|th|\")?\s*,?\s*[A-Z][a-z]+,?\s*20\d\d)|(?:[A-Z][a-z]+\s+\d{1,2}(?:st|nd|rd|th|%|\")?,?\s*20\d\d)|(?:\d{1,2}[./-]\d{1,2}[./-]20\d\d))",
    re.I,
)


def advert_deadline(text: str) -> str | None:
    """The last date as printed on the advert itself (to cross-check the listing)."""
    from nts.normalizer import parse_date  # local import: normalizer imports this module

    flat = " ".join(text.split())
    for m in _DEADLINE_RE.finditer(flat):
        raw = re.sub(r"(\d)(%|\")", r"\1", m.group(1))
        d = parse_date(raw)
        if d:
            return d
    return None


def conducted_by(text: str) -> str | None:
    t = " ".join(text.split())
    if re.search(r"test\s+(?:will\s+be\s+)?conducted\s+by\W{0,10}(NTS|National Testing Service)", t, re.I):
        return "NTS"
    if re.search(r"\b(GAT[- ]General|GAT[- ]Subject|HAT)\b", t):
        return "NTS (GAT)"
    if re.search(r"\bentry\s+test\b", t, re.I):
        return "entry test"
    return None


_SCORE_RE = re.compile(r"(\d{2})\s*%(?:\s*\S{1,3}){0,2}?\s*(?:marks\s*)?in\s*(GAT[- ]?(?:General|Subject|A|B|C)|HAT|NAT|USAT|entry test)", re.I)


def score_requirements(text: str) -> list[dict]:
    """'minimum score of 50% in GAT-General and 60% in GAT-Subject' ->
    [{"test": "GAT-General", "min_percent": 50}, {"test": "GAT-Subject", "min_percent": 60}]."""
    flat = " ".join(text.split())
    out, seen = [], set()
    for m in _SCORE_RE.finditer(flat):
        test = re.sub(r"\s+|-", "-", m.group(2)).upper().replace("GENERAL", "General").replace("SUBJECT", "Subject")
        if test not in seen:
            seen.add(test)
            out.append({"test": test, "min_percent": int(m.group(1))})
    return out


# --- perks -------------------------------------------------------------------------

BENEFITS = {
    "scholarship": re.compile(r"scholarships?", re.I),
    "free_accommodation": re.compile(r"free\W{0,5}(accom+odation|hostel|boarding)", re.I),
    "hostel": re.compile(r"\bhostel\b", re.I),
    "stipend": re.compile(r"\bstipend\b", re.I),
    "transport": re.compile(r"\b(pick\s*(and|&)\s*drop|transport(ation)? facility)\b", re.I),
    "merit_based": re.compile(r"\b(open\s+merit|merit[- ]based)\b", re.I),
    "international_certification": re.compile(r"international(ly)?\W{0,5}(accredited|recogni[sz]ed)|EASA|ENAC", re.I),
}


def benefits(text: str) -> list[str]:
    flat = " ".join(text.split())
    return [name for name, pattern in BENEFITS.items() if pattern.search(flat)]


# --- all together ------------------------------------------------------------------

def extract_facts(text: str) -> dict:
    age_min, age_max = age_range(text)
    return {
        "registration_open": registration_open(text),
        "session": session(text),
        "advert_last_date": advert_deadline(text),
        "age_min": age_min,
        "age_max": age_max,
        "gender": gender(text),
        "eligibility": eligibility(text),
        "duration": duration(text),
        "test_by": conducted_by(text),
        "test_requirements": score_requirements(text),
        "benefits": benefits(text),
    }
