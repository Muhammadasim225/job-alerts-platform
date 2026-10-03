# scrapers — NTS pipeline (Phase 1)

Fetches every NTS listing, downloads the advertisements, extracts their text and
turns everything into structured records.

```
scrape (nts/spider.py) → dedup (nts/dedup.py) → download (nts/downloader.py)
      → parse + OCR (nts/parser.py) → normalize (nts/normalizer.py)
```

`tasks.py` chains these steps, `celery_app.py` and `beat_schedule.py` run the chain on a schedule.

Reading adverts (OCR only, no paid API):

- `nts/parser.py`: PDF text via pdfplumber, OCR for scanned pages and pages whose table text is drawn as outlines.
  Image banners get **multi-pass OCR** (normal + thresholded + inverted), so white or yellow text on dark boxes
  ("REGISTRATION OPEN", "SESSION 2026-27") is read too.
- `nts/tables.py`: finds a ruled table ("Name of Post | BPS | No. of Posts | Qualification | Age | Experience", or
  "Programs | Eligibility") from its ruling lines and OCRs it cell by cell. It handles merged cells, tables without
  an outer border, and faint row lines.
- `nts/advert_info.py`: layout-independent facts: registration open, session/intake, advert deadline, age, gender,
  education requirements (with minimum %), programme duration, GAT/entry-test score requirements, and perks
  (scholarship, free accommodation, merit based, and so on).
- `nts/normalizer.py`: **jobs** get `vacancies` (post, BPS, seats, qualification, experience, fee, age). **Admissions
  and tests** get `programs` (level, subjects, duration, eligibility, age, fee, `via_nts`). Both kinds get
  `advert_facts`.

Anything read from an image is best-effort OCR, and such records carry `needs_review` with the reason.

More inputs:

- **Word files** (`.docx`) are read straight from their XML. "Content Weightages" files become a per-post test
  syllabus (`nts/syllabus.py`, shown as `test_syllabus` on each post).
- **Attachment roles** (`tasks.attachment_role`): `advert` is parsed for posts and facts, `syllabus` gives the test
  content, and `sample_paper` / `other` are downloaded but never mixed into the record.
- **Closed listings** are scraped and processed too, once (dedup), for the archive.
- **Optional VLM OCR** (`nts/vlm.py`, deAPI + Nanonets-OCR-s): set `DEAPI_API_KEY` in `.env` and image adverts and
  scanned pages are read by a vision-language model instead of Tesseract. Its HTML/Markdown tables are parsed
  directly. Results are cached per image hash, so a file is never paid for twice, and calls are capped per day
  (`VLM_MAX_CALLS_PER_DAY`, default 200 strips). Without a key, or if a call fails, Tesseract is used.
  - Measured limits (Oct 2026): about $0.004–0.014 per image depending on size. The model refuses tall or
    text-dense images (`INPUT_TOO_LARGE`, refunded), so images are read in ≤800 px strips cut on blank rows, and a
    strip that is still refused is halved and retried. A 429 rate limit is waited out.
  - The VLM text is primary. Tesseract's lines that the VLM skipped (small badges such as "NASTP Kharian") are
    appended.
  - **Ruled tables still come from the pixel-grid extractor**. Strips cut long tables into inconsistent pieces
    (ISMO gave 1 post instead of 26), so VLM tables are only used for borderless designs.

## What NTS actually looks like (checked Sep 2026)

- **Index:** `https://www.nts.org.pk/new/projectsnew.php`. It has two tabs (`cont-newProjects` = open,
  `cont-oldProjects` = closed). Each listing is an `li.product` with `.product-name a` (title and link) and
  `.price .amount` ("Last Date of … is: 8th October 2026"). There is no pagination and no JS.
- **Portal detail** (`portal.nts.org.pk/Alldetail/<base64 project id>`): organization, code, announce/last/test
  dates, an attachment table (`#advertTable`), and posts (name with BPS, fee, age limit). The posts HTML is
  malformed, so it is parsed as text.
