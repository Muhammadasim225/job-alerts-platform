# Frontend plan: SarkariAlert website (apps/web)

Status: plan, 2026-10-05. Based on:

- a teardown of 11 Pakistani sites (jobz.pk, pakistanjobsbank, ilmkidunya, rozee, mustakbil, NJP, Punjab Jobs, NTS, PPSC,
  FPSC, UrduPoint) and of freejobalert, sarkariresult, LinkedIn Jobs, Wellfound and eduvision;
- Google's own documentation (JobPosting, Indexing API, Core Web Vitals, interstitials, JavaScript SEO, spam policies,
  favicons) and the Next.js 16 docs;
- Google autocomplete for Pakistan (`gl=pk`), used as a demand signal;
- our real data: 22 NTS listings, of which 12 are open (jobs, admissions, tests).

## 1. Where we can win

| Competitors do | We do |
|---|---|
| Show the advert as a scanned image only. Posts, BPS and age are not text (jobz, PJB, paperpk) | Every post is text: BPS, seats, qualification, age, experience, fee, test syllabus |
| "Expected last date… or as per paper ad", with no countdown | An exact last date, "3 days left", a deadline reminder, and "deadline extended" |
| 11–50 ad slots, popups, 400–560 KB pages, 6–17 s loads (ilmkidunya) | No ads at launch, text-first pages, under 100 KB of JavaScript, LCP under 2.5 s on mobile |
| Broken SEO: generic titles (NJP, PPSC, Punjab), session IDs in URLs, "2026 2026", "Published 2014", non-ISO schema dates | One title formula, the year generated from data, valid JSON-LD, canonicals everywhere |
| Alerts by WhatsApp channel (broadcast only) or OneSignal push to everyone | **Personal** alerts: your BPS, field, province and age, by email digest, push and inbox |
| Official sites have the data but no SEO (NJP, FPSC, NTS) | The same data, made findable |

## 2. Keywords (what people type, Google autocomplete, Pakistan)

| Intent | Real queries | Our page |
|---|---|---|
| Testing body | nts jobs 2026, nts jobs advertisement 2026, nts jobs apply online, nts jobs sindh | `/jobs/test/nts` |
| Province / city | govt jobs in punjab, govt jobs in karachi, govt jobs lahore 2026, govt jobs islamabad | `/jobs/in/{province}`, `/jobs/city/{city}` |
| Grade | bps 16 jobs, bps 16 jobs in sindh / punjab / kpk, bs 16 jobs in pakistan | `/jobs/bps/{n}` (+ province later) |
| Qualification | jobs for matric pass, jobs for matric pass students in lahore | `/jobs/qualification/{matric\|intermediate\|bachelor\|master}` (backend gap, see §9) |
| Post | computer operator jobs islamabad / lahore / rawalpindi | Post pages (phase 2), field hubs |
| Organization | (org name) jobs 2026 | `/jobs/org/{org}` |
| Test lifecycle | nts test date 2026, nts result check by roll number, nts gat schedule 2026 | Later: test dates and results (needs scraping) |
| Admissions | admission 2026 last date, university admissions open in islamabad | `/admissions`, `/admissions/level/{level}` |
| Commissions | ppsc jobs 2026, fpsc jobs advertisement 2026 | **Only when those sources are scraped.** No empty pages |

## 3. SEO rules (hard requirements)

1. **Server-rendered content.** Title, H1, facts, posts table and links are all in the first HTML (Server Components,
   ISR). Links are real `<a href>`. Google: "Google can only discover your links if they are `<a>` HTML elements with an
   `href` attribute." No hash routes, and no infinite scroll without paginated URLs.
2. **Metadata per page**, using the Next 16 `generateMetadata` API:
   - unique `title` (root template `%s | SarkariAlert`)
   - `description`, `alternates.canonical`, `openGraph`, `twitter`, `robots`
   - `metadataBase` set in the root layout. Without it, relative canonicals fail the build.
