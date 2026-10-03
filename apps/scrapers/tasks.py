"""NTS pipeline: scrape -> dedup -> download -> parse -> normalize.

The same functions run with or without Celery:

    uv run python main.py run            # whole chain in-process, no Celery needed
    celery task `tasks.scrape_nts`       # scheduled by Beat; fans out one task per listing
"""

import json
import logging
import re
import time
from datetime import UTC, datetime

from celery.exceptions import SoftTimeLimitExceeded

import config
from celery_app import app
from nts import dedup
from nts.downloader import download_listing_attachments, listing_files_changed
from nts.normalizer import normalize_listing, save_normalized
from nts.parser import parse_file, save_parsed
from nts.run_spider import crawl_nts
from nts.store import queue_alerts, queue_reminders, store_record
from nts.syllabus import extract_test_syllabus
from nts.tables import extract_post_table, rows_from_tables

log = logging.getLogger(__name__)

LOCK_KEY = "nts:lock:scrape"
LAST_RUN_KEY = "nts:last_run"


class ScraperBroken(RuntimeError):
    """The site responded but nothing could be extracted - selectors need updating."""


_SYLLABUS_RE = re.compile(r"weightage|syllabus|test\s*pattern|content|outline", re.I)
_SAMPLE_RE = re.compile(r"sample|model[\s_-]?paper|past[\s_-]?paper", re.I)
_OTHER_RE = re.compile(r"answer|result|challan|form\b|instruction|undertaking|affidavit", re.I)


def attachment_role(f: dict) -> str:
    """advert | syllabus | sample_paper | other, from the attachment's name and file name.

    Only adverts are read for posts and facts; syllabi give the test content per post;
    sample papers and forms are kept on disk but never parsed into the record (a sample
    paper once put "SAMPLE PAPER DAE INTERMEDIATE 1" into eligibility)."""
    label = f"{f.get('name') or ''} {f.get('path') or ''}"
    if _SAMPLE_RE.search(label):
        return "sample_paper"
    if _SYLLABUS_RE.search(label):
        return "syllabus"
    if _OTHER_RE.search(label):
        return "other"
    return "advert"


def is_advert_file(f: dict) -> bool:
    return attachment_role(f) == "advert"


def process_listing(listing: dict) -> dict:
    """Download, parse and normalize one listing, then mark it as processed."""
    downloaded, download_errors = download_listing_attachments(listing)
    for f in downloaded:
        f["role"] = attachment_role(f)

    adverts = [f for f in downloaded if f["role"] == "advert"]
    if not adverts and downloaded:
        # A single unlabelled file is the advert, whatever it is called
        adverts = [f for f in downloaded if f["role"] != "sample_paper"][:1]
    syllabus_files = [f for f in downloaded if f["role"] == "syllabus"]

    docs = [parse_file(f["path"]) for f in adverts]
    syllabus_docs = [parse_file(f["path"]) for f in syllabus_files]
    all_docs = docs + syllabus_docs
    parsed_path = save_parsed(listing["listing_id"], all_docs) if all_docs else None
    syllabus = extract_test_syllabus([t for d in syllabus_docs + docs for t in d.tables])

    parsed = [d.to_dict() for d in docs]
    record = normalize_listing(listing, parsed, downloaded, syllabus=syllabus)
    table_sources = [f for f in adverts if not f["path"].lower().endswith((".docx", ".doc"))]
    if record["kind"] in ("job", "admission") and table_sources:
        # Read the advert's positions / programmes table cell by cell. It supplies the
        # posts when the portal has none, and qualification / experience / seat counts
        # (jobs) or eligibility per programme (admissions) either way. Slow OCR, so
        # not for GAT/NAT/TOEIC test listings.
        # Ruled tables: read from the table's own grid lines (exact, cell by cell). The
        # VLM reads tall adverts in strips, which breaks long tables into pieces with
        # shifting columns (ISMO: 1 post instead of 26), so its tables are only the
        # fallback for borderless designs where no grid is found.
        table_posts = [p for f in table_sources for p in extract_post_table(str(config.DATA_DIR / f["path"]))]
        if not table_posts:
            table_posts = rows_from_tables([t for d in docs for t in d.tables])
        if table_posts:
            record = normalize_listing(listing, parsed, downloaded, table_posts=table_posts, syllabus=syllabus)
    record["parsed_text_path"] = parsed_path
    for err in download_errors:
        record["review_reasons"].append(f"download failed: {err['url']} ({err['error']})")
    for url in listing.get("replaced_attachments", []):
        # Same page, new advert file: likely a corrigendum; worth a human look
        record["review_reasons"].append(f"advert file was replaced on the server: {url}")
    record["needs_review"] = bool(record["review_reasons"])
    record["is_new"] = not dedup.was_seen_before(listing["listing_id"])
    out = save_normalized(record)
    # Raises on a DB error: the listing then stays unmarked and is retried next run
    stored = store_record(record)
    alerts_queued = queue_alerts(stored, record)

    if download_errors:
        # Leave it unmarked so the next run retries the missing file (a Word file
        # once failed only because .docx was not an accepted type yet).
        log.warning("Not marking %s processed: %d attachment(s) failed", listing["listing_id"], len(download_errors))
    else:
        dedup.mark_processed(listing)
    log.info(
        "Processed %s: kind=%s vacancies=%d last_date=%s review=%s",
        listing["listing_id"],
        record["kind"],
        len(record["vacancies"]),
        record["last_date"],
        record["needs_review"],
    )
    return {
        "listing_id": listing["listing_id"],
        "kind": record["kind"],
        "vacancies": len(record["vacancies"]),
        "is_new": record["is_new"],
        "needs_review": record["needs_review"],
        "output": out,
        "db": stored,
        "alerts_queued": alerts_queued,
    }


