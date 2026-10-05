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

### Rate limiting

Public `/v1` endpoints allow `RATE_LIMIT_PER_MINUTE` (default 120) requests per client IP per minute. The count is kept
in Redis, so it is shared by all API workers and servers. Responses carry `X-RateLimit-Limit`, `-Remaining` and
`-Reset`. Over the limit, the API returns `429` with `Retry-After`. Internal endpoints and `/health` are not limited.
If Redis is down, requests are allowed (fail-open) and a warning is logged. Behind a reverse proxy, set
`FORWARDED_ALLOW_IPS` to the proxy's address so the real client IP is used.

## Accounts (`/v1/auth`, `/v1/me`)

Website users sign in **without a password**, with a 6-digit code sent to their email. The first sign-in creates the
account, with default preferences (jobs).

| Endpoint | Purpose |
|---|---|
| `POST /v1/auth/code` `{email}` | Email a sign-in code, valid 10 minutes. The answer is the same whether or not the account exists |
| `POST /v1/auth/verify` `{email, code}` | Returns `{token, expires_at, user}`. Send the token as `Authorization: Bearer <token>` |
| `POST /v1/auth/logout` | End this session (other devices stay signed in) |
| `GET /v1/me`, `PATCH /v1/me` | Profile and switches: `name`, `language`, `alerts_enabled`, `email_alerts`, `push_alerts`. Switching off cancels anything queued |
| `DELETE /v1/me` | Delete the account and everything tied to it |
| `PUT /v1/me/preferences` | Kinds, fields, provinces, BPS range, age, experience, programme levels, keywords (strictly validated) |
| `GET /v1/me/matches` | Open listings that suit the user now, closing soonest first |
| `GET /v1/me/alerts?limit=&before=&unread_only=` | **Inbox**, newest first, with `unread` count. Keyset pages: pass `next_before` as `before` |
| `POST /v1/me/alerts/read` `{ids}` or `{all: true}` | Mark as read |
| `POST /v1/me/push-subscriptions` | Register this browser for Web Push (the JSON of `PushSubscription`). At most 10 devices |
| `DELETE /v1/me/push-subscriptions` `{endpoint}` | Unregister a browser |
| `GET /v1/push/public-key` | VAPID key for `PushManager.subscribe({applicationServerKey})` |
| `POST /v1/email/unsubscribe?token=` | One-click unsubscribe from the signed link in alert emails (RFC 8058) |

Security:

- **Codes** are stored in Redis only as an HMAC (`APP_SECRET`). They are single-use, and burned after 5 wrong tries.
- **Sending is throttled:** one code per minute and five per hour per address, and 20 per hour per IP.
- **Sessions** are random 32-byte tokens. Only their SHA-256 is stored (`auth_sessions`). They expire after
  `SESSION_DAYS` (60).
- **Push endpoints** must be a real push service (FCM, Mozilla, Apple, Windows), so the notifier never calls an
  arbitrary or internal URL.
- **Sign-in is off** (503) while `APP_SECRET` is not set.

## Internal (`/v1/internal`, header `X-API-Key: $INTERNAL_API_KEY`)

For the back office and scripts. These endpoints are disabled if `INTERNAL_API_KEY` is not set.

| Endpoint | Purpose |
|---|---|
| `GET /alerts?status=` | Recent alerts (pending, sent, skipped) with the matched posts |
| `GET /admin/overview` | Users, active users, listings needing review, alerts by status, deliveries by channel and status |
| `GET /admin/review-queue`, `POST /admin/listings/{id}/verify` | Human spot checks (launch checklist) |
| `POST /admin/scrape?force=false` | Queue an NTS run now (Celery `scrape` queue) |

## Observability

- **Request ID:** every response has `X-Request-ID`. It is the client's own ID if it sent a valid one, otherwise a new
  one. The same ID is on every log line of that request and on its Sentry event. A 500 response returns
  `{"detail": "Internal server error", "request_id": ...}` and never the error details.
- **Access log:** one logfmt line per request, e.g.
  `level=INFO logger=api.access request_id=... method=GET path=/v1/listings status=200 duration_ms=12.4`.
  Requests slower than `SLOW_REQUEST_MS` (1000) are logged at WARNING. `LOG_LEVEL` sets verbosity.
- **Sentry:** set `SENTRY_DSN` (and optionally `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`) to report
  unhandled errors. No user PII is sent.

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

Settings come from `.env`: `DATABASE_URL`, `REDIS_URL`, `INTERNAL_API_KEY`, `APP_SECRET`, `SESSION_DAYS`,
`VAPID_PUBLIC_KEY`, `CORS_ORIGINS` (comma-separated),
`API_WORKERS` (uvicorn workers, default 2) and `RATE_LIMIT_PER_MINUTE` (default 120, 0 disables).

## Tests

```bash
docker compose up -d postgres
cd apps/api && uv run pytest     # throwaway <db>_apitest database, real migrations, real NTS records
```
