"""URL slugs for listings and hubs.

A listing's URL is /jobs/{slug}-{id}. The id keeps the URL stable: when a title or
organization is corrected the slug changes, and the website 301-redirects any old slug
for the same id to the current one. Hub slugs never end in "-<digits>", so the website
can tell /jobs/karachi (hub) from /jobs/nicvd-karachi-jobs-oct-2026-9 (listing).
"""

import re
import unicodedata
from datetime import date

_MONTHS = ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec")
MAX_SLUG = 80


def slugify(text: str | None, max_len: int = MAX_SLUG) -> str:
    """ASCII, lower case, words joined by single hyphens, cut on a word boundary."""
    if not text:
        return ""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower().replace("&", " and ")).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug


def listing_slug(
    *,
    kind: str,
    org: str | None,
    city: str | None,
    when: date | None,
    title: str | None = None,
) -> str:
    """e.g. "nicvd-karachi-jobs-oct-2026", "aiou-admission-2026", "gat-general-test-2026".

    org is the short name when known (NICVD), else the cleaned full name."""
    noun = {"job": "jobs", "admission": "admission", "test": "test"}.get(kind, "jobs")
    base = slugify(org or title, 50)
    parts = [base]
    if city and slugify(city) not in base:
        parts.append(slugify(city))
    parts.append(noun)
    if when:
        parts.append(f"{_MONTHS[when.month - 1]}-{when.year}" if kind == "job" else str(when.year))
    slug = "-".join(p for p in parts if p)
    return slug[:MAX_SLUG].strip("-") or "listing"


def listing_path_slug(slug: str, listing_id: int) -> str:
    return f"{slug}-{listing_id}"


def split_listing_path_slug(path_slug: str) -> tuple[str, int] | None:
    """ "nicvd-karachi-jobs-oct-2026-9" -> ("nicvd-karachi-jobs-oct-2026", 9); a hub slug -> None."""
    m = re.fullmatch(r"(.+)-(\d+)", path_slug)
    return (m.group(1), int(m.group(2))) if m else None
