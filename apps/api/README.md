# api — SarkariAlert backend API (FastAPI)

Interactive docs: **http://localhost:8000/docs** (OpenAPI at `/openapi.json`).

## Public, read-only (`/v1`)

| Endpoint | What it returns |
|---|---|
| `GET /v1/listings` | Listings, paginated. Default: open, not past the last date, closing soonest first |
| `GET /v1/listings/{id}` | One listing with posts / programmes, eligibility, test syllabus and advert files |
| `GET /v1/sources/{source}/listings/{external_id}` | The same, by the source's id (e.g. `nts` / `portal-101334`) |
| `GET /v1/vacancies` | Individual posts across listings, e.g. every open BPS 11–16 IT post in Punjab |
| `GET /v1/stats` | Open listings by kind, open posts and seats, closing within 7 days, last scrape time |
| `GET /v1/filters` | Values for filter menus (kinds, provinces, cities, fields, programme levels) with counts |

Filters on `/v1/listings` and `/v1/vacancies`:
`kind` (job, admission, test; repeatable), `status` (open, closed, any), `source`, `province` (repeatable), `city`,
`field` (repeatable), `bps_min`, `bps_max`, `program_level`, `q` (text), `closing_after`, `closing_before`,
`include_expired`, `sort` (closing_soon, newest, closing_last), `limit` (≤ 100) and `offset`.

Responses send `Cache-Control: public, max-age=300`, because data changes once a day. Internal columns (file paths,
raw snapshots, review notes) are never returned.

## Internal (`/v1/internal`, header `X-API-Key: $INTERNAL_API_KEY`)

For the Telegram bot and back office. These endpoints are disabled if `INTERNAL_API_KEY` is not set.

| Endpoint | Purpose |
|---|---|
| `PUT /users/{chat_id}` | Create or update a user on `/start` (default preferences: jobs) |
| `GET /users/{chat_id}` | User with preferences |
| `PUT /users/{chat_id}/preferences` | Kinds, fields, provinces, BPS range, age, experience, programme levels, keywords (strictly validated) |
| `POST /users/{chat_id}/unsubscribe`, `/resubscribe` | `/stop` and back. Unsubscribing skips pending alerts |
| `GET /users/{chat_id}/matches` | Live listings that suit the user now |
| `POST /alerts/claim?limit=50` | **Outbox:** hand out pending alerts to this sender. Safe with any number of senders (`SKIP LOCKED`) |
| `POST /alerts/{id}/sent`, `/failed` | Report delivery. Failures retry up to 3 times, or not at all when `permanent` is true |
| `GET /alerts?status=` | Recent alerts |
| `GET /admin/overview` | Active users, listings needing review, alerts by status |
| `GET /admin/review-queue`, `POST /admin/listings/{id}/verify` | Human spot checks (launch checklist) |
| `POST /admin/scrape?force=false` | Queue an NTS run now (Celery `scrape` queue) |

## Health

`GET /health` checks Postgres and Redis and returns 503 when either is down. `GET /health/live` checks only that the
process is up. The Docker healthcheck uses `/health`.

## Running

```bash
docker compose up -d --build api          # with postgres, redis, migrate
curl localhost:8000/health
curl "localhost:8000/v1/listings?kind=job&province=Punjab"
curl -H "X-API-Key: $INTERNAL_API_KEY" localhost:8000/v1/internal/admin/overview
```

Settings come from `.env`: `DATABASE_URL`, `REDIS_URL`, `INTERNAL_API_KEY`, `CORS_ORIGINS` (comma-separated) and
`API_WORKERS` (uvicorn workers, default 2).

## Tests

```bash
docker compose up -d postgres
cd apps/api && uv run pytest     # throwaway <db>_apitest database, real migrations, real NTS records
```
