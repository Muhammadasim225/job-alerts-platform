# SarkariAlert — job-alerts-platform

Pakistan government job and admission alerts. Adverts are collected from official sources (NTS first), read into
structured posts (BPS, seats, qualification, age, last date), and matched to each user's preferences. Users are alerted
by **email and Web Push**, and each match lands in their inbox on the website.

```
                 ┌──────────── scraper-beat (the one scheduler) ────────────┐
                 │ 06:00 scrape · 09:00 reminders · every 2 min dispatch     │
                 ▼                                                           ▼
 NTS ──► scraper-worker ──► Postgres ◄── api (FastAPI) ◄── website (later)   notifier ──► Mailpit / SMTP
        scrape, OCR, normalize,  ▲        public listings,                    email digests,  ──► Web Push
        match → alerts           │        sign-in, /v1/me, admin              sign-in codes
                                 └──────────────── Redis (broker, dedup, rate limits, codes)
```

| Path | What it is |
|---|---|
| [apps/scrapers](apps/scrapers/README.md) | NTS spider, downloads, PDF/image/DOCX parsing with OCR, normalizer, Celery tasks and Beat schedule |
| [apps/api](apps/api/README.md) | Public listings API, email-code sign-in, user account, inbox and push devices, back office |
| [apps/notifier](apps/notifier/README.md) | Email digests, Web Push and sign-in codes from the alert outbox |
| [packages/shared](packages/shared/README.md) | Database models and migrations, matching, notification outbox, security helpers |

## Run locally

```bash
cp .env.example .env            # fill in the secrets (see comments in the file)
docker compose build
docker compose up -d            # migrations run first (migrate service)
```

Always `docker compose up -d` after a rebuild or pull, never `docker compose start`: `start` reuses old containers
with their old images. Postgres and Redis listen on `127.0.0.1` only; connect DB tools to `127.0.0.1`, not
`localhost` (on Windows `localhost` tries IPv6 first and waits about 30 s).

Idle footprint: about 0.5 GB RAM for the whole stack. The scraper worker autoscales from 1 to `WORKER_CONCURRENCY`
processes during the daily run. Containers run as non-root users, and logs rotate (3 x 10 MB per container).

| URL | What |
|---|---|
| http://localhost:8000/docs | API docs (try the endpoints) |
| http://localhost:8025 | Mailpit: every email the system sends, locally |
| http://localhost:5555 | Flower: Celery workers and tasks (`FLOWER_BASIC_AUTH`). On demand: `docker compose --profile ops up -d flower` |

## Tests

```bash
docker compose up -d postgres redis
bash scripts/test-all.sh        # scrapers, shared, api, notifier; non-zero exit if any suite fails
```

CI (GitHub Actions) runs lint (ruff), all suites against Postgres and Redis, and the Docker builds on every push.
