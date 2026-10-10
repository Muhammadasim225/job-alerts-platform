# Frontend blueprint: pages, content, UI and growth (apps/web)

Status: blueprint, 2026-10-10. It builds on [frontend-plan.md](frontend-plan.md) (SEO rules, tech stack, budgets) and
replaces it where the two disagree: the URL map (§4), page priorities (§4) and build order (§12). Everything here is
backed by research saved in this repo:

| Evidence | File |
|---|---|
| 57 measured keywords (volume, CPC, SD) | [seo/keywords-2026-10.csv](seo/keywords-2026-10.csv) |
| 105 competitor keywords (jobz.pk, paperpk.com, ilmkidunya.com) | [seo/competitor-*.csv](seo/) |
| 50-keyword bulk check (orgs, police, lifecycle, cities, female, AIOU) | [seo/bulk-keywords-2026-10.csv](seo/bulk-keywords-2026-10.csv) |
| Google Trends PK: 16 terms, 5-year seasonality, related queries | [seo/google-trends-pk-2026-10.json](seo/google-trends-pk-2026-10.json) |
| Full analysis workbook (15 sheets) | `E:\Personal Product\Govt-Jobs-SEO-Keyword-Research-2026-10.xlsx` (outside the repo) |
| Live teardown of 6 competitor sites on 2026-10-10 | §2 of this document |

The brand is not final. This document writes **{Brand}**; LastBell is the conditional pick (§3.4).

---

## 1. Who we build for

### 1.1 One audience

**Pakistani government-job seekers, 18–30, Matric to Masters, mostly outside the big cities, on an Android phone with
mobile data.** Everything else (private jobs, board results, prayer times, study material) is out of scope, even where
the volume is big (BISE results ~1M/month, prayer times ~450K: both measured on ilmkidunya, both off-audience).

| Trait | What it means for the UI |
|---|---|
| Android, 360–412 px screens, mid-range phones, prepaid mobile data | Mobile-first, text-first, tiny pages; no image carousels; no web fonts on the critical path |
| Reads English job vocabulary (BPS, NTS, last date, apply online) but thinks and talks in Urdu/Roman Urdu | Headings and data in English (that is what Google and the advert use); one-line value messages and buttons in plain Roman Urdu |
| Applies through NTS / PPSC / FPSC / police / army portals; pays a test fee | Every page answers: "Can I apply? By when? Where is the official link?" |
| Afraid of fake adverts and fee scams | The official source is on every listing; we never ask for CNIC, phone, or money |
| Lives on WhatsApp; searches by **organization**, **city** and **commission**, with "2026" and "online apply" | Hubs are named exactly like those searches; sharing to WhatsApp is one tap |
| Women search by **city** ("female jobs in lahore" 5.4K) rather than nationally ("govt jobs for female in pakistan" 210) | A "Female eligible" block inside each city hub, not a separate national page |

### 1.2 The jobs the visitor came to do (in order of frequency)

1. **"What new jobs are there for me?"** (city, commission, organization): hubs and home.
2. **"What is the last date and how do I apply online?"**: listing page.
3. **"Is my roll number slip / result out?"**: lifecycle pages (NTS roll slip 1.3K, NTS result 1K, PPSC result 880,
   PPSC roll slip 880).
4. **"Don't let me miss the next one"**: the alert, which is our product and the reason to come back.

Nobody searches for the alert itself ("job alert" is near zero in Trends, "govt jobs whatsapp group" 70/month). Traffic
arrives through jobs 1–3, and **every page has to sell job 4**.

---

## 2. Market teardown (live fetch, mobile user agent, 2026-10-10)

### 2.1 What the competitors actually ship

| Site | Page | Size | Ad slots | Title / H1 | Last date | Schema | Look |
|---|---|---|---|---|---|---|---|
| jobz.pk | home | 199 KB, 1,008 links | AdSense + OneSignal push popup | **No H1**; title "Jobs in Pakistan 2026 Jobs.pk Jobz.pk" | n/a | none | Green `#87B843` / `#618F2C`, Arial, grey borders |
| jobz.pk | job advert | 135 KB, 24 images | **16 AdSense slots** | Title "…KPK Jobs 2026 **2026** Job Advertisement" (duplicate year) | "**Expected** Last Date: 24 October, 2026 **or as per paper ad**" | none | Posts only inside the scanned advert image; 0 tables; reader comments |
| jobz.pk | Karachi hub | 184 KB | 8 slots | H1 "Jobs in Karachi" | n/a | none | Govt + private mixed |
| ilmkidunya.com | /jobs | 410 KB, 49 images | AdSense + modal | H1 = title | n/a | none, no canonical | Teal `#15A18D`, Open Sans, Bootstrap 3 |
| ilmkidunya.com | job | 389 KB | 2 slots | **H1 "Latest Jobs in Public Sector Organization 2026"** (not the job) | in body text | JobPosting | Same |
| pakistanjobsbank.com | job | 48 KB | 4 slots | Title = 120-char keyword chain "…Apply Online Medical Officers, Technicians & Others SKMCH Latest" | from newspaper date | none | Grey + gold `#FFD700`, no web font |
| rozee.pk | home / job | 96 / 83 KB | Google Ad Manager | **H1 "Agay Barho!"** (Roman Urdu hero) | n/a | Organization, WebSite, JobPosting | Bootstrap blue `#007BFF`, Source Sans Pro / Google Sans |
| njp.gov.pk (official) | home / job | 712 KB, **285 images** / 36 KB | none | Title "National Job Portal" on **every page**, no meta description | in body | none | Govt green `#5D7E56` + navy `#182336`, Manrope |
| paperpk.com | any | n/a | n/a | Served a bot challenge ("One moment, please…") to our fetch | | | |

