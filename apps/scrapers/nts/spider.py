"""Scrapy spider for NTS open/closed application listings.

Page structure (checked against the live site, Sep 2026):

  projectsnew.php
    div[data-tabs-id="cont-newProjects"]  -> "Open Applications" tab
    div[data-tabs-id="cont-oldProjects"]  -> "Closed Applications" tab
      li.product
        .product-name a           title + detail URL
        .price .amount            "Last Date of ... is: 8th October 2026"

  Detail pages come in two shapes:
    portal.nts.org.pk/Alldetail/<base64 id>   structured: org, code, dates, attachment table, posts
    nts.org.pk/Test&Products/Announced/...    old static page: a title and a link to the advert PDF

Everything is server-rendered (no pagination, no JS), so plain Scrapy is enough.
Every fetched page is also saved as a raw snapshot, keyed by content hash.
"""

import hashlib
import re
from datetime import UTC, datetime
from urllib.parse import quote, urljoin

import scrapy
from scrapy.http import Response

import config
from nts.common import SOURCE, clean_text, detail_kind, listing_id_from_url

TABS = {"cont-newProjects": "open", "cont-oldProjects": "closed"}

ATTACHMENT_EXT_RE = re.compile(r"\.(pdf|jpe?g|png|gif|webp|tiff?)$", re.I)
# Logos and page chrome on the old static pages
IGNORED_ATTACHMENT_RE = re.compile(r"(logo|banner|header|footer|icon)", re.I)
POST_FIELD_RE = re.compile(
    r"^(?P<name>.*?)\s*(?:\((?P<mode>Online|Offline|Manual)\))?\s*(?:Apply Now)?\s*"
    r"(?:Total Posts?:\s*(?P<total>\d+))?\s*"
    r"(?:Fee:\s*(?P<fee>.*?))?\s*(?:Age Limit:\s*(?P<age>.*?))?\s*(?:Details:\s*(?P<details>.*))?$",
    re.I,
)


def safe_url(url: str) -> str:
    """NTS links contain raw spaces and '&' in paths; percent-encode what needs it."""
    return quote(url, safe=":/?&=%#+,;@~")


def parse_listing_page(response: Response) -> list[dict]:
    """Extract every listing from both tabs of projectsnew.php."""
    listings = []
    for tab_id, status in TABS.items():
        for li in response.css(f'div[data-tabs-id="{tab_id}"] li.product'):
            link = li.css(".product-name a")
            href = link.attrib.get("href")
            if not href:
                continue
            url = urljoin(response.url, href.strip())
            amount = clean_text(" ".join(li.css(".price .amount").xpath(".//text()").getall()))
            label, _, date_text = amount.partition(" is:")
            listings.append(
                {
                    "source": SOURCE,
                    "listing_id": listing_id_from_url(url),
                    "status": status,
                    "title": clean_text(" ".join(link.xpath(".//text()").getall())),
                    "url": url,
                    "detail_kind": detail_kind(url),
                    "deadline_label": clean_text(label.replace("Details", "")),
                    "deadline_raw": clean_text(date_text.replace("Details", "")),
                }
            )
    return listings


def _span_value(spans: list[str], prefix: str) -> str | None:
    for text in spans:
        if text.lower().startswith(prefix.lower()):
            return clean_text(text[len(prefix) :].lstrip(": "))
    return None


def parse_posts(text: str) -> list[dict]:
    """Split the portal's "Post Name: ... Fee: ... Age Limit: ..." text into posts."""
    posts: list[dict] = []
    seen: set[str] = set()
    for chunk in text.split("Post Name:")[1:]:
        chunk = clean_text(chunk)
        if not chunk or chunk in seen:
            continue
        seen.add(chunk)
        m = POST_FIELD_RE.match(chunk)
        if not m:
            posts.append({"name": chunk, "raw": chunk})
            continue
        posts.append(
            {
                "name": clean_text(m.group("name")),
                "mode": m.group("mode"),
                "total_posts": int(m.group("total")) if m.group("total") else None,
                "fee": clean_text(m.group("fee")) or None,
                "age_limit": clean_text(m.group("age")) or None,
                "details": clean_text(m.group("details")) or None,
                "raw": chunk,
            }
        )
    return posts


def parse_portal_detail(response: Response) -> dict:
    project = response.css("#projectDiv")
    headings = [clean_text(t) for t in project.css("h4::text").getall()]
    spans = [clean_text(t) for t in project.css("span::text").getall() if clean_text(t)]

    organization = next((h for h in headings if h and not h.lower().startswith(("last application", "attachment"))), None)
    last_date = next((h.split(":", 1)[1].strip() for h in headings if h.lower().startswith("last application date")), None)
    code = _span_value(spans, "Code")
    department = next((s for s in spans if not re.match(r"^(code|announce date|tentative test date)\b|^\(", s, re.I)), None)

    attachments = []
    for row in response.css("#advertTable tbody tr"):
        href = row.css("a::attr(href)").get()
        if not href:
            continue
        attachments.append(
            {
                "name": clean_text(" ".join(row.css("td:nth-child(2)").xpath(".//text()").getall())) or "Attachment",
                "url": safe_url(urljoin(response.url, href.strip())),
            }
        )

    # The post markup is malformed (unclosed divs), so parse it as text instead of by element.
    posts_text = " ".join(response.css(".invoice-product-details").xpath(".//text()").getall())
    posts_text = posts_text.split("Terms & Conditions")[0]

    return {
        "organization": organization,
        "department": department,
        "project_code": code,
        "last_date_raw": last_date,
        "announce_date_raw": _span_value(spans, "Announce Date"),
        "test_date_raw": _span_value(spans, "Tentative Test Date"),
        "attachments": attachments,
        "posts": parse_posts(posts_text),
    }


