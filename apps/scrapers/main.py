"""Manual entry point for the NTS pipeline (no Celery needed).

uv run python main.py scrape                 # spider only; prints listings found
uv run python main.py run [--force]          # full chain: scrape -> download -> parse -> normalize
uv run python main.py process <listing_id>   # re-run the chain for one listing from the latest scrape
uv run python main.py parse <file>...        # test the PDF/OCR parser on local files
uv run python main.py show [<listing_id>] [--kind job]   # readable view for checking against the NTS site
uv run python main.py forget <listing_id>    # clear dedup state so the listing is processed again
uv run python main.py last-run               # summary of the most recent run
"""

import argparse
import json
import logging
import sys
from pathlib import Path

import config
from shared.redact import install_redaction


def _find_in_feeds(listing_id: str) -> dict | None:
    """The most recently scraped copy of a listing, searching feeds newest first
    (by file time: "manual_listings" sorts after "2026..." by name)."""
    feeds = sorted(config.RUNS_DIR.glob("*_listings.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    for feed in feeds:
        for line in feed.read_text(encoding="utf8").splitlines():
            listing = json.loads(line)
            if listing["listing_id"] == listing_id and listing.get("detail"):
                return listing
    return None


def cmd_scrape(args) -> None:
    from nts.run_spider import crawl_nts

    print("Scraping NTS (takes ~30s)...", flush=True)
    items, stats = crawl_nts(config.RUNS_DIR / "manual_listings.jsonl", include_closed_details=not args.open_only)
    for it in items:
        d = it.get("detail") or {}
        print(
            f"[{it['status']:6}] {it['listing_id']:45} {it['deadline_raw']:30} posts={len(d.get('posts', [])):2} "
            f"files={len(d.get('attachments', []))}  {it['title'][:70]}"
        )
    print(
        f"\n{len(items)} listings; responses: "
        f"{ {k.split('/')[-1]: v for k, v in stats.items() if k.startswith('downloader/response_status_count')} }"
    )


def cmd_run(args) -> None:
    from tasks import run_nts_pipeline

    print("Running NTS pipeline: scrape -> download -> parse -> normalize (can take a few minutes)...", flush=True)
    summary = run_nts_pipeline(force=args.force, include_closed_details=not args.open_only)
    print(json.dumps(summary, indent=2, default=str))


def cmd_process(args) -> None:
    from tasks import process_listing

    listing = _find_in_feeds(args.listing_id)
    if listing is None:
        sys.exit(f"{args.listing_id} not found in any scrape feed; run `main.py scrape` first")
    print(json.dumps(process_listing(listing), indent=2))


def cmd_parse(args) -> None:
    from nts.parser import parse_file

    for f in args.files:
        doc = parse_file(Path(f).resolve())
        print(f"== {f}\n   method={doc.method} pages={[(p.page, p.method, p.chars) for p in doc.pages]} warnings={doc.warnings}")
        print(doc.text[: args.chars])
        print()


def _print_record(r: dict) -> None:
    kind_label = {"job": "JOB", "admission": "Admission", "test": "Test (GAT/NAT/TOEIC)"}.get(r["kind"], r["kind"])
    print("=" * 90)
    print(f"{r['listing_id']}   [{kind_label}]")
    print(f"  Open on NTS:   {r['url']}")
    print(f"  Title:         {r['title']}")
    if r.get("department") and r["department"] != r["title"]:
        print(f"  Department:    {r['department']}")
    print(f"  Last date:     {r['last_date'] or '-'}" + ("   (EXPIRED)" if r.get("is_expired") else ""))
    if r.get("test_date"):
        print(f"  Test date:     {r['test_date']} (tentative, hidden on NTS page)")
    if r.get("provinces"):
        print(f"  Location:      {', '.join(r['provinces'])}" + (f" ({', '.join(r['cities'])})" if r.get("cities") else ""))
    facts = r.get("advert_facts") or {}
    badges = []
    if facts.get("registration_open"):
        badges.append("Applications invited" if r.get("kind") == "job" else "Registration/Admissions OPEN")
    if facts.get("session"):
        badges.append(f"Session {facts['session']}")
    if facts.get("test_by"):
        badges.append(f"Test: {facts['test_by']}")
    if facts.get("gender"):
        badges.append({"both": "Male & Female", "female": "Female only", "male": "Male only"}[facts["gender"]])
    if facts.get("benefits"):
        badges.append(", ".join(b.replace("_", " ") for b in facts["benefits"]))
    if badges:
        print(f"  On the advert:  {' | '.join(badges)}")
    if facts.get("advert_last_date"):
        print(f"  Advert deadline: {facts['advert_last_date']}")
    for req in facts.get("test_requirements") or []:
        print(f"  Requirement:    at least {req['min_percent']}% in {req['test']}")

    if r.get("programs"):
        print(f"  Programs ({len(r['programs'])}):")
        for i, p in enumerate(r["programs"], 1):
            bits = [b for b in (p.get("level"), p.get("duration")) if b]
            if p.get("fee_pkr"):
                bits.append(f"test fee Rs {p['fee_pkr']}")
            if p.get("age_min") and p.get("age_max"):
                bits.append(f"age {p['age_min']}-{p['age_max']}")
            elif p.get("age_max"):
                bits.append(f"age up to {p['age_max']}")
            if not p.get("via_nts"):
                bits.append("on advert only, no NTS test")
            print(f"    {i}. {p['name']}" + (f"  ({', '.join(bits)})" if bits else ""))
            if p.get("subjects"):
                print(f"         Subjects:    {', '.join(p['subjects'])}")
            for e in p.get("eligibility") or []:
                print(f"         Eligibility: {e}")
    elif r["vacancies"]:
        print(f"  Posts ({len(r['vacancies'])}):")
        for i, v in enumerate(r["vacancies"], 1):
            bits = []
            if v["bps"]:
                bits.append("BPS-" + "/".join(map(str, v["bps"])))
            if v.get("total_posts"):
                bits.append(
                    f"{v['total_posts']} seat(s)" + (" shared with next/previous post" if v.get("total_posts_shared") else "")
                )
            if v["fee_pkr"]:
                bits.append(f"fee Rs {v['fee_pkr']}")
            if v["age_min"] and v["age_max"]:
                bits.append(f"age {v['age_min']}-{v['age_max']}")
            elif v["age_max"]:
                bits.append(f"age up to {v['age_max']}")
            print(f"    {i}. {v['post_name']}" + (f"  ({', '.join(bits)})" if bits else ""))
            if v.get("qualification"):
                print(f"         Qualification: {v['qualification']}")
            if v.get("experience"):
                print(f"         Experience:    {v['experience']}")
            if v.get("test_syllabus"):
                parts = [
                    s["subject"] + (f" {s['weight_percent']}%" if s.get("weight_percent") is not None else "")
                    for s in v["test_syllabus"]
                ]
                print(f"         Test:          {', '.join(parts)}")
    else:
        print("  Posts:         none extracted")
    if r.get("kind") == "job" and facts.get("eligibility") and not any(v.get("qualification") for v in r["vacancies"]):
        for e in facts["eligibility"][:5]:
            print(f"  Eligibility:   {e['text']}")
    labels = {"advert": "Advert file", "syllabus": "Syllabus file", "sample_paper": "Sample paper", "other": "Other file"}
    for a in r.get("attachments", []):
        print(f"  {labels.get(a.get('role'), 'Advert file') + ':':15}data/{a['path']}")
    if r.get("needs_review"):
        print("  NEEDS REVIEW:")
        for reason in r["review_reasons"]:
            print(f"    - {reason}")


def cmd_show(args) -> None:
    """Readable view of the normalized records, for checking against the NTS site."""
    files = sorted(config.NORMALIZED_DIR.glob("*.json"))
    records = [json.loads(f.read_text(encoding="utf8")) for f in files]
    if args.listing_id:
        records = [r for r in records if r["listing_id"] == args.listing_id]
    elif args.kind:
        records = [r for r in records if r["kind"] == args.kind]
    if not records:
        sys.exit("No matching records; run `main.py run` first")
    for r in records:
        _print_record(r)
    print("=" * 90)
    print(f"{len(records)} record(s)")


def cmd_db_backfill(args) -> None:
    """Load every normalized JSON record into Postgres (after migrations)."""
    from nts.store import backfill, db_enabled

    if not db_enabled():
        sys.exit("DATABASE_URL is not set")
    files = sorted(config.NORMALIZED_DIR.glob("*.json"))
    stored, failed = backfill(files)
    print(f"Stored {stored} record(s) in Postgres, {failed} failed")


def _csv(value: str | None) -> list[str]:
    return [v.strip() for v in value.split(",") if v.strip()] if value else []


def cmd_user_add(args) -> None:
    """Dev helper (the website signs users up by email code): create/update a user."""
    from datetime import UTC, datetime

    from sqlalchemy import select

    from shared.db import session_scope
    from shared.models import Preference, User

    with session_scope(config.DATABASE_URL) as s:
        email = args.email.strip().lower()
        user = s.scalar(select(User).where(User.email == email))
        if user is None:
            user = User(email=email, name=args.name, email_verified_at=datetime.now(UTC))
            s.add(user)
        user.preference = Preference(
            kinds=_csv(args.kinds) or ["job"],
            fields=_csv(args.fields),
            provinces=_csv(args.provinces),
            keywords=_csv(args.keywords),
            program_levels=_csv(args.levels),
            bps_min=args.bps_min,
            bps_max=args.bps_max,
            age=args.age,
            max_experience_years=args.max_experience,
        )
        s.flush()
        print(f"User {user.id} ({user.email}) saved")


def cmd_match(args) -> None:
    """Show which live listings match a user, without queueing anything."""
    from sqlalchemy import select

    from shared.db import session_scope
    from shared.matching import matches_for_user
    from shared.models import Listing, Program, User, Vacancy

    with session_scope(config.DATABASE_URL) as s:
        user = s.scalar(select(User).where(User.email == args.email.strip().lower()))
        if user is None:
            sys.exit("No such user; add one with user-add")
        for m in matches_for_user(s, user):
            listing = s.get(Listing, m.listing_id)
            print(f"{listing.external_id:45} [{listing.kind}] last date {listing.last_date}  {listing.title[:60]}")
            for vid in m.vacancy_ids:
                print(f"    - {s.get(Vacancy, vid).post_name}")
            for pid in m.program_ids:
                print(f"    - {s.get(Program, pid).name}")


def cmd_queue_alerts(args) -> None:
    """Queue alerts for listings already in the DB (normally done as they arrive)."""
    from sqlalchemy import select

    from shared.db import session_scope
    from shared.matching import queue_alerts_for_listing
    from shared.models import Listing

    with session_scope(config.DATABASE_URL) as s:
        q = select(Listing.id).where(Listing.status == "open")
        if args.listing_id:
            q = q.where(Listing.external_id == args.listing_id)
        total = sum(queue_alerts_for_listing(s, lid) for lid in s.scalars(q).all())
    print(f"Queued {total} new alert(s)")


def cmd_alerts(args) -> None:
    from sqlalchemy import select

    from shared.db import session_scope
    from shared.models import Alert, Listing, User

    with session_scope(config.DATABASE_URL) as s:
        rows = s.execute(
            select(Alert, User.email, Listing.external_id, Listing.title)
            .join(User, User.id == Alert.user_id)
            .join(Listing, Listing.id == Alert.listing_id)
            .order_by(Alert.created_at.desc())
            .limit(args.limit)
        ).all()
        for alert, email, ext_id, title in rows:
            n = len(alert.matched_vacancy_ids) + len(alert.matched_program_ids)
            print(f"[{alert.status:7}] {alert.alert_type:17} {email:28} {ext_id:40} {n} match(es)  {title[:45]}")
        print(f"{len(rows)} alert(s)")


def cmd_forget(args) -> None:
    from nts import dedup

    dedup.forget_listing(args.listing_id)
    print(f"Forgot {args.listing_id}")


def cmd_last_run(args) -> None:
    runs = sorted(p for p in config.RUNS_DIR.glob("*.json"))
    if not runs:
        sys.exit("No runs yet")
    print(runs[-1].read_text(encoding="utf8"))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    install_redaction()
    p = argparse.ArgumentParser(description="LastBell NTS scraper")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("scrape")
    s.add_argument("--open-only", action="store_true", help="skip detail pages of closed listings")
    s.set_defaults(func=cmd_scrape)

    s = sub.add_parser("run")
    s.add_argument("--force", action="store_true", help="ignore dedup and re-process every open listing")
    s.add_argument("--open-only", action="store_true")
    s.set_defaults(func=cmd_run)

    s = sub.add_parser("process")
    s.add_argument("listing_id")
    s.set_defaults(func=cmd_process)

    s = sub.add_parser("parse")
    s.add_argument("files", nargs="+")
    s.add_argument("--chars", type=int, default=3000)
    s.set_defaults(func=cmd_parse)

    s = sub.add_parser("show", help="readable view of processed records")
    s.add_argument("listing_id", nargs="?")
    s.add_argument("--kind", choices=["job", "admission", "test", "unknown"])
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("db-backfill", help="load data/normalized/*.json into Postgres")
    s.set_defaults(func=cmd_db_backfill)

    s = sub.add_parser("user-add", help="dev: create/update a user and their preferences")
    s.add_argument("email")
    s.add_argument("--name")
    s.add_argument("--kinds", help="job,admission,test (default job)")
    s.add_argument("--fields", help="e.g. it,engineering,health")
    s.add_argument("--provinces", help="e.g. Punjab,Sindh")
    s.add_argument("--keywords", help="e.g. computer,nurse")
    s.add_argument("--levels", help="programme levels for admissions, e.g. BSN,MPhil,PhD")
    s.add_argument("--bps-min", type=int)
    s.add_argument("--bps-max", type=int)
    s.add_argument("--age", type=int)
    s.add_argument("--max-experience", type=int, help="years; 0 = fresh graduate")
    s.set_defaults(func=cmd_user_add)

    s = sub.add_parser("match", help="dev: live listings that match a user")
    s.add_argument("email")
    s.set_defaults(func=cmd_match)

    s = sub.add_parser("queue-alerts", help="queue alerts for open listings already in the DB")
    s.add_argument("listing_id", nargs="?")
    s.set_defaults(func=cmd_queue_alerts)

    s = sub.add_parser("alerts", help="recent queued/sent alerts")
    s.add_argument("--limit", type=int, default=30)
    s.set_defaults(func=cmd_alerts)

    s = sub.add_parser("forget")
    s.add_argument("listing_id")
    s.set_defaults(func=cmd_forget)

    s = sub.add_parser("last-run")
    s.set_defaults(func=cmd_last_run)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