### 2.2 What users are used to (keep it, so the site feels familiar)

- **Navigation vocabulary.** jobz.pk's menu is the market's mental model: Government · FPSC · PPSC · SPSC · KPPSC · BPSC ·
  AJKPSC · Join Pak Army · Join Pak Navy · Join PAF · Police · Rangers · FC · ASF · ANF · IB · Motorway Police · NTS · PTS
  · ETEA. Our hub names use the same words.
- **"Online Apply" and "Last Date" in titles.** pakistanjobsbank puts "Apply Online" in every title. Trends agrees:
  "nts jobs apply online" is the #1 NTS query, "ppsc jobs apply" scores 48 and "pak army online apply" 58.
- **Year in the title** ("2026"). Trends marks "govt jobs 2026" and "latest govt jobs 2026" as Breakout.
- **Dense lists.** Users scan long lists of org names and dates; a sparse "marketing" homepage would look empty to them.
- **Roman Urdu hero lines are normal** (rozee: "Agay Barho!").

### 2.3 Where every competitor is weak (our openings)

| Weakness, measured | Our answer | Principle |
|---|---|---|
| Posts, BPS, age and fee live only inside a scanned image (jobz: 0 tables) | Every post is text in a table: BPS, seats, qualification, age, fee | Value |
| "Expected last date… or as per paper ad" | Exact last date, "3 din baqi", reminder, "Deadline extended" banner | Believability |
| 8–16 ad slots per page, push popups, 135–410 KB, 285 images (NJP) | No ads at launch, no popups, under 100 KB JS, H1 text as LCP | Trust |
| Broken titles: no H1, "2026 2026", generic H1, one title for the whole site (NJP) | One title formula with the year from data (§6.2) | SEO |
| Govt and private jobs mixed in one list | Government only | One audience |
| Alerts = a OneSignal broadcast to everyone | Personal alert: city + education + field + age, then a reminder 2 days before the last date | Offer |
| Nothing after you apply | Roll slip, test date and result follow-ups on the same listing | Bundle |
| Green everywhere (jobz, NJP, ilmkidunya teal) | Deep blue + amber "bell" accent: stands out, and never looks like a government site | Trust |

### 2.4 How we pull users away from them (the "genius" part, kept honest)

1. **Be the page that answers in one screen.** A competitor shows a scan and 16 ads; we show "Last date 24 Oct · 3 din
   baqi · 12 posts · BPS 7–16 · Apply online →" above the fold. Users bookmark the faster answer.
2. **Own the return trip.** A competitor gets one visit per advert. We get every next visit, because the alert and the
   deadline reminder bring the user back to us, not to Google.
3. **Follow the candidate through the lifecycle.** Advert → roll number slip → test date → result, on one listing and in
   one alert. No competitor connects them.
4. **Eligibility in seconds.** "Aap is post ke liye eligible hain?" (age and education) turns a list into an answer.
5. **WhatsApp-native sharing.** A prewritten message with the last date and our link, plus a clean OG image. Each share
   is a free ad in a group of 200 job seekers.
6. **Be first on spikes.** FIA (one drive took Trends to 100) and ASF are event-driven. Org hubs exist and rank before the
   drive; the alert catches everyone who arrives during it.

---

## 3. Positioning and the 10-second offer

### 3.1 Promise (one sentence)

> **Sarkari job ki last date ab kabhi miss nahi hogi.**

### 3.2 The 10-second test

A first-time visitor from Google must understand three things before scrolling:

| Second | They see | Element |
|---|---|---|
| 0–3 | "This is the job I searched for, and it is current" | H1 with the org/city name + year, status chip, last date |
| 3–7 | "This site saves me effort" | Facts strip: last date · days left · posts · BPS · apply link |
| 7–10 | "It will remind me for free, without risk" | One alert CTA with the trust line "Free · Koi CNIC nahi · Koi fee nahi" |

On the home page the order is promise → proof → action (§5.1).

### 3.3 The bundle (what "free alert" really contains)

1. **New-job alert** for your city, education and field (email digest + browser push + inbox).
2. **Last-date reminder** 2 days before the deadline, for jobs you saved.
3. **Eligibility filter**: only posts you can apply for by age and education.
4. **Test follow-ups**: roll number slip, test date and result for jobs you saved.
5. **Official link check**: every listing links to the official advert and portal, with "last checked" time.

Shown as 5 ticks on the alert landing and in the wizard's success screen. Later premium bundles (WhatsApp delivery,
syllabus packs) build on the same list.

### 3.4 Brand notes