def parse_legacy_detail(response: Response) -> dict:
    """Old static pages: title text, a deadline, and a link to the advertisement file."""
    body_text = clean_text(" ".join(response.xpath("//body//text()[not(ancestor::script) and not(ancestor::style)]").getall()))
    attachments = []
    seen = set()
    for a in response.css("a[href]"):
        href = a.attrib["href"].strip()
        if not ATTACHMENT_EXT_RE.search(href.split("?")[0]) or IGNORED_ATTACHMENT_RE.search(href):
            continue
        url = safe_url(urljoin(response.url, href))
        if url in seen:
            continue
        seen.add(url)
        attachments.append({"name": "Advertisement", "url": url})

    m = re.search(r"Last Date for\s+Application Submission\s*:\s*(.+?\d{4})", body_text, re.I)
    return {
        "organization": None,
        "department": None,
        "project_code": None,
        "last_date_raw": clean_text(m.group(1)) if m else None,
        "announce_date_raw": None,
        "test_date_raw": None,
        "attachments": attachments,
        "posts": [],
        "page_text": body_text[:5000],
    }


# Cloudflare re-obfuscates e-mail addresses with fresh random hex on every request
_VOLATILE_RE = re.compile(rb'(email-protection#|data-cfemail=")[0-9a-f]+')


def save_snapshot(listing_id: str, body: bytes) -> str:
    """Store raw HTML once per distinct content, so structure changes can be debugged later."""
    digest = hashlib.sha1(_VOLATILE_RE.sub(rb"\1", body)).hexdigest()[:16]
    folder = config.RAW_HTML_DIR / listing_id
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{digest}.html"
    if not path.exists():
        path.write_bytes(body)
    return str(path.relative_to(config.DATA_DIR))


class NtsSpider(scrapy.Spider):
    name = "nts"
    allowed_domains = ["nts.org.pk"]

    custom_settings = {
        "USER_AGENT": config.USER_AGENT,
        "ROBOTSTXT_OBEY": True,
        "DOWNLOAD_DELAY": config.DOWNLOAD_DELAY,
        "DOWNLOAD_DELAY_JITTER": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": config.DOWNLOAD_DELAY,
        "RETRY_TIMES": 3,
        "DOWNLOAD_TIMEOUT": 60,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        },
        "LOG_LEVEL": "INFO",
    }

    def __init__(self, include_closed_details: str = "true", *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Closed listings' detail pages are fetched too (their full data is kept for the
        # archive / SEO pages); dedup makes that a one-time cost per listing.
        self.include_closed_details = str(include_closed_details).lower() in ("1", "true", "yes")
        self.scraped_at = datetime.now(UTC).isoformat()

    async def start(self):
        yield scrapy.Request(config.NTS_LISTING_URL, callback=self.parse)

    def parse(self, response: Response):
        listings = parse_listing_page(response)
        self.logger.info(
            "NTS index: %d open, %d closed",
            sum(1 for x in listings if x["status"] == "open"),
            sum(1 for x in listings if x["status"] == "closed"),
        )
        if not listings:
            # Zero listings almost always means the page layout changed.
            self.logger.error("NTS index returned 0 listings - selectors may be broken")
            self.crawler.stats.set_value("nts/zero_listings", True)

        for listing in listings:
            listing["scraped_at"] = self.scraped_at
            if listing["status"] == "open" or self.include_closed_details:
                yield scrapy.Request(
                    safe_url(listing["url"]),
                    callback=self.parse_detail,
                    errback=self.detail_failed,
                    cb_kwargs={"listing": listing},
                    dont_filter=True,
                )
            else:
                yield listing

    def parse_detail(self, response: Response, listing: dict):
        if listing["detail_kind"] == "portal":
            detail = parse_portal_detail(response)
        else:
            detail = parse_legacy_detail(response)
        listing["detail"] = detail
        listing["raw_html_path"] = save_snapshot(listing["listing_id"], response.body)
        self.crawler.stats.inc_value("nts/details_ok")
        yield listing

    def detail_failed(self, failure):
        listing = failure.request.cb_kwargs["listing"]
        self.logger.warning("Detail page failed for %s: %s", listing["url"], failure.value)
        self.crawler.stats.inc_value("nts/details_failed")
        listing["detail"] = None
        listing["detail_error"] = repr(failure.value)
        yield listing