- **Legacy detail** (`nts.org.pk/Test&Products/Announced/<mm_yy>/<name>/…php`): static page with a link to the
  advertisement PDF.
- **Advertisements:** portal ads are usually **JPG/PNG images**, so OCR is required. Legacy ads are PDFs; some
  draw the positions table as vector outlines (text-less), and the parser OCRs those pages too.
- The index mixes jobs, admission tests and GAT/NAT/TOEIC. Every record gets `kind` = `job|admission|test|unknown`.

## Running

```bash
uv sync
uv run pytest                               # parsing tests against saved real pages (tests/fixtures)

uv run python main.py scrape                # spider only: prints every listing found
uv run python main.py run                   # full chain without Celery (Redis must be running)
uv run python main.py run --force           # ignore dedup, reprocess every open listing
uv run python main.py process portal-101334 # rerun one listing from the latest scrape
uv run python main.py parse some.pdf ad.jpg # test the parser / OCR on local files
uv run python main.py show [--kind job]     # readable report to check against the NTS site
uv run python main.py forget portal-101334  # clear dedup so the listing is processed next run
uv run python main.py last-run

uv run scrapy shell "https://www.nts.org.pk/new/projectsnew.php"   # try selectors interactively
```

OCR needs Tesseract. The Docker image includes it. On Windows, install it
(https://github.com/UB-Mannheim/tesseract/wiki) and set `TESSERACT_CMD` if it is not on PATH.
Without it, image adverts are recorded with `needs_review` and a clear reason, and are not silently dropped.

With Docker (from the repo root):

```bash
docker compose up -d --build redis scraper-worker scraper-beat
docker compose exec scraper-worker python main.py run          # one manual run inside the container
docker compose exec scraper-worker celery -A celery_app call tasks.scrape_nts   # queue a run via Celery
docker compose logs -f scraper-worker
```

Beat runs the pipeline **once a day** (Asia/Karachi time). The times can be changed in `.env`:

| Time | Task | Queue |
|---|---|---|
| 03:00 (`HOUSEKEEPING_HOUR`) | delete run logs older than `RUN_LOG_RETENTION_DAYS` (30) | default |
| 06:00 (`NTS_SCRAPE_HOUR`, `NTS_SCRAPE_MINUTE`) | scrape NTS, then one task per new or changed listing | scrape → process |
| 09:00 (`REMINDER_HOUR`) | queue deadline reminders `REMINDER_DAYS_BEFORE` (2) days ahead | default |

A run missed because the machine was off starts when Beat comes back. A Redis lock stops overlapping scrapes.
Listings are processed in parallel on the `process` queue (`WORKER_CONCURRENCY`, default 4). Every task is
idempotent, so a crash or redelivery never processes or alerts twice.

## Output (`data/`, git-ignored)

| Path | Contents |
|---|---|
| `raw/html/<listing_id>/<sha1>.html` | raw detail-page snapshots, one per distinct version |
| `raw/attachments/<listing_id>/` | downloaded PDFs/images |
| `parsed/<listing_id>.json` | extracted text per page, with the method used (`text`, `ocr`, `text+ocr`) |
| `normalized/<listing_id>.json` | the structured record: kind, dates, provinces/cities, vacancies (post, BPS, field, fee, age) |
| `runs/<run_id>.json` | per-run counts: listings, processed, unchanged, errors, HTTP errors |

Records with `needs_review: true` list their `review_reasons`, for example: posts guessed from advert text, OCR
used, deadline mismatch, or an unreadable file. Use these for the 50-listing spot check before launch.

Storing records in Postgres is Phase 3. The JSON shape above is the input for that schema.

## Environment variables

`REDIS_URL`, `DATA_DIR`, `TESSERACT_CMD`, `OCR_LANGS` (default `eng`), `NTS_SCRAPE_HOUR`, `WORKER_CONCURRENCY`,
`SCRAPER_DOWNLOAD_DELAY` (seconds, default 2), `SENTRY_DSN` (optional; enables error reporting from the worker and beat).