- Never use "sarkari naukri" in copy: it scores **0** in Pakistan on Trends and reads Indian.
- "Sarkari job" (mixed) is fine in Roman Urdu body copy; titles use "Govt Jobs", which people actually type.
- LastBell (conditional): an old school hand-bell icon, i.e. "the bell before the last period". It fits the deadline
  promise. Final name, handles and domain are the owner's decision (§14).

---

## 4. Information architecture and URL map (final)

### 4.1 Rules

- Short URLs that match the words people type. Competitors use `jobs_in_karachi`; we use `/jobs/karachi`.
- One **slug registry** in the backend (`hub_slugs`: slug, type, label) keeps city, province, field and topic slugs
  unique inside `/jobs/…`. A listing slug always ends in `-{id}`, and hub slugs never do, so `/jobs/[slug]` can tell
  them apart.
- A hub is indexable only with **≥3 live listings**; otherwise `noindex, follow` and out of the sitemap (unchanged
  from frontend-plan §3.7).
- No year in URLs. The year goes in titles only, generated from data.
- Filters (BPS, qualification, age) are query parameters with a canonical to the clean hub. BPS pages are not indexed
  (total demand ~100/month).

### 4.2 Page inventory with evidence

Priority: **P1** = launch, **P2** = first month after launch, **P3** = when data exists, **P4/P5** = auto-generated only
when the ≥3 rule passes. Volumes are monthly (keyword tool, Pakistan, Oct 2026).

| Pri | URL | Template | Evidence |
|---|---|---|---|
| P1 | `/` | Home | Brand + "govt jobs" head term (Trends ~0.8× PPSC; SD 38+, so a long-term target) |
| P1 | `/jobs` | All jobs | "latest govt jobs today" 390, "govt jobs 2026" Breakout |
| P1 | `/jobs/{slug}-{id}` | Listing | Every advert, archive when closed |
| P1 | `/jobs/karachi` `/lahore` `/islamabad` `/rawalpindi` `/multan` `/faisalabad` `/peshawar` `/quetta` `/hyderabad-sindh` | City hub | Karachi 9.9K SD 8, Lahore 6.6K, Islamabad 4.4K, Multan 1.6K, Rawalpindi 1.6K… |
| P1 | `/jobs/punjab` `/sindh` `/kpk` `/balochistan` | Province hub | Punjab 12.1K, KPK 2.9K, Sindh 2.4K |
| P1 | `/nts` + `/nts/roll-number-slip` `/nts/result` `/nts/test-date` | Commission hub + lifecycle | NTS 18.1K; roll slip 6.6K (SD 6) / "download" 1.3K; result 1K |
| P1 | `/closing-soon`, `/new-today` | Freshness | Return visits (low search, high retention) |
| P2 | `/ppsc` + `/ppsc/result` `/ppsc/roll-number-slip` | Commission hub + lifecycle | PPSC ~110K family (SD 11–17); result 880 (SD 11); slip 880 |
| P2 | `/fpsc` | Commission hub | FPSC ~40K (SD 13); Trends 0.52× PPSC |
| P2 | `/org/ministry-of-defence` `/org/nadra` `/org/fia` `/org/wapda` `/org/pak-army` | Org hub | MoD 12.1K, NADRA 8.1K, FIA 6.6K (one spike = 100), WAPDA 6.6K SD 13, "join pak army" ≈1.1× PPSC |
| P2 | `/jobs/police` + `/jobs/police/punjab` | Field hub | Punjab Police 9.9K (SD 18), Breakout |
| P3 | `/org/asf` `/org/paf` `/org/pakistan-railways` `/org/pak-navy` `/org/fbr` | Org hub | ASF 4.4K, PAF 2.9K, Railways 1.9K, Navy 1.3K |
| P3 | `/jobs/police/sindh`, `/jobs/ajk`, `/jobs/health` | Hubs | Sindh Police 2.9K SD 10; AJK 390; health CPC Rs 2,114 |
| P3 | `/spsc`, `/kppsc`, `/fpsc/result` | Commission | SPSC 390, KPPSC 260; FPSC result peaks Aug–Sep |
| P3 | `/admissions`, `/admissions/aiou`, `/admissions/nursing`, `/admissions/{slug}-{id}` | Admissions | AIOU admission 12.1K (peaks Feb, Oct); BSN 880 |
| P4 | `/jobs/gujranwala` `/sialkot` `/sargodha` `/bahawalpur` `/abbottabad` `/gilgit-baltistan`, `/org/ib` `/org/etea` `/org/ots`, `/jobs/computer-operator`, `/jobs/teaching`, `/jobs/female` | Auto hubs | 170–390 each |
| — | `/alerts/new`, `/alerts`, `/settings`, `/sign-in`, `/unsubscribe` | App | noindex |
| — | `/about`, `/how-it-works`, `/privacy`, `/terms`, `/contact`, `/report-error` | Trust | indexed except report-error |
| Never | BISE results, prayer times, study material, private jobs, newspaper-name pages, STS/PTS/BTS hubs | | Off-audience or ~0 demand |

### 4.3 Navigation

**Mobile header (56 px):** logo · search icon · "Alert" button (filled). The menu opens as a sheet with 4 groups, using
the market's own words:

