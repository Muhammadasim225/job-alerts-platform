"""Turn a scraped listing (+ parsed advert text) into a structured record.

Output shape (one record per NTS listing, with one entry per post/vacancy):

  {
    source, listing_id, url, status, kind,            # kind: job | admission | test | unknown
    title, organization, department, project_code,
    last_date, announce_date, test_date,              # ISO dates or null
    provinces, cities,
    vacancies: [{post_name, bps, bps_min, bps_max, field, fee_pkr, age_min, age_max, mode, details, extracted_from}],
    attachments, parsed_text_path, raw_html_path,
    needs_review, review_reasons, normalized_at
  }

Structured portal HTML is trusted first; advert text (PDF / OCR) is only used to
fill gaps, and anything taken from it is flagged for manual review.
"""

import json
import re
from datetime import UTC, date, datetime

from dateutil import parser as dateparser

import config

# --- dates -----------------------------------------------------------------

_WEEKDAY_RE = re.compile(r"\b(mon|tue|wed|thu|fri|sat|sun)[a-z]*\.?,?\s*", re.I)
_ORDINAL_RE = re.compile(r"(\d{1,2})(st|nd|rd|th)\b", re.I)


def parse_date(value: str | None) -> str | None:
    """'Thursday 15th October 2026', '27th September, 2026', '2026-09-28' -> '2026-10-15'."""
    if not value:
        return None
    text = _ORDINAL_RE.sub(r"\1", _WEEKDAY_RE.sub("", value)).replace(",", " ").strip()
    if not re.search(r"\d{4}", text):
        return None
    try:
        dayfirst = not re.match(r"^\d{4}-\d{1,2}-\d{1,2}", text)
        parsed = dateparser.parse(text, dayfirst=dayfirst, fuzzy=True, default=datetime(2000, 1, 1))
    except (ValueError, OverflowError):
        return None
    if not (2000 < parsed.year < 2100):
        return None
    return parsed.date().isoformat()


# --- grades ----------------------------------------------------------------

# BPS-17, BPS 17, B.P.S-17, BS-17, (BPS-11 to 14), PPS-8, Scale 16
_BPS_RE = re.compile(
    r"\b(?:B\.?\s*P\.?\s*S|BS|PPS|PBS|Scale|Grade)\.?\s*[-–:#(]?\s*(\d{1,2})"
    r"(?:\s*(?:-|–|to|&|/)\s*(?:(?:BPS|BS)\s*[-–]?\s*)?(\d{1,2}))?\b",
    re.I,
)


def extract_bps(text: str | None) -> list[int]:
    grades: set[int] = set()
    for m in _BPS_RE.finditer(text or ""):
        lo = int(m.group(1))
        hi = int(m.group(2)) if m.group(2) else lo
        if 1 <= lo <= 22 and 1 <= hi <= 22 and hi >= lo and hi - lo <= 6:
            grades.update(range(lo, hi + 1))
        elif 1 <= lo <= 22:
            grades.add(lo)
    return sorted(grades)


# --- classification --------------------------------------------------------

