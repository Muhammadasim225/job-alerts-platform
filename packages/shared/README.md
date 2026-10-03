# shared — database, persistence and matching

Backend code used by the scraper today and by the API and Telegram bot later.

| Module | What it does |
|---|---|
| `shared/models.py` | PostgreSQL schema: `listings`, `vacancies`, `programs`, `attachments`, `users`, `preferences`, `alerts` |
| `shared/migrations/` | Alembic migrations (`python -m shared.migrate` to apply, `... revision "msg"` to autogenerate) |
| `shared/db.py` | Engine/session from `DATABASE_URL` (psycopg 3) |
| `shared/repository.py` | `upsert_listing(session, record)`: a normalized scraper record → rows, reporting significant changes |
| `shared/matching.py` | Preference matching, idempotent alert queueing, deadline reminders, `matches_for_user` |

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

## Tests

Tests run against a throwaway `<db>_test` database on the local Postgres container, built with the real migrations:

```bash
docker compose up -d postgres
cd packages/shared && uv run pytest
```