```
Shehar        Karachi · Lahore · Islamabad · Rawalpindi · Multan · Peshawar · Quetta · Sab shehar →
Commission    NTS · PPSC · FPSC · SPSC · KPPSC
Idare         Pak Army · Police · FIA · NADRA · WAPDA · ASF · MoD · Sab idare →
Admissions    AIOU · Nursing / BSN · Sab admissions →
```

**Desktop header:** logo · Jobs · Commissions ▾ · Idare ▾ · Admissions · Closing soon · [search] · **Free alert lagayein**.

**Footer:** the same 4 link groups (the internal-linking mesh for SEO), trust links, and the disclaimer on every page:
"{Brand} ek independent website hai, kisi sarkari idare se taaluq nahi. Hamesha official advert se confirm karein."

---

## 5. Page templates

Wireframes are at 360 px. `[ ]` = button, `( )` = chip. Everything above the `── fold ──` line must fit on a
360×640 screen.

### 5.1 Home `/`

**Job:** prove freshness, route the visitor to their city or commission, sell the alert.

```
┌────────────────────────────────────┐
│ 🔔 {Brand}          🔍   [Alert]    │
├────────────────────────────────────┤
│ Sarkari job ki last date ab        │  H1 (promise)
│ kabhi miss nahi hogi.              │
│ Apna shehar aur taleem chunein —   │  sub-line (offer)
│ nayi job aate hi free alert, aur   │
│ last date se 2 din pehle reminder. │
│ [ Free alert lagayein ]            │  primary CTA
│ ✓ Aaj 214 jobs check ki gayin       │  proof row (DB numbers)
│ ✓ Official advert link   ✓ Koi fee │
│   nahi, koi CNIC nahi               │
│ (Karachi)(Lahore)(Islamabad)(NTS)  │  quick chips → hubs
│ (PPSC)(Pak Army)(Police)(+ more)   │
├──────────── fold ──────────────────┤
│ ⏰ Jald band ho rahi hain (7)  →    │  closing soon, max 5 cards
│ [card][card][card]                 │
│ 🆕 Aaj ki nayi jobs (12)  →         │
│ [card][card][card]                 │
│ Shehar ke hisaab se    (grid)      │
│ Commission / testing   (grid)      │
│ Idare                  (grid)      │
│ Admissions (AIOU, BSN)             │
│ Alert kaise kaam karta hai (3 steps)│
│ FAQ (5, from data)                 │
│ Footer                             │
└────────────────────────────────────┘
```

- **Title:** `Govt Jobs {YYYY} Pakistan – Latest Jobs, Last Dates & Free Alerts | {Brand}`
- **Meta:** `Aaj ki {N} sarkari jobs: last date, online apply link aur official advert. Free email/push alert, koi fee nahi.`
- The proof numbers come from `/v1/stats` (`open_posts`, `closing_in_7_days`, `last_scraped_at`). If the API is down,
  the proof row is hidden; we never show a fake number.
- "Alert kaise kaam karta hai": 1. Shehar aur taleem chunein → 2. Email confirm karein (6-digit code) → 3. Nayi job aur
  last-date reminder paayein.

### 5.2 Location hub `/jobs/{city|province}` (the P1 traffic engine)

**Job:** answer "govt jobs in Karachi" better than anyone, then convert to a Karachi alert.

```
│ Home › Jobs › Karachi                │
│ Latest Govt Jobs in Karachi 2026     │  H1
│ 23 open · 5 closing this week ·      │  live counts
│ Last checked aaj 9:40 AM             │
│ ┌──────────────────────────────────┐ │
│ │🔔 Karachi ki har nayi sarkari job │ │  inline alert, prefilled city
│ │   ka free alert   [Alert lagayein]│ │
│ └──────────────────────────────────┘ │
│ Filter: (Matric)(Inter)(Bachelor)    │  query params, canonical = hub
│        (Female eligible)(BPS ▾)      │
├──────────── fold ────────────────────┤
│ [listing card] × 20, paginated       │
│ Female ke liye eligible jobs (n)     │  only if n ≥ 1
│ Jald band ho rahi hain               │
│ Karachi ke qareeb: Hyderabad (Sindh) │  nearby hubs + province hub
│ Is shehar ke idare: KMC, KWSC…       │  org links from data
│ FAQ (from data)                      │
```

- **Title:** `Latest Govt Jobs in Karachi {YYYY} – {N} Open, Last Dates & Online Apply`
- **H1:** `Latest Govt Jobs in Karachi {YYYY}`
- **Intro (2 sentences, generated):** "Karachi mein is waqt {N} sarkari jobs open hain, jin mein {top orgs}. Sab se
  qareeb last date {date} ({org}) hai."
- **FAQ from data:** "Karachi mein matric pass ke liye kitni jobs hain?" ({count}) · "Sab se qareeb last date kaunsi
  hai?" · "Kya female apply kar sakti hain?" ({count female-eligible}).
- **Hyderabad:** always "Hyderabad, Sindh" (`/jobs/hyderabad-sindh`), because tool data mixes in Hyderabad, India.

### 5.3 Commission hub `/ppsc`, `/fpsc`, `/nts`