FIELD_KEYWORDS: dict[str, list[str]] = {
    "engineering": [
        "engineer",
        "sub engineer",
        "sdo",
        "dae",
        "technician",
        "electrical",
        "mechanical",
        "civil",
        "surveyor",
        "draftsman",
        "design",
    ],
    "it": [
        "computer",
        "software",
        "developer",
        "programmer",
        "network",
        "database",
        "it officer",
        "it manager",
        "data entry",
        "system administrator",
        "web",
    ],
    "education": [
        "teacher",
        "lecturer",
        "professor",
        "educator",
        "instructor",
        "sst",
        "est",
        "pst",
        "headmaster",
        "principal",
        "school",
    ],
    "health": [
        "doctor",
        "medical officer",
        "nurse",
        "nursing",
        "pharmacist",
        "dispenser",
        "lab ",
        "laboratory",
        "radiograph",
        "lhv",
        "midwife",
        "physiotherap",
        "dental",
        "mbbs",
        "echo",
        "cssd",
        "cardiac",
        "cardio",
        "surgical",
        "operation theatre",
        "ot technician",
        "anesthesia",
        "anaesthesia",
        "dialysis",
        "x-ray",
        "radiolog",
        "dietitian",
        "registrar",
        "consultant",
        "medical",
    ],
    "finance": ["account", "audit", "finance", "cashier", "treasur", "budget"],
    "legal": ["legal", "law officer", "advocate", "prosecutor", "judicial", "judge"],
    "security": ["security", "guard", "constable", "police", "sepoy", "watchman", "chowkidar"],
    "clerical": [
        "clerk",
        "assistant",
        "stenograph",
        "steno",
        "typist",
        "record keeper",
        "office secretary",
        "data processing",
        "computer operator",
    ],
    "admin": [
        "officer",
        "manager",
        "director",
        "administrator",
        "admin",
        "coordinator",
        "supervisor",
        "inspector",
        "deputy",
        "secretary",
    ],
    "support": ["driver", "naib qasid", "qasid", "sweeper", "mali", "cook", "helper", "peon", "attendant", "khakroob", "baildar"],
}
# Order matters: the first match wins, so specific fields come before generic "admin".
# Order matters: the first match wins. Health comes before engineering so hospital
# posts like "Echo Technician" are not filed under engineering's "technician".
FIELD_PRIORITY = ["it", "health", "engineering", "education", "legal", "finance", "security", "clerical", "support", "admin"]
# "IT" only in capitals ("IT Support", "Analyst-II (IT)"); lowercase "it" is an ordinary word
_IT_RE = re.compile(r"\bIT\b")

JOB_WORDS = re.compile(r"\b(job|jobs|career|vacanc|vacant|recruit|positions?|posts?|employment|opportunit|hiring)\w*", re.I)
TEST_WORDS = re.compile(r"\b(GAT|NAT|TOEIC|HAT|aptitude test|assessment test|scholarship)\b", re.I)
ADMISSION_WORDS = re.compile(
    r"\b(admission|admissions|ms|mphil|phd|bs|bsn|program|programme|programs|course|diploma|degree|pharm\.?\s*d|fall|spring|semester)\b",
    re.I,
)


_FIELD_RES = {
    field: re.compile(r"\b(?:" + "|".join(re.escape(k.strip()) for k in words) + ")", re.I)
    for field, words in FIELD_KEYWORDS.items()
}


def classify_field(post_name: str) -> str | None:
    # Keywords match at word starts only ("est" must not match "Test")
    if _IT_RE.search(post_name):
        return "it"
    for field in FIELD_PRIORITY:
        if _FIELD_RES[field].search(post_name):
            return field
    return None


def classify_kind(title: str, post_names: list[str], text: str = "") -> str:
    joined = " ".join([title, *post_names])
    # "Admissions Test for ... Post RN BSN" / "... PBS (01 Years Program)" is an admission,
    # even though it contains "Post" or something that looks like a pay scale.
    if re.search(r"\badmissions?\b", title, re.I):
        return "admission"
    if extract_bps(joined):
        return "job"
    if JOB_WORDS.search(title):
        return "job"
    if TEST_WORDS.search(joined):
        return "test"
    if ADMISSION_WORDS.search(joined):
        return "admission"
    if extract_bps(text) or JOB_WORDS.search(text[:2000]):
        return "job"
    return "unknown"


# --- locations -------------------------------------------------------------

PROVINCE_ALIASES = {
    "Punjab": ["punjab"],
    "Sindh": ["sindh"],
    "Khyber Pakhtunkhwa": ["khyber pakhtunkhwa", "kpk", "k.p.k", "khyber-pakhtunkhwa", "kp govt"],
    "Balochistan": ["balochistan", "baluchistan"],
    "Islamabad": ["islamabad", "ict"],
    "Gilgit-Baltistan": ["gilgit", "baltistan"],
    "Azad Kashmir": ["azad jammu", "azad kashmir", "ajk", "ajk&k", "muzaffarabad"],
}