def run_nts_pipeline(dispatch=None, force: bool = False, include_closed_details: bool = True) -> dict:
    """Scrape NTS and process every new/changed open listing.

    dispatch: None processes listings in this process; otherwise a callable that
              receives each listing (used by Celery to queue one task per listing).
    force:    re-process listings even if their fingerprint is unchanged.
    """
    started = time.monotonic()
    started_at = datetime.now(UTC)
    run_id = started_at.strftime("%Y%m%dT%H%M%SZ")
    feed = config.RUNS_DIR / f"{run_id}_listings.jsonl"

    items, stats = crawl_nts(feed, include_closed_details=include_closed_details)
    summary: dict = {
        "run_id": run_id,
        "started_at": started_at.isoformat(),
        "listings_total": len(items),
        "open": sum(1 for i in items if i["status"] == "open"),
        "closed": sum(1 for i in items if i["status"] == "closed"),
        "detail_failures": sum(1 for i in items if i.get("detail_error")),
        "unchanged": 0,
        "in_flight": 0,
        "files_replaced": [],
        "processed": [],
        "dispatched": [],
        "errors": [],
        "http_errors": {k: v for k, v in stats.items() if "response_status_count" in k and not k.endswith("/200")},
    }

    if not items:
        summary["errors"].append("spider returned 0 listings")
        _write_run_log(summary, started)
        raise ScraperBroken(f"NTS spider returned no listings (run {run_id}); check selectors in nts/spider.py")

    for listing in items:
        if listing["status"] != "open":
            dedup.update_status(listing)
            if not listing.get("detail"):
                continue  # closed and its page is gone / not fetched: nothing to add
        if listing.get("detail_error"):
            # Don't mark it seen - try again next run
            summary["errors"].append({"listing_id": listing["listing_id"], "error": listing["detail_error"]})
            continue
        if not force and not dedup.is_new_or_changed(listing):
            # The page is the same, but NTS sometimes replaces the advert file under
            # the same URL (corrigendum, extended date, extra posts).
            replaced = listing_files_changed(listing)
            if not replaced:
                summary["unchanged"] += 1
                continue
            listing["replaced_attachments"] = replaced
            summary["files_replaced"].append(listing["listing_id"])
        if not dedup.claim(listing):
            # An overlapping run already queued this exact version
            summary["in_flight"] += 1
            continue

        if dispatch is not None:
            dispatch(listing)
            summary["dispatched"].append(listing["listing_id"])
            continue
        try:
            summary["processed"].append(process_listing(listing))
        except Exception as exc:
            log.exception("Failed to process %s", listing["listing_id"])
            summary["errors"].append({"listing_id": listing["listing_id"], "error": f"{type(exc).__name__}: {exc}"})
        finally:
            dedup.release_claim(listing)

    _write_run_log(summary, started)
    return summary