Same layout as §5.2, plus a **lifecycle bar** under the H1, because the commission is a journey, not a list:

```
│ PPSC Jobs 2026 – Online Apply, Advertisement & Last Date │
│ (Open jobs 14)(Roll number slip)(Result)(Test date)      │  tabs → lifecycle URLs
│ 🔔 Naye PPSC advert aur result ka free alert [Alert]      │
```

- **Title:** `PPSC Jobs {YYYY} – Online Apply, Advertisement & Last Date`; `NTS Jobs {YYYY} – Apply Online,
  Advertisement & Last Date`.
- A **"PPSC online apply kaise karein"** box: 4–6 numbered steps with the official portal link. This answers the #1
  modifier in Trends.
- Seasonality: PPSC peaks in December and August, NTS in February. Hubs and the alert CTA copy are reviewed 4–6 weeks
  before the peaks.

### 5.4 Lifecycle page `/nts/roll-number-slip`, `/nts/result`, `/ppsc/result`

**Job:** the visitor has already applied; give them the official link fast and capture them for the next stage.

```
│ NTS Roll Number Slip 2026 – Download Link & Test Date │  H1
│ Last checked aaj 10:05 AM                              │
│ ┌ Search your test ───────────────────┐               │  filter by org / project
│ └──────────────────────────────────────┘               │
│ Table: Test / project · Slip status · Test date · Official link → │
│ 🔔 "Jab aap ke test ka roll slip ya result aaye, hum bata dein?" [Haan, alert] │
│ How to download (steps, official site only)            │
│ FAQ                                                    │
```

- We **link** to the official slip or result page; we never host a slip or a result.
- Each row links back to the original listing, which shows the same status.

### 5.5 Organization hub `/org/{org}`

Like §5.2, with an **organization fact box** (data only): full name, short name, official website, typical
recruitment (testing body, provinces), "last advert: {date}", and an "Archive" section of closed adverts (which keeps
the page useful between drives).