CITY_PROVINCE = {
    "Lahore": "Punjab",
    "Faisalabad": "Punjab",
    "Rawalpindi": "Punjab",
    "Multan": "Punjab",
    "Gujranwala": "Punjab",
    "Sialkot": "Punjab",
    "Bahawalpur": "Punjab",
    "Sargodha": "Punjab",
    "Sheikhupura": "Punjab",
    "Jhang": "Punjab",
    "Rahim Yar Khan": "Punjab",
    "Gujrat": "Punjab",
    "Sahiwal": "Punjab",
    "Okara": "Punjab",
    "Kasur": "Punjab",
    "Mianwali": "Punjab",
    "Dera Ghazi Khan": "Punjab",
    "Chakwal": "Punjab",
    "Attock": "Punjab",
    "Jhelum": "Punjab",
    "Kharian": "Punjab",
    "Wah Cantt": "Punjab",
    "Taxila": "Punjab",
    "Khanewal": "Punjab",
    "Vehari": "Punjab",
    "Muzaffargarh": "Punjab",
    "Layyah": "Punjab",
    "Bhakkar": "Punjab",
    "Khushab": "Punjab",
    "Hafizabad": "Punjab",
    "Mandi Bahauddin": "Punjab",
    "Narowal": "Punjab",
    "Pakpattan": "Punjab",
    "Lodhran": "Punjab",
    "Toba Tek Singh": "Punjab",
    "Nankana Sahib": "Punjab",
    "Chiniot": "Punjab",
    "Bahawalnagar": "Punjab",
    "Rajanpur": "Punjab",
    "Murree": "Punjab",
    "Karachi": "Sindh",
    "Hyderabad": "Sindh",
    "Sukkur": "Sindh",
    "Larkana": "Sindh",
    "Nawabshah": "Sindh",
    "Mirpurkhas": "Sindh",
    "Tharparkar": "Sindh",
    "Khairpur": "Sindh",
    "Gambat": "Sindh",
    "Thatta": "Sindh",
    "Jamshoro": "Sindh",
    "Dadu": "Sindh",
    "Badin": "Sindh",
    "Sanghar": "Sindh",
    "Shikarpur": "Sindh",
    "Jacobabad": "Sindh",
    "Ghotki": "Sindh",
    "Umerkot": "Sindh",
    "Tando Allahyar": "Sindh",
    "Tando Muhammad Khan": "Sindh",
    "Matiari": "Sindh",
    "Kashmore": "Sindh",
    "Peshawar": "Khyber Pakhtunkhwa",
    "Mardan": "Khyber Pakhtunkhwa",
    "Abbottabad": "Khyber Pakhtunkhwa",
    "Swat": "Khyber Pakhtunkhwa",
    "Kohat": "Khyber Pakhtunkhwa",
    "Bannu": "Khyber Pakhtunkhwa",
    "Chakdara": "Khyber Pakhtunkhwa",
    "Dir": "Khyber Pakhtunkhwa",
    "Malakand": "Khyber Pakhtunkhwa",
    "Dera Ismail Khan": "Khyber Pakhtunkhwa",
    "Mansehra": "Khyber Pakhtunkhwa",
    "Charsadda": "Khyber Pakhtunkhwa",
    "Nowshera": "Khyber Pakhtunkhwa",
    "Swabi": "Khyber Pakhtunkhwa",
    "Haripur": "Khyber Pakhtunkhwa",
    "Karak": "Khyber Pakhtunkhwa",
    "Chitral": "Khyber Pakhtunkhwa",
    "Mingora": "Khyber Pakhtunkhwa",
    "Lakki Marwat": "Khyber Pakhtunkhwa",
    "Quetta": "Balochistan",
    "Gwadar": "Balochistan",
    "Turbat": "Balochistan",
    "Khuzdar": "Balochistan",
    "Islamabad": "Islamabad",
    "Gilgit": "Gilgit-Baltistan",
    "Skardu": "Gilgit-Baltistan",
    "Muzaffarabad": "Azad Kashmir",
    "Mirpur": "Azad Kashmir",
}


def extract_locations(*texts: str | None) -> tuple[list[str], list[str]]:
    blob = " ".join(t for t in texts if t)
    lower = f" {blob.lower()} "
    cities = sorted(c for c in CITY_PROVINCE if re.search(rf"\b{re.escape(c.lower())}\b", lower))
    provinces = {CITY_PROVINCE[c] for c in cities}
    for prov, aliases in PROVINCE_ALIASES.items():
        if any(re.search(rf"\b{re.escape(a)}\b", lower) for a in aliases):
            provinces.add(prov)
    return sorted(provinces), cities


# --- posts -----------------------------------------------------------------


def _first_int(text: str | None) -> int | None:
    m = re.search(r"\d[\d,]*", text or "")
    return int(m.group().replace(",", "")) if m else None


