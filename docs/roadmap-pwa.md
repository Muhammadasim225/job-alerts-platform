# Roadmap: LastBell PWA (backend APIs + Next.js frontend + Contabo deploy)

Status: 2026-10-10, for review. Inputs: the Claude Design canvas "LastBell — Design System" (29 artboards),
[frontend-blueprint.md](frontend-blueprint.md), [brand-and-design-prompts.md](brand-and-design-prompts.md), the current
code (map below), and an external AI review of the stack (§3).

**Rule for this phase:** the backend that exists works and is tested. We **add** to it; we do not rewrite it.

---

## 1. Where we stand

| Area | Exists today | Gap for the PWA |
|---|---|---|
| Data | Postgres 16: listings, vacancies, programs, attachments, users, sessions, preferences, alerts, deliveries, push_subscriptions (Alembic, 3 migrations) | org registry, slugs, deadline datetime + history, saved listings, education level, gender, apply URL |
| Scraping | NTS via Scrapy; pdfplumber → Tesseract (+ grid-table OCR) → **deAPI VLM (Nanonets-OCR-s)** fallback with cache + daily cap; Redis fingerprint dedup; raw snapshots | PPSC/FPSC sources, NTS lifecycle (roll slip, result), a numeric confidence |
| Alerts | Matching, transactional outbox (`deliveries`), `FOR UPDATE SKIP LOCKED` claims, retries, email (SMTP) + Web Push (VAPID), digest settle window, reminders 2 days before | reminders for **saved** listings, "extended" alerts, lifecycle alerts |
| API | FastAPI `/v1`: listings, vacancies, stats, filters, auth (email code), me (prefs, matches, inbox, push), unsubscribe, internal admin | hub endpoints, by-slug lookup, org pages, saved, match-count preview, report-error, sitemap feed, `indexable` flag |
| Web | — (`apps/web` does not exist) | everything |
| Ops | docker-compose (api, postgres, redis, migrate, scraper worker + beat, notifier, mailpit, flower), Sentry hooks, CI (ruff + 4 test suites + image builds) | prod compose, TLS/reverse proxy, Cloudflare, backups, uptime/heartbeat monitoring |

---

## 2. Design review (canvas, 29 artboards)

**Verdict: approved as the build reference.** It follows the blueprint: 10-second hero, status chips with words, text
posts table, two actions on listings, prefilled wizard, inline install card, no popups, OG images without countdowns,
digest with reminders above new jobs.

Corrections and data the design assumes (✱ = needs backend work in W0/W1):

| # | Board | Item | Action |
|---|---|---|---|
| 1 | all | Wordmark uses the Poppins web font from Google Fonts | Build ships the wordmark as an **SVG outline**; no font download (performance rule) |
| 2 | Home | "Aaj 214 jobs check ki gayin" | ✱ add `checked_today` to `/v1/stats` |
| 3 | Listing | "Last date 13 Oct, 5:00 PM" | ✱ deadline as datetime (`last_date_at`, PKT); show the time only when known |
| 4 | Listing, cards | "Kaun: Male · Female", "Female bhi" | ✱ `vacancies.gender` from `advert_facts.gender` |
| 5 | Listing | Eligibility checker education list (Matric … BSN, Pharm-D) | ✱ `vacancies.education_levels[]` + a fixed taxonomy |
| 6 | Extended header | "NTS ne 11 Oct ko notice jari kiya" | ✱ `deadline_changes` table (old, new, detected_at, source) |
| 7 | Wizard step 1 | Live match count | ✱ `GET /v1/match-count` (public, cached) |
| 8 | Listing / sign-in sheet | "Reminder lagayein" | ✱ saved listings + reminders for saved listings |
| 9 | Settings | Data download + delete | ✱ `GET /v1/me/export` (delete exists) |
| 10 | Inbox | 4 alert types incl. roll slip/result | At launch show only new / reminder / extended; lifecycle comes with lifecycle scraping (W8) |
| 11 | About | Founder name; "PPSC 762,392 applicants (2024)" | **Owner to confirm** name and keep the source link for the stat, or remove it |
| 12 | Home/Hub | Counts per hub (Karachi 23 …) | ✱ hub counts endpoint |
| 13 | Empty hub | "Pichli job: … band hui 21 Sep" | ✱ last closed listing per hub (same endpoint) |

---

## 3. The external AI review: what we adopt

