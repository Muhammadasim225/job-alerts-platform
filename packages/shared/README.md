# shared — database, persistence and matching

Backend code used by the scraper, the API and the notifier.

| Module | What it does |
|---|---|
| `shared/models.py` | PostgreSQL schema: `listings`, `vacancies`, `programs`, `attachments`, `users`, `auth_sessions`, `push_subscriptions`, `preferences`, `alerts`, `deliveries` |
| `shared/migrations/` | Alembic migrations (`python -m shared.migrate` to apply, `... revision "msg"` to autogenerate) |
| `shared/db.py` | Engine/session from `DATABASE_URL` (psycopg 3) |
| `shared/repository.py` | `upsert_listing(session, record)`: a normalized scraper record → rows, reporting significant changes |
| `shared/matching.py` | Preference matching, idempotent alert queueing, deadline reminders, `matches_for_user` |
| `shared/notifications.py` | Notification outbox: batches alerts into deliveries (email digest, Web Push), exactly-once claims, retries with backoff |

## Matching rules

An empty preference list, or `None`, means "any".

- **Listing:** open, not past its last date, `kind` in `preference.kinds` (`job` / `admission` / `test`).
- **Location:** the listing's provinces overlap the user's. A listing without a known province matches everyone.
- **Job post:**
  - BPS range overlaps. Posts without BPS (company grades) are kept.
  - Field in `fields` **or** a keyword in the post name or qualification.
  - The user's age is within the age limits.
  - The required experience is at most `max_experience_years`.
- **Programme:** level in `program_levels`, a keyword in the name or subjects, and age limits.

Unknown values never exclude a post: a missed alert is worse than an extra one.

An alert is unique per `(user, listing, alert_type)` and inserted with `ON CONFLICT DO NOTHING`, so re-running the matcher
never duplicates one. Deadline reminders go only to users who were sent the first alert.

## Notifications

```
alerts (pending) --dispatch()--> deliveries: one per user per channel --notifier--> sent
```

- **One notification per batch.** A user's pending alerts are sent together once no new alert has arrived for 10
  minutes (`SETTLE`), or after 60 minutes at most (`MAX_WAIT`). A morning run with 6 matches is one email and one
  push, not 12 messages.
- **The inbox.** Dispatched alerts become `sent` and show in the user's inbox on the website, even when email and
  push are both switched off.
- **Channels.** Email needs `email_alerts` and a verified address. Push needs `push_alerts` and at least one browser
  subscription.
- **Sent once.** `claim_delivery` uses `SELECT ... FOR UPDATE SKIP LOCKED`, so any number of notifier processes, or a
  redelivered broker message, still send each notification once.
- **Retries** live in Postgres (`next_attempt_at`): 1 min, 5 min, 30 min, then 2 h, and the delivery fails after 5
  attempts. A permanent error (invalid address) fails at once. A crashed sender's claim is handed out again after 10
  minutes.

## Tests

Tests run against a throwaway `<db>_test` database on the local Postgres container, built with the real migrations:

```bash
docker compose up -d postgres
cd packages/shared && uv run pytest
```