def _age_range(text: str | None) -> tuple[int | None, int | None]:
    m = re.search(r"(\d{2})\s*(?:-|–|to)\s*(\d{2})", text or "")
    if m:
        return int(m.group(1)), int(m.group(2))
    return None, _first_int(text)


_GRADE_IN_NAME_RE = re.compile(
    r"\(\s*(?:B\.?P\.?S|BS|PPS)\.?\s*[-–:#]?\s*\d{1,2}(?:\s*(?:-|to|&)\s*\d{1,2})?\s*\)"
    r"|\b(?:B\.?P\.?S|PPS)\.?\s*[-–:#]?\s*\d{1,2}(?:\s*(?:-|to|&)\s*\d{1,2})?",
    re.I,
)


def _strip_grade(name: str) -> str:
    """'Computer Operator (BPS-12)' -> 'Computer Operator'; other brackets stay intact."""
    cleaned = re.sub(r"\s+", " ", _GRADE_IN_NAME_RE.sub(" ", name)).replace("()", "")
    return cleaned.strip(" -,") or name


_NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "ten": 10}


def experience_years(text: str | None) -> int | None:
    """'Minimum 05 years of post-qualification ...' -> 5; 'Minimum 2-Years ...' -> 2;
    'Candidates with relevant experience will be preferred' -> 0 (not required)."""
    if not text:
        return None
    m = re.search(r"(\d{1,2})\s*(?:\+\s*)?[- ]?\s*years?", text, re.I)
    if m:
        return int(m.group(1))
    m = re.search(r"\b(" + "|".join(_NUM_WORDS) + r")\b\s*(?:\(\d+\))?\s*years?", text, re.I)
    if m:
        return _NUM_WORDS[m.group(1).lower()]
    if re.search(r"preferred|fresh|not required|no experience", text, re.I):
        return 0
    return None


def _experience_clause(text: str | None) -> str | None:
    """The part of a qualification that talks about experience, if any."""
    if not text:
        return None
    m = re.search(r"[^.;()]*\bexperience\b[^.;]*", text, re.I)
    return m.group(0) if m else None


def _name_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", _strip_grade(name).lower())


def enrich_posts(posts: list[dict], table_posts: list[dict]) -> list[dict]:
    """Add qualification / experience / seat count from the advert table to posts
    that came from the portal HTML (which only has name, BPS, fee and age)."""
    import difflib

    rows = {_name_key(r["name"]): r for r in table_posts if r.get("name")}
    enriched = []
    for post in posts:
        key = _name_key(post.get("name") or "")
        match = rows.get(key)
        if match is None and rows:
            best = difflib.get_close_matches(key, rows.keys(), n=1, cutoff=0.8)
            match = rows[best[0]] if best else None
        if match:
            post = {**post}
            for field in ("qualification", "experience", "total_posts", "total_posts_shared"):
                if match.get(field) is not None and post.get(field) is None:
                    post[field] = match[field]
        enriched.append(post)
    return enriched


def normalize_post(post: dict, extracted_from: str) -> dict:
    name = post.get("name") or ""
    grades = extract_bps(name) or extract_bps(post.get("details"))
    age_min, age_max = _age_range(post.get("age_limit"))
    return {
        "post_name": _strip_grade(name),
        "post_name_raw": name,
        "bps": grades,
        "bps_min": min(grades) if grades else None,
        "bps_max": max(grades) if grades else None,
        "field": classify_field(name),
        "fee_pkr": _first_int(post.get("fee")),
        "age_min": age_min,
        "age_max": age_max,
        "mode": post.get("mode"),
        "qualification": post.get("qualification"),
        "experience": post.get("experience"),
        # Some adverts fold experience into the qualification cell ("... and having five years relevant experience")
        "experience_years_min": experience_years(post.get("experience"))
        if post.get("experience")
        else experience_years(_experience_clause(post.get("qualification"))),
        "total_posts": post.get("total_posts"),
        # True when one "No. of Positions" cell covers several posts (e.g. Engineer-II + Engineer-I: 60)
        "total_posts_shared": bool(post.get("total_posts_shared")),
        "details": post.get("details"),
        "extracted_from": extracted_from,
    }


_SERIAL_RE = re.compile(r"^\s*(?:\d{1,3}|[ivxlc]{1,5})[.)\-]\s+", re.I)