| Suggestion | Decision | Why (our context) |
|---|---|---|
| Keep FastAPI, Postgres (+pg_trgm, FTS), Next.js App Router + Tailwind v4 + shadcn, Serwist, VAPID push, email-OTP, Docker Compose | ✅ Keep (already chosen) | Matches the code and plan |
| **Cloudflare (free) in front** | ✅ Adopt at deploy | PK edge PoPs cut TTFB on mobile data, free TLS, DDoS/bot shield, hides the Contabo IP |
| Replace Celery with Procrastinate/Dramatiq | ❌ Not now | Celery is built, tested and in CI. Rewriting adds risk for no user value. We **drop Flower in prod** and keep the ops profile |
| OCR: pdfplumber → PaddleOCR → vision LLM | ⚠️ Partly | We already have pdfplumber → Tesseract → **deAPI VLM** with cache and cap. Keep deAPI as the main fallback. Add a **confidence score** and route low scores to review. PaddleOCR only if Tesseract misses stay high after measuring |
| Scrapy → httpx + selectolax | ⚠️ New sources only | NTS stays on Scrapy. PPSC/FPSC modules may use httpx + selectolax (lighter) behind the same `store_record` contract |
| Email via SES or Brevo, SPF/DKIM/DMARC, List-Unsubscribe | ✅ Brevo free first (works with our SMTP code, no code change); SES later | §6 |
| Sentry + Healthchecks.io + UptimeRobot | ✅ Adopt (all free) | A silent scraper stop kills the product; heartbeat after every run |
| openapi-typescript contract | ✅ Adopt | FastAPI already emits OpenAPI; types generated in CI |
| Daily pg_dump to R2/B2 + restore test | ✅ Adopt | Contabo reliability is average; R2 10 GB free |
| No Kubernetes, microservices, Kafka, Mongo, GraphQL, search engine, native app | ✅ Agree | One 8 GB VPS + Cloudflare is enough for 50–100K subscribers |
| Astro vs Next | Next.js, with discipline | Server Components by default; `"use client"` only for chips, eligibility checker, wizard, inbox, push button |

---

## 4. Target architecture (simple, reliable, no new moving parts)

```
                 Cloudflare (DNS, TLS, cache static, WAF)
                                │
                    Contabo VPS (Docker Compose)
   ┌────────────────────────────┼─────────────────────────────────┐
   │ existing linkduk-caddy (80/443) + a lastbell.pk site block    │
   │   ├── web   Next.js  127.0.0.1:3100 (ISR cache on a volume)   │
   │   └── api   FastAPI  127.0.0.1:8100 /v1                       │
   │ postgres 16 (volume)   redis 7 (cache, rate limit, locks)     │
   │ scraper-worker + scraper-beat (Celery)  notifier (Celery)     │
   │ backup (cron container → pg_dump → R2)                        │
   └───────────────────────────────────────────────────────────────┘
```

### 4.0 The real server (checked 2026-10-10) and what it changes

Contabo VPS: 4 vCPU (Broadwell 2.0 GHz), 7.8 GiB RAM (6.8 available), **no swap**, 96 GB disk (14 % used), Ubuntu
24.04, EU data centre (CEST clock), "system restart required" with 23 pending updates.

**It is shared.** Another project ("linkduk") already runs there: `linkduk-caddy` owns ports 80/443, plus
`linkduk-frontend` (127.0.0.1:3000), `linkduk-backend` (:5001), `linkduk-redis` (:6379), `postgres-db` (:5432) and
`rabbitmq` (:5672/15672). Consequences for our prod setup:

1. **No host ports for our Postgres and Redis.** They live only on our private Docker network (`lastbell_internal`), so
   they never clash with :5432/:6379 and are unreachable from outside. Only `web` and `api` publish ports, on unused
   loopback ports (`127.0.0.1:3100` web, `127.0.0.1:8100` api).
2. **No second Caddy.** Ports 80/443 are taken. We add a `lastbell.pk` site block to the **existing** Caddy that proxies
   to 127.0.0.1:3100 and :8100. This touches the other project's Caddyfile, so it is done only with the owner's
   go-ahead at deploy time (W7).
3. **Our own Postgres container and volume** (not the shared `postgres-db`): isolation, separate backups, independent
   upgrades. RAM cost ≈ 200–400 MB, which fits.
4. **Add a 4 GB swap file** before deploy. Without swap, an OCR spike (Tesseract/pdf rendering in the scraper worker)
   can OOM-kill containers of both projects.