def _write_run_log(summary: dict, started: float) -> None:
    summary["duration_s"] = round(time.monotonic() - started, 1)
    summary["finished_at"] = datetime.now(UTC).isoformat()
    config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
    (config.RUNS_DIR / f"{summary['run_id']}.json").write_text(json.dumps(summary, indent=2, default=str), encoding="utf8")
    try:
        dedup.get_redis().set(LAST_RUN_KEY, json.dumps(summary, default=str))
    except Exception:
        log.warning("Could not store last run summary in Redis", exc_info=True)
    log.info(
        "NTS run %s: %d listings (%d open), %d processed, %d dispatched, %d unchanged, %d errors in %ss",
        summary["run_id"],
        summary["listings_total"],
        summary["open"],
        len(summary["processed"]),
        len(summary["dispatched"]),
        summary["unchanged"],
        len(summary["errors"]),
        summary["duration_s"],
    )


# --- Celery tasks ------------------------------------------------------------


@app.task(
    name="tasks.scrape_nts",
    bind=True,
    autoretry_for=(RuntimeError, OSError),
    dont_autoretry_for=(ScraperBroken, SoftTimeLimitExceeded),
    retry_backoff=60,
    retry_backoff_max=900,
    max_retries=3,
)
def scrape_nts(self, force: bool = False) -> dict:
    lock = dedup.get_redis().lock(LOCK_KEY, timeout=60 * 30, blocking=False)
    if not lock.acquire():
        log.info("Previous NTS scrape still running; skipping")
        return {"skipped": "locked"}
    try:
        return run_nts_pipeline(dispatch=lambda listing: process_nts_listing.delay(listing), force=force)
    finally:
        try:
            lock.release()
        except Exception:
            pass


@app.task(
    name="tasks.process_nts_listing",
    autoretry_for=(Exception,),
    dont_autoretry_for=(SoftTimeLimitExceeded,),
    retry_backoff=30,
    retry_backoff_max=600,
    max_retries=4,
)
def process_nts_listing(listing: dict) -> dict:
    # A redelivered task (worker restart, acks_late) for a version that is already done
    if not listing.get("replaced_attachments") and not dedup.is_new_or_changed(listing):
        dedup.release_claim(listing)
        return {"listing_id": listing["listing_id"], "skipped": "already processed"}
    result = process_listing(listing)
    dedup.release_claim(listing)
    return result


@app.task(name="tasks.queue_deadline_reminders")
def queue_deadline_reminders_task(days_before: int = 2) -> int:
    """Daily: second alert N days before the last date (sent by the bot, Phase 5)."""
    n = queue_reminders(days_before)
    log.info("Queued %d deadline reminder(s)", n)
    return n


def cleanup_old_runs(retention_days: int, keep_latest: int = 5) -> int:
    """Delete run summaries and scrape feeds older than retention_days, always keeping
    the newest few (main.py process reads the latest feed). Returns files deleted."""
    cutoff = time.time() - retention_days * 86400
    files = sorted(config.RUNS_DIR.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
    deleted = 0
    for path in files[keep_latest:]:
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            deleted += 1
    return deleted


@app.task(name="tasks.housekeeping")
def housekeeping() -> dict:
    """Daily: keep disk usage flat (raw snapshots and attachments are kept; they are
    deduplicated by content and are the debugging record of each listing)."""
    deleted = cleanup_old_runs(config.RETENTION_DAYS)
    log.info("Housekeeping: deleted %d old run file(s)", deleted)
    return {"deleted_run_files": deleted}