def posts_from_text(text: str) -> list[dict]:
    """Best-effort: every advert line that mentions a pay scale is treated as a post."""
    posts, seen = [], set()
    for line in text.splitlines():
        line = line.strip()
        if len(line) < 6 or len(line) > 200 or not extract_bps(line):
            continue
        name = _SERIAL_RE.sub("", line)
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        posts.append({"name": name})
    return posts


# --- listing ---------------------------------------------------------------


def normalize_listing(
    listing: dict,
    parsed_docs: list[dict] | None = None,
    attachments: list[dict] | None = None,
    table_posts: list[dict] | None = None,
    syllabus: dict[str, list[dict]] | None = None,
) -> dict:
    detail = listing.get("detail") or {}
    parsed_docs = parsed_docs or []
    advert_text = "\n\n".join(d.get("text", "") for d in parsed_docs)
    reasons: list[str] = []

    if listing.get("detail_error"):
        reasons.append("detail page could not be fetched")

    from nts.advert_info import extract_facts

    title = listing.get("title") or ""
    portal_posts = detail.get("posts") or []
    facts = extract_facts(f"{title}\n{advert_text}")
    kind = classify_kind(title, [p.get("name", "") for p in portal_posts or table_posts or []], advert_text)

    programs: list[dict] = []
    posts = portal_posts
    extracted_from = "portal_html"
    if kind in ("admission", "test"):
        # Admissions / tests are not vacancies: they get their own "programs" list
        programs, program_reasons = build_programs(portal_posts, table_posts or [], facts, title)
        reasons.extend(program_reasons)
        posts = []
    elif posts and table_posts:
        posts = enrich_posts(posts, table_posts)
    elif not posts and table_posts:
        posts = table_posts
        extracted_from = "advert_table"
        reasons.append("posts were read from the advert's positions table (OCR)")
    elif not posts and advert_text and kind != "unknown":
        posts = posts_from_text(advert_text)
        extracted_from = "advert_text"
        if posts:
            reasons.append("posts were extracted from advert text")
    vacancies = [normalize_post(p, extracted_from) for p in posts]
    attach_syllabus(vacancies, syllabus or {}, key="post_name_raw")
    attach_syllabus(programs, syllabus or {}, key="name")

    last_date = parse_date(detail.get("last_date_raw")) or parse_date(listing.get("deadline_raw"))
    if not last_date:
        reasons.append("no parseable last date")
    listing_date = parse_date(listing.get("deadline_raw"))
    if listing_date and last_date and listing_date != last_date:
        reasons.append(f"index deadline {listing_date} differs from detail page {last_date}")

    # NTS hides the "Tentative Test Date" on the page (display:none) and often leaves it
    # stale; a test before the application deadline is certainly wrong, so drop it.
    test_date = parse_date(detail.get("test_date_raw"))
    if test_date and last_date and test_date < last_date:
        test_date = None

    advert_last = facts.get("advert_last_date")
    if advert_last and last_date and advert_last != last_date:
        reasons.append(f"advert says last date {advert_last}, NTS page says {last_date}")

    if kind == "job" and not vacancies:
        reasons.append("job listing with no posts extracted")
    if kind == "unknown":
        reasons.append("could not classify listing kind")

    # Advert quality only matters when the record depends on the advert, i.e. the
    # portal gave no structured posts.
    if kind == "job" and (extracted_from != "portal_html" or not vacancies):
        for d in parsed_docs:
            if d.get("method") == "failed":
                reasons.append(f"could not read {d.get('path')}: {'; '.join(d.get('warnings') or []) or 'no text'}")
            else:
                if d.get("method") in ("ocr", "mixed") and vacancies and extracted_from == "advert_text":
                    reasons.append("posts came from OCR text")
                for w in d.get("warnings") or []:
                    reasons.append(f"partly unread {d.get('path')}: {w}")

    # Adverts mention NTS's own Islamabad address, so advert text is only a fallback
    provinces, cities = extract_locations(title, detail.get("organization"), detail.get("department"))
    if not provinces:
        # Contact blocks ("... Old Airport Rawalpindi, Phone: ...") give the head office,
        # not where the job/course is, so address and contact lines are skipped.
        own_lines = re.compile(r"\bNTS\b|national testing service|nts\.org\.pk|051-", re.I)
        advert_lines = "\n".join(
            l for l in advert_text[:6000].splitlines() if not own_lines.search(l) and not _ADDRESS_RE.search(l)
        )
        provinces, cities = extract_locations(advert_lines)

    return {
        "source": listing["source"],
        "listing_id": listing["listing_id"],
        "url": listing["url"],
        "status": listing["status"],
        "kind": kind,
        "title": title,
        "organization": detail.get("organization") or title,
        "department": detail.get("department"),
        "project_code": detail.get("project_code"),
        "deadline_label": listing.get("deadline_label"),
        "last_date": last_date,
        "announce_date": parse_date(detail.get("announce_date_raw")),
        "test_date": test_date,
        "is_expired": bool(last_date and last_date < date.today().isoformat()),
        "provinces": provinces,
        "cities": cities,
        "vacancies": vacancies,  # jobs only
        "programs": programs,  # admissions / tests only
        "test_syllabus": syllabus or {},  # post -> [{subject, weight_percent}] from "Content Weightages" files
        "advert_facts": facts,
        "attachments": attachments or [],
        "raw_html_path": listing.get("raw_html_path"),
        "needs_review": bool(reasons),
        "review_reasons": reasons,
        "scraped_at": listing.get("scraped_at"),
        "normalized_at": datetime.now(UTC).isoformat(),
    }