5. **Memory budget** (limits in compose): postgres 768 MB, redis 128 MB, api 384 MB, web 512 MB, scraper worker 1.5 GB
   (concurrency 2), beat 128 MB, notifier 256 MB, backup 128 MB → ≈ 3.8 GB, leaving room for linkduk.
6. **EU server, Pakistani users:** ~150 ms round trip without a CDN, so **Cloudflare is required**, not optional.
7. Apply the pending OS updates and reboot in a quiet hour (affects linkduk too; owner's call).

### 4.1 Events without an event bus (the "event streaming" we actually need)

One table, written **in the same transaction** as the data change (transactional outbox, like `deliveries`):

`listing_events (id, listing_id, type, payload jsonb, created_at, processed_at)`, types: `created`, `deadline_changed`,
`closed`, `reopened`, `updated`.

A Celery task (every minute, `FOR UPDATE SKIP LOCKED`) consumes unprocessed events and:

1. calls the web app's `POST /api/revalidate` (secret header) with the listing path and its hub tags;
2. queues alerts (new → matching users; deadline_changed → users who saved it or were alerted);
3. invalidates the Redis hub-count cache.

This gives us ordered, replayable, at-least-once processing with zero new infrastructure. Kafka/Redis Streams are not
needed at our volume (tens of listings per day).

### 4.2 Correctness rules (ACID, idempotency, locks): where each one applies

| Risk | Guard | Status |
|---|---|---|
| Same advert scraped twice | Redis fingerprint + claim key; DB upsert on `(source, external_id)` | ✅ exists |
| Duplicate alert to a user | `UNIQUE (user, listing, alert_type)` + `ON CONFLICT DO NOTHING` | ✅ exists |
| Two workers send the same delivery | `FOR UPDATE SKIP LOCKED` claim, committed before sending | ✅ exists |
| Data change without its event | Insert `listing_events` in the **same transaction** as the upsert | W0 |
| Saving a listing twice / double tap | `UNIQUE (user_id, listing_id)` + `ON CONFLICT DO NOTHING`, endpoint is PUT (idempotent) | W0 |
| Overlapping scheduled runs | Redis lock (scrape) + Postgres advisory lock for the event consumer | W0 |
| Revalidation storms | Revalidate by tag, deduplicate tags per consumer batch | W0 |
| Login code reuse | Single-use HMAC in Redis, burn after 5 tries | ✅ exists |

### 4.3 Backend structure (clean, matches what exists)

- `packages/shared`: models, repository (write side), matching, notifications, **new**: `orgs.py` (normalization),
  `slugs.py`, `events.py`, `taxonomy.py` (education levels, gender).
- `apps/api/app`: routers stay thin (validate → query → schema). Queries live in `queries.py`/new `hubs.py`. No business
  rules in routers.
- `apps/scrapers`: per-source module behind one contract (`store_record` + event). New sources do not touch NTS code.

---

## 5. Frontend architecture (Next.js 16, `apps/web`)

### 5.1 Layers

```
apps/web/
  app/                  routes only: fetch via lib/api, render components, export metadata
  components/ui/        shadcn primitives (Button, Sheet, Accordion, Tabs, Toast)
  components/listing|hub|alerts|layout|seo/   feature components (Server by default)
  lib/api/              typed client generated from FastAPI OpenAPI (openapi-typescript) + fetch wrapper with tags
  lib/seo/              title/description builders, canonical, JSON-LD builders, OG helpers
  lib/domain/           pure functions: days-left (PKT), status, eligibility, slug parsing (unit-tested)
  app/api/              BFF: session cookie (httpOnly, Secure, SameSite=Lax), revalidate webhook
  public/               icons, manifest assets, offline page
```

Dependency direction: `app → components → lib/domain`; only `lib/api` talks to the network. No client state library;
URL params hold filters.

### 5.2 SEO and performance checklist (Next.js specifics)

| Topic | Implementation |
|---|---|
| Rendering | Server Components + ISR (`revalidate` 3600) + on-demand `revalidateTag` from the event consumer |
| Metadata | `generateMetadata` per route; root `metadataBase`, title template `%s | LastBell`; canonical on every page; `robots` noindex for thin hubs, filters, app pages, `needs_review` listings |
| Structured data | JSON-LD via a `<script type="application/ld+json">` component: Organization + WebSite (home), BreadcrumbList (all inner), FAQPage (only when visible), EducationEvent (admissions). No JobPosting at launch |
| Sitemaps | `app/sitemap.ts` with `generateSitemaps` (split by type: listings, hubs, orgs), `lastModified` from `updated_at`; `robots.ts` allows AI crawlers, blocks `/api`, `/alerts`, `/settings`, filter URLs |
| Links | Real `<a href>` via `next/link`; numbered pagination URLs (`?page=2`) with self-canonical |
| Images | Almost none. When used: `next/image` with explicit `width`/`height` and `sizes` (e.g. `sizes="(max-width: 768px) 100vw, 720px"`), descriptive `alt`, lazy by default; never the LCP element. Advert scans are links or lazy thumbnails. SVG icons inline (lucide) |
| Fonts | System stack only; wordmark as inline SVG. No `next/font` download on content pages |
| OG images | `opengraph-image.tsx` per listing/hub (1200×630, `ImageResponse`), absolute dates only |
| Headings | One H1 per page (the job/hub name + year), H2 per section, semantic `<main> <nav> <article> <dl>` |
| Attributes | `lang="en"` on html; `hreflang` not needed (one language); external links get `rel="noopener"`; official portal and advert links stay followed (no `nofollow`), because they are the trustworthy sources we cite |
| Core Web Vitals | JS < 100 KB gz on content pages, LCP < 2.5 s, INP < 200 ms, CLS < 0.1; Lighthouse CI budget in GitHub Actions |
| PWA | `app/manifest.ts` (name, short_name "LastBell", theme `#0F5C85`, icons 192/512/maskable), Serwist SW: network-first HTML (short timeout), cache-first fingerprinted assets, offline page, push + notificationclick handlers |
| Analytics | Umami (self-hosted, free) events from blueprint §9.4; Search Console + Bing Webmaster |

---

## 6. Services: free first, and what will cost money

| Need | Pick | Cost | Note |
|---|---|---|---|
| Server | Contabo VPS | **already bought** | One box runs everything |
| Domain | lastbell.pk (+ lastbell.com.pk) | **≈ Rs 2,100/yr each** (only unavoidable cost) | After the name checks |
| CDN, DNS, TLS, WAF | Cloudflare Free | 0 | Proxy on; origin cert for Caddy |
| Email (alerts + login codes) | **Brevo Free** (300 emails/day, SMTP: works with our current code) → **Amazon SES** when daily volume passes ~250 (≈ $0.10 per 1,000) | 0 → a few $ | One digest per user per day keeps volume low. Set SPF, DKIM, DMARC on the domain from day 1 |
| Push | Web Push (VAPID) | 0 | Already built |
| Errors | Sentry Developer (free) | 0 | Already wired |
| Scraper heartbeat | Healthchecks.io (free, 20 checks) | 0 | Ping after each scrape, dispatch and backup |
| Uptime | UptimeRobot (free, 5-min checks) | 0 | Home, API health |
| Backups | Cloudflare R2 (10 GB free) or Backblaze B2 (10 GB free) | 0 | Daily pg_dump, 30-day retention, monthly restore test |
| Analytics | Umami self-hosted + Search Console + Bing | 0 | |
| OCR/VLM | deAPI (current), capped at 200 calls/day | current spend | Keep the cap; add a monthly budget alert |
| Later (optional) | WhatsApp Business API, Play Store account ($25 once) | — | Only after revenue |

---

## 7. Roadmap (each chunk = one branch → CI green → merge → next branch)

| Chunk | Branch | Contents | Done when |
|---|---|---|---|
| **W0a** | `feature/data-model-v2` | Migration: `organizations` (slug, name, short_name, aliases[], kind, official_url) + `listings.organization_id`; `listings.slug`, `apply_url`, `last_date_at`, `indexable`; `vacancies.gender`, `education_levels[]`; `deadline_changes`; `saved_listings`; `listing_events`; `hub_slugs` registry seeded (cities incl. `hyderabad-sindh`, provinces, regions, fields, topics). Backfill from existing data | migrations + tests green |
| **W0b** | `feature/normalization` | Org normalization (alias + pg_trgm match, unknown → review queue), slug builder, education/gender parsers, deadline-change detection writing `deadline_changes` + `listing_events` in the same transaction | NTS data fully mapped, tests |
| **W0c** | `feature/public-api-v2` | `GET /v1/listings/by-slug/{slug}`, `GET /v1/hubs/{kind}/{slug}` (listings + counts + nearby + last closed), `GET /v1/hubs` (all counts, for nav and sitemap), `GET /v1/orgs/{slug}`, `GET /v1/match-count`, `GET /v1/sitemap/{type}`, `/v1/stats.checked_today`, `POST /v1/reports`; `indexable` filter; Redis cache for counts | OpenAPI updated, tests |
| **W0d** | `feature/saved-and-events` | `PUT/DELETE/GET /v1/me/saved`, reminders for saved listings, "extended" alerts, event consumer task (revalidate webhook + alert queue + cache bust), `GET /v1/me/export` | end-to-end test: deadline change → event → alert + revalidate call |
| W1 | `feature/web-scaffold` | Next.js 16 app, tokens, layout/header/footer/menu, SEO infra, typed client, Dockerfile, compose service, CI (lint, typecheck, build, Lighthouse budget) | `/` renders from API |
| W2 | `feature/web-listing` | Listing page all states, OG image, eligibility checker, redirects | matches boards 04–04e |
| W3 | `feature/web-home-lists` | Home, `/jobs`, closing-soon, new-today | boards 02 |
| W4 | `feature/web-hubs` | City/province hubs, NTS hub + lifecycle shells, empty state, sitemaps | boards 03, 05 |
| W5 | `feature/web-alerts` | BFF cookie session, sign-in sheet, reminder, wizard, inbox, settings, unsubscribe | boards 06, 07 |
| W6 | `feature/web-pwa` | Manifest, Serwist SW, push button, install card, offline page | installable + push works |
| W7 | `feature/deploy` | Prod compose (internal network, no host ports for db/redis, memory limits, no mailpit/flower), `lastbell.pk` block in the existing Caddy, swap file, Cloudflare, Brevo DNS records, backups to R2, Healthchecks/UptimeRobot, trust pages, analytics, Search Console + Bing | live on lastbell.pk **before December** |
| W8 | `feature/ppsc-source` | PPSC scraper (httpx + selectolax), PPSC/FPSC hubs, org hubs (MoD, NADRA, FIA, WAPDA, Pak Army), police hubs, NTS lifecycle scraping | P2 pages live |

---

## 8. Future challenges (and the plan for each)

| Challenge | Plan |
|---|---|
| Source sites change layout or block us | Per-source parser tests on saved fixtures; Healthchecks heartbeat + "0 listings parsed" alert; polite rate limits; raw snapshots allow re-parsing |
| OCR mistakes destroy trust | deAPI fallback + confidence score; `needs_review` = noindex + "official advert se confirm karein"; "Ghalti batayein" button feeding the review queue |
| One VPS = single point of failure | Daily off-site backups + tested restore runbook; Cloudflare keeps serving cached static assets; documented rebuild in < 1 hour |
| Alert bursts (e.g. 2,400 police posts × many users) | Already batched digests + rate-limited delivery queue; Brevo/SES daily caps monitored |
| Email landing in Spam/Promotions | SPF/DKIM/DMARC, one digest/day, List-Unsubscribe, warm-up, plain design |
| iPhone push needs install | Email fallback always on; install steps shown on iOS |
| Google rules (thin pages, JobPosting fee rule) | ≥3-listing threshold, data-only content, no JobPosting at launch |
| Seasonality spikes (Dec, Jan, Feb, Aug) | ISR + Cloudflare; load test before December |
| Disk growth (attachments, snapshots) | Retention policy already for run logs; move attachments to R2 when > 20 GB |
| deAPI cost/availability | Daily cap, cache by image hash, Tesseract fallback, budget alert |

---

## 9. Decisions

Answered on 2026-10-10:

- **Brand:** LastBell is final. Code, emails and docs rename from "SarkariAlert" (branch `chore/rename-lastbell`).
- **Domain:** not bought yet. Config uses `lastbell.pk`; buy it before W7.
- **Server:** shared Contabo VPS, see §4.0.
- **Order:** backend W0 first, then frontend (the default; pages need slugs and hubs).

Still open:

1. **About page:** confirm the founder name shown, and whether to keep the PPSC applicants stat (with its source link).
2. **Email:** OK to start with Brevo Free (300/day) and move to SES later?
3. **Deploy (W7):** OK to add a `lastbell.pk` block to the existing linkduk Caddy, add a 4 GB swap file, and reboot for
   the pending updates?