3. **Title formulas.** The year always comes from the data, never typed:
   - Listing: `{Org short} Jobs {Month YYYY}: {N} Posts, Last Date {DD Mon}` (e.g. "NICVD Jobs Oct 2026: 15 Posts, Last
     Date 11 Oct")
   - Hub: `Govt Jobs in Sindh {YYYY}: {N} Open Posts` / `NTS Jobs {YYYY}: Latest Advertisements, Last Dates`
   - Admission: `{Institution} Admission {Session}: Programs, Eligibility, Last Date`
4. **Description formula:** `{Org} has announced {N} posts ({top 3 posts}) in {city}. Last date {date}. BPS {range}.
   Check eligibility, age limit, fee and how to apply.` Keep it under ~155 characters.
5. **JSON-LD**, rendered as a native `<script type="application/ld+json">` with `<` escaped (Next docs pattern):
   - `BreadcrumbList` on every inner page; `WebSite` + `Organization` on home;
   - `FAQPage` only where a FAQ is visible on the page;
   - `EducationEvent` on admission pages;
   - `JobPosting` **only on single-post pages** (phase 2), never on listing/hub pages. Google: "Don't add structured
     data to pages intended to present a list of jobs."
     - `title` is the post name only. Google: "Don't include job codes, addresses, dates, salaries, or company names."
     - `hiringOrganization` is the real employer, never us.
     - `validThrough` is an ISO datetime with `+05:00`. `datePosted` is set. No `baseSalary` (BPS is not an amount).
     - **Open risk:** Google says "We don't allow job postings that require payment from applicants", and most NTS
       posts have a test fee. Google has made no ruling on government test fees. Plan: leave JobPosting out at launch,
       then try it on a few posts and watch Search Console. The pages rank as normal results either way.
6. **Expired listings:** keep the page as a "Closed" archive (it still gets "result" and "test date" searches), never
   with JobPosting markup, and link it to newer adverts from the same organization.
7. **Programmatic pages, without scaled-content abuse.** Google lists "pages generated… where little value is provided"
   and doorway pages as spam. So:
   - a hub is indexable only with **at least 3 live listings**, otherwise it is `noindex, follow` and stays out of the
     sitemap;
   - every hub has real, usable content on the page: a live list, counts, closing-soon items and a short factual intro
     generated from data. No spun text and no keyword blocks;
   - never generate combinations with zero results (e.g. city × BPS × qualification) as URLs.
8. **Sitemaps:** `sitemap.ts` with real `lastModified` (from `listings.updated_at`), and `generateSitemaps` past
   ~45k URLs.
   - `robots.ts` blocks `/settings`, `/alerts`, `/sign-in`, `/api`, and filter query URLs.
   - Filter URLs (`?province=..&bps=..`) set their canonical to the clean hub URL.
9. **Indexing API** (officially only for JobPosting pages; default quota 200/day): use it in phase 2, for new post
   pages only.
10. **Fresh signals:** a visible "Last checked {date}" from `scraped_at`, a "Deadline extended" banner, and on-demand
    ISR revalidation when the daily scrape stores a change (§8).

## 4. Pages and URLs

| Route | Purpose | Indexed | Data |
|---|---|---|---|
| `/` | Home: search, alert CTA, closing soon, new today, browse by province / test body / field / BPS, admissions | yes | `/v1/stats`, `/v1/listings` |
| `/jobs` | All open government jobs (paginated `?page=`) | yes | `/v1/listings?kind=job` |
| `/jobs/{slug}-{id}` | **Listing page** (one advert): see §5 | yes (archive when closed) | `/v1/listings/{id}` |
| `/jobs/{slug}-{id}/{post-slug}` | Single post page, with JobPosting (phase 2) | yes, if complete | vacancy |
| `/jobs/test/{nts}` | Jobs by testing body | ≥3 live | filter |
| `/jobs/in/{province}`, `/jobs/city/{city}` | Location hubs | ≥3 live | filter |
| `/jobs/bps/{n}` | Grade hubs (BPS 1–22) | ≥3 live | `/v1/vacancies` |
| `/jobs/field/{it\|health\|engineering…}` | Field hubs | ≥3 live | filter |
| `/jobs/org/{org}` | Organization hubs | ≥3 live or archive | needs org slug (§9) |
| `/jobs/qualification/{matric…}` | Qualification hubs | ≥3 live | needs education level (§9) |
| `/closing-soon`, `/new-today` | Freshness pages; strong for return visits | yes | sort and filter |
| `/admissions`, `/admissions/{slug}-{id}`, `/admissions/level/{BS\|MPhil\|PhD…}` | Admissions | yes / ≥3 | `kind=admission` |
| `/tests`, `/tests/{slug}-{id}` | GAT, NAT and other test notices | yes | `kind=test` |
| `/listings/{id}` | **301 redirect** to the canonical slug URL. Links already in sent emails use it | no | |
| `/alerts/new` | Alert wizard (§6) | no | `/v1/me/preferences` |
| `/alerts` | Inbox. Email links already point here | no | `/v1/me/alerts` |
| `/settings`, `/sign-in`, `/unsubscribe?token=` | Account. `/unsubscribe` POSTs to the API on a button click, so link scanners can't unsubscribe anyone | no | `/v1/me`, `/v1/email/unsubscribe` |
| `/about`, `/how-it-works`, `/privacy`, `/terms`, `/contact` | Trust pages. The disclaimer is in the footer on every page | yes | static |
| `/report-error?listing={id}` | Report a mistake in a listing | no | needs endpoint (§9) |
| Later: `/tools/age-calculator` | Competitors earn traffic with tools (age calculator with relaxation, photo resizer) | yes | client |

Slug example: `/jobs/nicvd-karachi-jobs-oct-2026-9`. The id at the end keeps the URL stable when the title is
corrected. Any other slug for the same id 301-redirects to the canonical one.

## 5. Listing page (job), section order

From freejobalert, sarkariresult and NJP, without their clutter:

1. Breadcrumbs (Home › Jobs › Sindh › NICVD)
2. **Header:** org, H1 title, status chip (Open / Closing soon / Extended / Closed), "N days left", and a "Last checked"
   source badge
3. **Key facts strip:** last date · posts · seats · BPS range · test body · city. One line per fact, separated by
   middle dots.
4. Inline **Alert CTA**: "Get an alert for jobs like this", prefilled from this listing's field, BPS and province
5. **Posts table** (Post | BPS | Seats | Qualification | Age | Experience). Below 768px each row becomes a card, with
   details in an accordion.
6. Important dates (announced, last date, tentative test date), then fee, then how to apply (numbered steps)
7. **Important links table:** Apply on official portal, Official advertisement (PDF/image), Test syllabus, Official
   website
8. Test syllabus (from the "Content Weightages" DOCX) for each post, where we have it
9. Second Alert CTA and **WhatsApp share** (prewritten: title, last date, link with `utm_source=whatsapp`)
10. FAQ, built from data only (e.g. "What is the last date?", "What is the age limit for Computer Operator?")
11. Related: same organization, same city, same field (real links)
12. Footer disclaimer: "Independent portal, not affiliated with any government body. Always confirm on the official
    advertisement."

The admission variant swaps the posts table for a programs table (Program | Level | Duration | Eligibility) and adds
entry test details and session.

**OCR text:** qualification text read by OCR can contain errors ("instinste tecognized the Boord"). Until the cleanup
in §9 exists:

- show the official advert link next to the posts table;
- add `noindex` to listings with `needs_review` until a human verifies them (the back office already has the review
  queue and verify endpoint).

## 6. Onboarding and alerts (marketing flow)

- **No splash screen and no popups.** A web splash delays first paint, which hurts LCP on mobile data. Google:
  interstitials that obscure the page "may lead to poor search performance". The installed PWA gets the OS launch screen
  from the manifest, which is enough.
- **Entry points:** the alert CTA is in context on every listing page (top, middle and bottom) and on every hub ("Alert
  me for BPS 16 jobs in Sindh"). A sticky bottom bar on mobile scrolls away with the page and has no overlay.
- **Wizard** at `/alerts/new`, prefilled from the page the user came from:
  1. What: jobs / admissions / tests; fields; BPS range; province; keywords (chips, not dropdowns)
  2. You (optional): age, years of experience, education. These filter out posts the user is not eligible for.
  3. Where: email. Enter the address, then type the 6-digit code; this is our existing passwordless sign-in, with no
     password and no CNIC or phone. After saving, an **Enable browser notifications** button. Permission is asked only
     on that click (Chrome data: ~12% allow on page load vs ~30% after an interaction). On iOS show "Add to Home Screen
     first" (Web Push works on iOS 16.4+ only from the installed app).
- **Success screen:** "You'll get alerts like these", showing the first 3 matches from `/v1/me/matches`. The value is
  visible at once.
- **Install banner:** a small dismissible card from the 2nd visit or after saving an alert. Never full-screen.

## 7. Design system

- **Colors** (CSS variables; check WCAG AA, at least 4.5:1, before final):

| Token | Value | Use |
|---|---|---|
| `--brand` | `#0F5C85` (deep teal-blue) | Buttons, links, header. Not government green, so we never look like an official body |
| `--bg` / `--surface` | `#F8FAFC` / `#FFFFFF` | Page / cards |
| `--text` / `--muted` | `#0F172A` / `#475569` | Body / meta |
| `--urgent` | text `#B91C1C` on `#FEE2E2` | ≤3 days left |
| `--soon` | text `#92400E` on `#FEF3C7` | ≤7 days |
| `--open` | text `#166534` on `#DCFCE7` | Open |
| `--info` | text `#1E40AF` on `#DBEAFE` | Extended / result out / new |
| `--closed` | text `#475569` on `#F1F5F9` | Closed |

  A status is always shown as text plus color, never color alone. Dark mode comes later, using the same tokens.

- **Typography:** the system font stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`), which is Roboto on
  Android, our main audience. It needs no font download, so there is no font flash and nothing added to LCP. The
  Indian market leaders do the same.
  - Sizes: 16px body (smaller inputs make iOS zoom), 14px meta and table text, headings 20 / 24 / 30px, line-height 1.5.
  - `tabular-nums` for dates and counts.
  - Urdu (Noto Nastaliq) is a later phase, loaded only on Urdu pages.
- **Layout:** mobile-first at 360px, content max 1120px, an 8px spacing scale, touch targets ≥44px. Cards use one fact
  per line with middle dots (Wellfound style). Desktop has a two-column listing page, with facts and CTA in a sticky
  aside.
- **Icons:** lucide-react, tree-shaken inline SVG.
- **Images:** almost none.
  - The LCP element is the H1 text, never an image.
  - Advert scans are linked, or shown as a lazy thumbnail with fixed `width`/`height` (no CLS) and descriptive `alt`
    ("Official NTS advertisement for NICVD Karachi jobs, October 2026").
  - Next 16 deprecated `priority`; use `fetchPriority="high"` only if an image is ever the LCP.
- **Share images:** a per-listing `opengraph-image.tsx` (1200×630, `ImageResponse`) showing org, "15 posts", "Last date
  11 Oct" and the brand. This is what shows when a link is shared on WhatsApp, our main sharing channel.
- **Favicons:**
  - `app/favicon.ico` (multi-size), `app/icon.png` (512) and `app/apple-icon.png` (180).
  - Google wants square images larger than 48×48 and does not list SVG as a format, so ship PNG/ICO.
  - The manifest has 192 and 512 icons, plus a separate maskable 512.

## 8. Technical architecture

- **Stack:**
  - Next.js 16 (App Router, Turbopack), TypeScript, Tailwind v4
  - shadcn/ui primitives (Button, Input, Sheet, Dialog, Accordion, Tabs, Toast)
  - react-hook-form + zod for forms
  - Serwist for the service worker
- **Data:** Server Components call the FastAPI API over the internal network.
  - Pages are ISR with `revalidate` of 1 h.
  - On-demand revalidation: after the daily scrape stores or changes a listing, the backend calls a secret
    `POST /api/revalidate` on the web app, which runs `revalidateTag` / `updateTag` for that listing and its hubs.
    Pages are therefore never stale by more than minutes.
  - "Days left" and "closed" are computed at render time and on the client, so they never go stale between revalidations.
- **Auth:** the session token from `/v1/auth/verify` is stored in an **httpOnly, Secure, SameSite=Lax cookie** by a Next
  route handler (a BFF), never in localStorage, so a script injection cannot steal it. Account pages call `/v1/me`
  through the Next server.
- **Service worker:** network-first for HTML and data, with a short timeout. A deadline must never come from an old
  cache. Static assets are cached long (they are fingerprinted). There is an offline page, and push and
  notification-click handlers (payload format is in `apps/notifier/README.md`).
- **Next 16 notes:**
  - `params` and `searchParams` are async.
  - `middleware.ts` is now `proxy.ts`.
  - `viewport` / `themeColor` go in `generateViewport`.
  - `next lint` is removed; we use ruff-style CI with ESLint/Biome run directly.
- **Budgets:**
  - JavaScript under 100 KB gzipped on content pages.
  - Mobile p75 targets: LCP < 2.5 s, INP < 200 ms, CLS < 0.1 (Google thresholds).
  - Lighthouse SEO and Accessibility ≥ 95.
  - Every content page works with JavaScript disabled.
- **Analytics:** privacy-friendly events (Umami self-hosted, or GA4), all with `utm_*`:
  - `view_listing`, `click_official_apply`, `start_alert`, `complete_alert`, `enable_push`, `share_whatsapp`,
    `install_pwa`

```
apps/web/
├── app/
│   ├── layout.tsx            metadataBase, title template, header/footer, disclaimer
│   ├── page.tsx              home
│   ├── jobs/ [listing]/ [listing]/[post]/ test/[body]/ in/[province]/ city/[city]/ bps/[n]/ field/[f]/ org/[org]/
│   ├── admissions/ tests/ closing-soon/ new-today/ listings/[id]/ (redirect)
│   ├── alerts/ alerts/new/ settings/ sign-in/ unsubscribe/
│   ├── about/ how-it-works/ privacy/ terms/ contact/ report-error/
│   ├── api/ (session BFF, revalidate)
│   ├── sitemap.ts robots.ts manifest.ts favicon.ico icon.png apple-icon.png opengraph-image.tsx
├── components/ ui/ (shadcn) · listing/ (ListingCard, FactsStrip, PostsTable, StatusChip, DaysLeft, SourceBadge,
│               ImportantLinks, Breadcrumbs, Pagination) · alerts/ (AlertCTA, AlertWizard, PushButton, InstallBanner)
│               · share/ (WhatsAppShare) · seo/ (JsonLd)
├── lib/ api.ts (typed client) · seo.ts (titles, descriptions, canonicals) · jsonld.ts · dates.ts (PKT, days left) · slug.ts
└── public/ icons, offline page
```

## 9. Backend work needed first (small, in this order)

1. **Slugs:** a stable `slug` per listing (org + city + month-year) and per post, returned by the API.
2. **Organization normalization:** an `org_slug` and short name (NICVD, ISMO, WCLA) for `/jobs/org/` and titles.
3. **Education level** per post (matric / intermediate / bachelor / master / diploma), parsed from qualification. This
   enables the "jobs for matric pass" pages, which are high-demand queries.
4. **Hub counts endpoint:** live counts per province, city, BPS, field, org and level in one call. This drives the
   index/noindex threshold and the sitemap.
5. **Revalidation webhook** from the scraper to the web app after each stored change.
6. **Report-error endpoint** (rate-limited), which feeds the review queue.
7. **OCR quality gate:** keep `needs_review` listings out of the index until verified, and clean common OCR noise in
   qualification text.
8. **Deadline as a datetime** in PKT (`+05:00`), plus deadline history for "extended" banners.

## 10. Build order (chunks; each is merged after CI is green)

| Chunk | Contents |
|---|---|
| W0 | Backend prerequisites 1–5 from §9 |
| W1 | Next.js scaffold, design tokens, layout, header/footer, SEO infrastructure (metadata helpers, JsonLd, sitemap, robots, icons, manifest), CI job |
| W2 | Listing page (job / admission / test), `/listings/{id}` redirect, OG image |
| W3 | Home, `/jobs`, `/admissions`, `/tests`, closing-soon, new-today, pagination |
| W4 | Programmatic hubs with thresholds, plus sitemaps |
| W5 | Sign-in (BFF cookie), alert wizard, inbox, settings, unsubscribe page |
| W6 | PWA: service worker, push button, install banner, offline page |
| W7 | Trust pages, report-error, analytics events, Lighthouse/CWV pass, Search Console and Rich Results Test |

## 11. Decisions for the owner

- **Brand name and domain** (e.g. sarkarialert.pk). This is needed for `metadataBase`, emails and the OG image.
- **Brand color:** `#0F5C85` teal-blue (recommended) or another.
- **Font:** the system stack (recommended for speed) or Inter (one self-hosted variable file, more brand feel).
- **JobPosting / Google for Jobs:** start without it because of the fee rule, and test it later (recommended).