# --- admissions / tests ------------------------------------------------------------

_LEVEL_RE = [
    ("PhD", re.compile(r"\bPh\.?\s?D\b", re.I)),
    ("MPhil", re.compile(r"\bM\.?\s?Phil\b", re.I)),
    ("MS", re.compile(r"\bMS\b|\bM\.?S\.?c\b|\bMaster", re.I)),
    ("Pharm-D", re.compile(r"\bPharm\.?\s?-?D\b|Doctor of Pharmacy", re.I)),
    ("MBBS/BDS", re.compile(r"\bMBBS\b|\bBDS\b", re.I)),
    ("BSN", re.compile(r"\bBSN\b|\bB\.?Sc\.?\s*Nursing", re.I)),
    ("BS", re.compile(r"\bBS\b|\bBachelor|\bB\.?Sc\b|\bundergraduate", re.I)),
    ("Diploma", re.compile(r"\bdiploma\b|\bLHV\b|\bCMW\b|\bmidwi", re.I)),
    ("Certificate / course", re.compile(r"\bcertificate\b|\bcourse\b|\btraining\b|\bPBS\b", re.I)),
    ("Test", re.compile(r"\b(GAT|NAT|HAT|TOEIC)\b", re.I)),
]
_ADDRESS_RE = re.compile(
    r"\b(road|street|st-\d+|block|plot|sector|society|colony|phase|floor|building|square|airport|house\s*no|"
    r"p\.?\s?o\.?\s?box|phone|ph\.|tel|e-?mail|fax|contact|address|cell)\b|www\.|@|(?:\d[\s-]?){7,}",
    re.I,
)


def program_level(*texts: str | None) -> str | None:
    blob = " ".join(t for t in texts if t)
    return next((level for level, pattern in _LEVEL_RE if pattern.search(blob)), None)


def program_subjects(name: str, details: str | None) -> list[str]:
    """'MS/ MPhil Programs (1. Sociology 2. Social Work 3. Pashto)' -> [Sociology, Social Work, Pashto];
    'Mathematics (PhD Program)' -> [Mathematics]."""
    if details:
        items = re.split(r"\s*\d{1,2}\s*[.)]\s*", details)
        items = [re.sub(r"[()]", "", i).strip(" ,;") for i in items[1:]]
        items = [i for i in items if len(i) > 1]
        if items:
            return items
    m = re.match(r"^(.+?)\s*\((?:PhD|M\.?Phil|MS|BS)[^)]*\)\s*$", name, re.I)
    return [m.group(1).strip()] if m else []


def _match_key(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.lower())


def _find_row(name: str, rows: list[dict]) -> dict | None:
    """Table row for a portal post: exact, containment ('Generic BSN' in 'Generic BSN (04 years ...)'), or fuzzy."""
    import difflib

    key = _match_key(name)
    if not key:
        return None
    keys = {_match_key(r["name"]): r for r in rows}
    if key in keys:
        return keys[key]
    for k, row in keys.items():
        if k.startswith(key) or key.startswith(k):
            return row
    best = difflib.get_close_matches(key, keys.keys(), n=1, cutoff=0.8)
    return keys[best[0]] if best else None