- **Title:** `{Org} Jobs {YYYY} – Latest Advertisement, Last Date & Online Apply`
- **Pak Army** targets "join pak army" phrasing in the H2 and intro ("Join Pak Army {YYYY}: online registration aur last
  date"). Trends: "pak army online apply 2026 last date" is Breakout.
- **Spike readiness** (FIA, ASF): when an archived org gets a new advert, the hub's revalidation and the alert fan-out
  happen in the same run.

### 5.6 Listing page `/jobs/{slug}-{id}` (the conversion page)

Section order is defined in frontend-plan §5; this adds the above-the-fold contract and copy.

```
│ Home › Jobs › Sindh › NICVD                       │
│ NICVD Karachi                                      │  org line
│ NICVD Jobs Oct 2026: 15 Posts, Last Date 11 Oct    │  H1
│ (Open) ⏰ 3 din baqi · Last checked 9:40 AM ✓ Source│
│ Last date 11 Oct · 15 posts · BPS 7–17 · NTS · Karachi │  facts strip
│ [ Apply online (official) ↗ ]  [ 🔔 Reminder lagayein ] │  two actions
├──────────── fold ──────────────────────────────────┤
│ Aap eligible hain? Umar ___  Taleem ▾  → result    │  eligibility checker (client)
│ Posts table → cards on mobile                       │
│ Important dates · Fee · How to apply (steps)        │
│ Important links (official portal, advert, syllabus) │
│ Test syllabus (from NTS weightage)                  │
│ 🔔 "Aisi aur jobs ka alert" (prefilled) + WhatsApp share │
│ FAQ (from data) · Related (same org / city / field) │
│ Disclaimer                                          │
```

- **"Reminder lagayein"** saves the listing and schedules the 2-day reminder (sign-in by email code if needed). It is
  the smallest possible commitment, so it converts better than a full alert wizard.
- **Closed state:** grey "Closed" chip, the H1 keeps its text, the facts strip says "Last date guzar gayi (11 Oct)", and
  the first block becomes "Is idare ki agli job ka alert" plus links to open jobs from the same org and city.
- **Deadline extended:** blue banner "Last date barha di gayi: 11 Oct → 25 Oct" (from deadline history).
- **OCR-flagged listings** (`needs_review`): noindex, and a line "Details official advert se confirm karein" next to the
  posts table.

### 5.7 Admissions `/admissions`, `/admissions/aiou`

Same hub layout. The facts strip shows session, program count, last date and entry test. Seasonality: AIOU peaks in
February and August–October, so the page and its alert copy ("AIOU admission ki last date ka reminder") are published
before January and July.

### 5.8 Freshness pages `/closing-soon`, `/new-today`

A plain sorted list with the days-left chip and the alert CTA. These are built for returning users (search demand is
near zero), linked from the home page and every hub.

### 5.9 Alert flow `/alerts/new` (wizard), success, inbox

Three steps, one screen each, prefilled from the page the user came from (frontend-plan §6). Copy:

| Step | Heading | Fields | Button |
|---|---|---|---|
| 1 | "Aap ko kaunsi jobs chahiye?" | Shehar/province chips, taleem chips, field chips, optional keywords | Aage |
| 2 | "Sirf woh jobs jin ke aap eligible hain (optional)" | Umar, experience (years) | Aage / Skip |
| 3 | "Alert kahan bhejein?" | Email → 6-digit code | Alert lagayein |

- **Success screen:** "Aap ka alert lag gaya ✓" + the 5-item bundle (§3.3) + "Aap ko aisi jobs milengi:" with the first 3
  matches (`/v1/me/matches`) + an **"Browser notifications on karein"** button. Push permission is requested only on this
  click; on iOS the copy says "Pehle Home Screen par add karein".
- **Inbox `/alerts`:** unread first, each item = listing card with a days-left chip; "Mark all read".
- No password, no phone, no CNIC, ever. The wizard says so on step 3.

### 5.10 Trust pages

- `/about`: who runs it, why, "independent, not a government body", how data is collected (official portals, daily
  checks), contact.
- `/how-it-works`: the 3 steps + the bundle + a sample alert email screenshot.
- `/report-error`: one textarea + listing id; every listing links to it ("Ghalti batayein").
- These pages feed GEO: AI answers cite pages that say clearly who they are and where the data comes from.

---

## 6. Content rules

### 6.1 Language

- **English** for titles, H1/H2, table headers, org names and data. These match what people type and what the official
  advert says.
- **Roman Urdu** for the one-line value messages, CTAs, empty states and FAQ answers. Short and plain, in the way a
  friend would say it. One language per sentence; never mix scripts in one line.
- Urdu script (Noto Nastaliq) is a later phase, only on Urdu pages.

### 6.2 Titles and descriptions (formulas, year and counts from data)

| Page | Title (≤ 60 chars where possible) |
|---|---|
| City/province hub | `Latest Govt Jobs in {Place} {YYYY} – {N} Open, Last Dates & Online Apply` |
| Commission hub | `{PPSC} Jobs {YYYY} – Online Apply, Advertisement & Last Date` |
| Org hub | `{Org} Jobs {YYYY} – Latest Advertisement, Last Date & Online Apply` |
| Lifecycle | `{NTS} Roll Number Slip {YYYY} – Download Link & Test Date` |
| Listing | `{Org short} Jobs {Mon YYYY}: {N} Posts, Last Date {DD Mon}` |
| Admission | `{Institution} Admission {Session}: Programs, Eligibility, Last Date` |

Descriptions follow frontend-plan §3.4: facts first (count, top posts, city, last date), ≤155 characters.

### 6.3 Always / never

| Always | Never |
|---|---|
| Numbers from the database (counts, dates, "last checked") | Invented numbers, "1000+ users", fake testimonials |
| The official advert and portal link on every listing | Hosting slips, results or advert copies as if they were ours |
| "Last checked {time}" and the source name | "Expected last date… or as per paper ad" |
| "Online apply kaise karein" steps | "Sarkari naukri", clickbait ("100% guaranteed job") |
| FAQ generated from real data | Spun intro text or keyword blocks |
| A disclaimer in every footer | Asking for CNIC, phone, password or any payment |

---

## 7. UI principles and hierarchy

1. **Answer first, then offer, then everything else.** The visual order on every page is: what (H1) → is it current
   (status, last checked) → key facts → action → the rest.
2. **One primary action per screen.** Content pages: "Apply online (official)" for the user's task, plus one alert CTA
   for ours. Never more than two filled buttons in view.
3. **Status is text plus color**, never color alone ("3 din baqi" in a red chip, not a red dot).
4. **Scannable, not sparse.** Lists stay dense like the competitors' (users expect it), with clean typography and
   spacing instead of borders and ads.
5. **No interruptions.** No popups, interstitials, splash screens or auto push prompts. Banners are inline and
   dismissible. (Google penalises intrusive interstitials, and this is our trust signal against jobz.pk's OneSignal
   popup.)
6. **Thumb-friendly.** Touch targets ≥44 px; the primary CTA sits in the lower half on mobile listing pages (sticky
   bottom bar that scrolls away, no overlay).
7. **Fast on bad data.** The H1 text is the LCP, there are no images above the fold, and the system font is used.
   A page must be readable with JavaScript off.

---

## 8. Design system

### 8.1 Color

Market check: jobz.pk is green (`#87B843`), ilmkidunya teal (`#15A18D`), NJP government green (`#5D7E56`), rozee
Bootstrap blue, pakistanjobsbank grey and gold. Green reads "government", which we must not imply, and it is crowded.

| Token | Value | Use |
|---|---|---|
| `--brand` | `#0F5C85` deep blue | Header, links, primary buttons |
| `--brand-ink` | `#0B3F5C` | Pressed state, footer |
| `--accent` | `#F59E0B` amber (the "bell") | Logo bell, reminder icon, small highlights only. **Never text on white** (fails contrast); text on amber uses `--text` |
| `--bg` / `--surface` | `#F8FAFC` / `#FFFFFF` | Page / cards |
| `--text` / `--muted` | `#0F172A` / `#475569` | Body / meta |
| `--border` | `#E2E8F0` | Card and table lines |
| Status | urgent `#B91C1C` on `#FEE2E2` · soon `#92400E` on `#FEF3C7` · open `#166534` on `#DCFCE7` · info `#1E40AF` on `#DBEAFE` · closed `#475569` on `#F1F5F9` | Chips (unchanged from frontend-plan §7) |

All text pairs must pass WCAG AA (4.5:1); this is checked in CI with a contrast test of the token pairs.

### 8.2 Typography

System stack (`system-ui, -apple-system, "Segoe UI", Roboto, sans-serif`), which is Roboto on Android. Sizes: body 16,
meta/table 14, H3 18, H2 20/24, H1 24 (mobile) / 30 (desktop), line-height 1.5 (1.25 for headings), weights 400/600/700.
`tabular-nums` for dates and counts. Competitors load Open Sans, Manrope or Source Sans; we skip the download.

### 8.3 Spacing, layout, shape

8 px scale (4, 8, 12, 16, 24, 32, 48). Mobile padding 16 px. Content max-width 1120 px; listing page on desktop = main
column + 320 px sticky aside (facts + both actions). Radius 8 px for cards and buttons, 999 px for chips. Shadows only
on sheets and dialogs.

### 8.4 Component inventory

| Component | Variants / states | Used on |
|---|---|---|
| `Header`, `MobileMenuSheet`, `Footer` | logged in/out | all |
| `Breadcrumbs` | — | all inner |
| `SearchBox` | idle, typing (suggest orgs/cities), no results | header, home |
| `HeroOffer` | home, hub (prefilled) | home, hubs |
| `ProofRow` | hidden when stats are unavailable | home, alert landing |
| `QuickChips` | — | home, hubs (filters) |
| `ListingCard` | open, closing (≤7d), urgent (≤3d), extended, closed, new | lists |
| `StatusChip`, `DaysLeft`, `SourceBadge` ("Last checked") | — | cards, listing |
| `FactsStrip` | job, admission, test | listing |
| `PrimaryActions` | Apply online + Reminder; closed → "Agli job ka alert" | listing |
| `EligibilityChecker` | empty, eligible, not eligible, partly | listing |
| `PostsTable` | table ≥768 px; cards + accordion below | listing |
| `HowToApply` (steps) | portal, post, in-person | listing, commission hubs |
| `ImportantLinks` | — | listing |
| `LifecycleTabs`, `LifecycleTable` | — | commission hubs, lifecycle pages |
| `OrgFactBox` | — | org hubs |
| `AlertCTA` | inline card, sticky bottom bar, footer block; prefilled context | everywhere |
| `AlertWizard` (3 steps), `CodeInput` (6 digits), `PushButton`, `InstallCard` | idle, loading, error, success | alerts |
| `WhatsAppShare` | — | listing, hubs |
| `FAQ` (accordion, JSON-LD when visible) | — | home, hubs, listing |
| `EmptyState` | hub below threshold, no filter results | hubs |
| `Banner` | deadline extended, needs review, offline | listing, global |
| `Pagination` | real `<a href>` links | lists |
| `Toast` | saved, copied, error | global |

### 8.5 Dialogs (the only ones allowed)

| Dialog | Trigger | Why it is acceptable |
|---|---|---|
| Sign-in sheet (email → code) | User taps "Reminder lagayein" or "Alert lagayein" while signed out | User-initiated, keeps the page context |
| Mobile menu sheet | Menu icon | User-initiated |
| Filter sheet (mobile) | "Filter" chip | User-initiated |
| Share fallback (copy link) | Share on a device without the share API | User-initiated |

Nothing opens by itself. The browser push prompt only follows a tap on `PushButton`.

### 8.6 Icons, images, social

lucide-react icons. No stock photos. The logo is a hand-bell mark in `--accent` with the wordmark in `--brand`. Per-page
OG images (1200×630) show org, "15 posts", "Last date 11 Oct" and the brand: this is what a WhatsApp share displays.

---

## 9. Conversion and growth mechanics

### 9.1 CTA map

| Page | Top (fold) | Middle | Bottom | Mobile sticky |
|---|---|---|---|---|
| Home | Hero "Free alert lagayein" | After "closing soon" | Before FAQ | No |
| Hub | Inline prefilled card | After 10 cards | Footer block | "🔔 {City} ka alert" bar |
| Listing | "Reminder lagayein" next to Apply | After posts table: "Aisi aur jobs" | With WhatsApp share | Apply + Reminder bar |
| Lifecycle | — | "Result aate hi bataein?" | Footer block | Bar |

### 9.2 Return loops

1. **Deadline reminder**, 2 days before the last date (saved listings).
2. **New-job digest** (email daily, or instant push for matches).
3. **Lifecycle follow-ups**: roll slip → test date → result for saved listings.
4. **Seasonal nudges** via the existing digest: "PPSC season shuru" (Dec/Aug), "AIOU admissions" (Feb/Aug–Oct).

### 9.3 Sharing

`WhatsAppShare` prefilled: "{Org} – {N} posts, last date {date}. Details aur official link: {url}?utm_source=whatsapp".
The OG image carries the same facts, so the share works even if nobody taps through.

### 9.4 Funnel and targets (first 90 days, to validate)

| Metric | Event | Target |
|---|---|---|
| Click official apply | `click_official_apply` / `view_listing` | ≥ 25% |
| Start alert | `start_alert` / sessions | ≥ 6% |
| Complete alert | `complete_alert` / `start_alert` | ≥ 50% |
| Push opt-in | `enable_push` / `complete_alert` | ≥ 30% |
| WhatsApp share | `share_whatsapp` / `view_listing` | ≥ 2% |
| Returning visitors (28 days) | analytics | ≥ 30% |

Below target: change the copy or placement first, not the feature (A/B on hero line and CTA text).

---

## 10. SEO and GEO, as applied to these templates

- Frontend-plan §3 rules hold: server rendering, unique metadata, JSON-LD, ≥3 threshold, sitemaps, canonicals,
  expired-listing archives.
- **Internal links:** every listing links to its org, city, province and commission hub; every hub links to nearby
  hubs and its top orgs; the footer carries the 4 navigation groups. No orphan pages.
- **"Online apply" + year** in titles and H2s, from Trends evidence.
- **Freshness:** "Last checked" on every page, ISR plus on-demand revalidation from the scraper.
- **GEO/AEO:** a 2-sentence factual answer at the top of each hub (who is hiring, how many, nearest last date), FAQ from
  data, `Organization` + `WebSite` schema, clear About page, AI crawlers allowed in `robots.ts`. Submit to **Bing
  Webmaster Tools** (ChatGPT search uses Bing) as well as Google Search Console.
- **Calendar:** launch the P1 hubs before December (PPSC and govt-jobs peak Dec–Jan); AIOU before January; review
  commission copy 4–6 weeks before each peak.
- **Long-term reality:** generic terms fell 55–72% in 5 years on Trends (govt jobs −72%, ppsc jobs −67%, nts jobs −63%),
  while year-suffixed queries are Breakout. Search traffic is a funnel into alerts, not the end goal; subscribers are the
  asset.

---

## 11. Performance and accessibility budgets

Unchanged from frontend-plan §8: JS < 100 KB gzipped on content pages, LCP < 2.5 s / INP < 200 ms / CLS < 0.1 at mobile
p75, Lighthouse SEO and Accessibility ≥ 95, every content page usable without JavaScript. Our target HTML size per page
is **< 60 KB** (competitors: 135–410 KB).

---

## 12. Build order (updated)

| Chunk | Contents | Why now |
|---|---|---|
| **W0** backend | Slug registry; org normalization (`org_slug`, short name: NADRA, FIA, WAPDA, MoD, Pak Army, police forces); `gender_eligibility`; education level per post; hub counts endpoint; deadline datetime + history; revalidation webhook; official apply-link field | Org, police and city hubs depend on it |
| W1 | Next.js scaffold, tokens, header/footer/menu, SEO infrastructure, CI | |
| W2 | Listing page (all states), OG image, `/listings/{id}` redirect | Conversion page first |
| W3 | Home, `/jobs`, closing-soon, new-today | |
| W4 | City + province hubs, NTS hub + lifecycle (P1), sitemaps | **Before December peak** |
| W5 | Sign-in sheet, reminder, alert wizard, inbox, settings, unsubscribe | The product |
| W6 | PWA, push button, install card | |
| W7 | Trust pages, report-error, analytics, CWV pass, Search Console + Bing | Launch |
| W8 (P2) | PPSC/FPSC hubs + PPSC scraper, org hubs (MoD, NADRA, FIA, WAPDA, Pak Army), police hubs | First month after launch |
| W9 (P3) | ASF/PAF/Railways/Navy, Sindh police, AJK, health, admissions + AIOU (before January) | |

---

## 13. Backend data each template needs

| Template | Needs (✓ = exists in `ListingDetail` today) |
|---|---|
| Listing | ✓ title, organization, last_date, days_left, status, vacancies (BPS, seats, qualification, age, fee, syllabus), attachments, announce/test date, verified, updated_at · **new:** slug, org_slug, official apply URL, deadline history, education level, gender eligibility |
| Location hub | ✓ provinces, cities filters · **new:** city slugs (incl. `hyderabad-sindh`), hub counts, female-eligible count |
| Commission hub | ✓ source (NTS) · **new:** PPSC/FPSC sources, lifecycle notices (slip, test date, result) per project |
| Org hub | **new:** org registry (name, short, slug, official site), archive of closed adverts |
| Home | ✓ `/v1/stats` (open posts, closing in 7 days, last scraped) |
| Alerts | ✓ auth, `/v1/me`, matches, inbox, push subscriptions · **new:** saved listing + reminder schedule |

---

## 14. Decisions for the owner

1. **Brand and domain:** LastBell (conditional) or another. Blocks `metadataBase`, logo, OG images and emails.
2. **Brand color:** deep blue `#0F5C85` + amber bell (recommended) or a different pair.
3. **Language mix:** English structure + Roman Urdu value lines (recommended) or full Roman Urdu UI.
4. **Ads:** none at launch (recommended; it is our trust edge). Revisit after alert retention is proven; health and
   Punjab keywords have high CPC (Rs 698–2,114), so later sponsorship is realistic.
5. **Launch target:** P1 pages live before December (PPSC/govt-jobs peak season).