def _program(
    name: str, *, details=None, fee=None, mode=None, eligibility_text=None, age_limit=None, via_nts=True, source="portal_html"
) -> dict:
    from nts.advert_info import age_range, duration
    from nts.tables import cell_items

    items = cell_items(eligibility_text) if eligibility_text else []
    edu = [i for i in items if not re.match(r"^age\b", i, re.I)]
    # Portal gives a bare "14 - 35 Years"; eligibility cells say "Age Limit: 14-35 years"
    age_min, age_max = _age_range(age_limit) if age_limit else age_range(eligibility_text or "")
    return {
        "name": name,
        "level": program_level(name, details),
        "subjects": program_subjects(name, details),
        "duration": duration(f"{name} program\n{details or ''}") or duration(f"program\n{eligibility_text or ''}"),
        "eligibility": edu,
        "age_min": age_min,
        "age_max": age_max,
        "fee_pkr": _first_int(fee),
        "mode": mode,
        "details": details,
        "via_nts": via_nts,
        "extracted_from": source,
    }


def build_programs(posts: list[dict], table_rows: list[dict], facts: dict, title: str) -> tuple[list[dict], list[str]]:
    """Programmes of an admission/test listing: the portal's list (applied through NTS),
    completed from the advert table, plus programmes that appear only on the advert."""
    reasons: list[str] = []
    programs, used = [], set()
    for post in posts:
        row = _find_row(post.get("name") or "", table_rows)
        if row:
            used.add(id(row))
        programs.append(
            _program(
                _strip_grade(post.get("name") or ""),
                details=post.get("details") or (row or {}).get("name"),
                fee=post.get("fee"),
                mode=post.get("mode"),
                eligibility_text=(row or {}).get("qualification"),
                age_limit=post.get("age_limit") or (row or {}).get("age_limit"),
            )
        )
    extra = [r for r in table_rows if id(r) not in used]
    for row in extra:
        programs.append(
            _program(
                row["name"],
                eligibility_text=row.get("qualification"),
                age_limit=row.get("age_limit"),
                via_nts=not posts,
                source="advert_table",
            )
        )
    if extra:
        reasons.append(f"{len(extra)} programme(s) were read from the advert table (OCR)")

    if not programs:
        # Banner-only listing: "Visionary Institute ..., Sukkur (BSN (Generic) 4 Year Degree
        # Program 2026-27)" -> programme "BSN (Generic) 4 Year Degree Program 2026-27"
        name = title
        for i, ch in enumerate(title):
            rest = title[i + 1 :]
            if ch == "(" and re.search(r"program|degree|course|diploma|admission", rest, re.I):
                name = rest[:-1] if rest.endswith(")") and rest.count("(") < rest.count(")") else rest
                break
        programs.append(_program(name.strip(), via_nts=True, source="listing_title"))
    # A single-programme banner: the banner's own eligibility / age apply to it
    if len(programs) == 1:
        p = programs[0]
        if not p["eligibility"]:
            p["eligibility"] = [e["text"] for e in facts.get("eligibility", [])]
        if p["age_min"] is None and p["age_max"] is None:
            p["age_min"], p["age_max"] = facts.get("age_min"), facts.get("age_max")
        if not p["duration"]:
            p["duration"] = facts.get("duration")
        if p["extracted_from"] == "listing_title" and (p["eligibility"] or p["age_max"]):
            reasons.append("programme details were read from the advert banner (OCR)")
    return programs, reasons


def attach_syllabus(items: list[dict], syllabus: dict[str, list[dict]], key: str) -> None:
    """Give each post/programme its test syllabus, matching names like the advert table."""
    if not syllabus:
        return
    rows = [{"name": name, "subjects": subjects} for name, subjects in syllabus.items()]
    for item in items:
        row = _find_row(_strip_grade(item.get(key) or ""), rows)
        item["test_syllabus"] = row["subjects"] if row else []


def save_normalized(record: dict) -> str:
    config.NORMALIZED_DIR.mkdir(parents=True, exist_ok=True)
    out = config.NORMALIZED_DIR / f"{record['listing_id']}.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf8")
    return str(out.relative_to(config.DATA_DIR))
