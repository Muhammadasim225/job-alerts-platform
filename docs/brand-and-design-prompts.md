# Brand identity, copy and Claude Design prompts

Status: 2026-10-10. Built on [frontend-blueprint.md](frontend-blueprint.md) (pages, components, tokens) and the keyword /
Trends / competitor research in [seo/](seo/). The name is the recommendation, not yet final: run the checks in §1.3
before buying domains.

---

## 1. Name

### 1.1 Recommendation: **LastBell** (backup: JobBell)

| Test | LastBell |
|---|---|
| Says the promise | "The last bell before the deadline": never miss a last date |
| Easy to say in Urdu and English, 2 syllables | "Laast-bel" |
| Not Indian-sounding | Yes. "Sarkari naukri" scores 0 in Pakistan on Google Trends, so "Sarkari…" names start with a handicap |
| Not tied to "govt" | Can grow to admissions, tests, results, scholarships |
| Domains (checked 2026-10-09) | lastbell.pk and lastbell.com.pk free; lastbell.com is a finance newsletter (no job conflict) |
| Conflicts | No job brand; 0 App Store results |

Rejected earlier: SarkariAlert-style names, Khabri (Indian govt-exam app), Asami (existing job portal), Elaan, Bedaar,
WaqtPar, JobGhanti, Aagah.

### 1.2 How the name is written

- Wordmark: **LastBell**, written as one word with a capital B.
- Titles and handles: "LastBell Pakistan" / `@lastbellpk`.
- Never "Last Bell" (two words), "Lastbell" or "LB".

### 1.3 Checks before buying (owner)

1. Say the name to 10 people and ask them to write it down. At least 8/10 should write "LastBell".
2. Check that the Facebook, Instagram, TikTok, X and YouTube handles are free.
3. Run a trademark search (IPO Pakistan, WIPO Global Brand Database).
4. Search Google from Pakistan for "lastbell" and check there is no conflict.
5. Register lastbell.pk and lastbell.com.pk.

---

## 2. Platform: PWA first, Play Store later, no native app now

| Option | Verdict | Why |
|---|---|---|
| **PWA (website that installs like an app)** | **Build now** | All traffic comes from Google search into web pages. Web Push works on Android Chrome and on iOS 16.4+ once installed. One codebase, no store review, instant updates, tiny size on cheap phones |
| Play Store app via **TWA** (the same PWA wrapped) | **Phase 2**, ~1 day of work | Gives Play Store presence and trust ("app hai?") with zero extra code. Needs `assetlinks.json` + Bubblewrap |
| Native Android/iOS app | **Not now** | 2–3× the cost, a second codebase, and no SEO. Only if retention data later proves users want it |

The design is therefore **mobile-first web at 360 px**, with an "Install app" card from the second visit.

---

## 3. Brand identity

### 3.1 Brand idea

**"Woh ghanti jo last date se pehle bajti hai."** (The bell that rings before the last date.)
In school, the last bell meant "time is up". LastBell rings early, so you are never late.

### 3.2 Personality and voice

| We are | We are not |
|---|---|
| A helpful elder brother or sister who knows the system | A government office |
| Clear, calm, exact (dates, counts, links) | Loud, clickbait, "100% guaranteed job" |
| Simple Roman Urdu for messages; English for job data | Urdu–English mixed in one sentence |
| Honest: "official advert se confirm karein" | Pretending to be an official source |

### 3.3 Logo

- **Mark:** an old school **hand-bell** (wooden handle, metal bell) seen from the side, slightly tilted as if ringing,
  with two short "ring" lines. Inside or under the bell sits a small **check tick** or a calendar-page corner, meaning
  "done before the deadline".
- **Not** a phone notification bell (generic, and every app uses it).
- **Colors:** bell in amber `#F59E0B`, outline and wordmark in deep blue `#0F5C85`.
- **Wordmark:** a geometric bold sans (e.g. Poppins SemiBold or Inter Bold), delivered as an **SVG outline**, so the site
  loads no font file for it.
- **Deliverables:** horizontal lockup (mark + wordmark), stacked lockup, mark only, app icon 512×512 (maskable, mark on
  `#0F5C85`), favicon 48×48 and 32×32 (mark only, simplified), and a monochrome white version for dark backgrounds.

### 3.4 Colors and type

From the blueprint §8: `--brand #0F5C85`, `--brand-ink #0B3F5C`, `--accent #F59E0B` (bell, highlights; never text on
white), `--bg #F8FAFC`, `--surface #FFFFFF`, `--text #0F172A`, `--muted #475569`, `--border #E2E8F0`, plus the status
chips (urgent red, soon amber, open green, info blue, closed grey). UI text uses the system font stack (Roboto on
Android).

### 3.5 Taglines (pick one; A/B test the top two)

1. **"Last date se pehle, LastBell."** (recommended: short, rhymes with the name, says the promise)
2. "Har sarkari job, last date se pehle."
3. "Job aayi? Hum bata denge."

---

## 4. Copy: the 10-second offer

### 4.1 Home hero

**Headline (H1), 3 variants for A/B testing:**

- A (recommended): **Sarkari job ki last date ab kabhi miss nahi hogi.**
- B: **Aap ke shehar ki har nayi sarkari job — sab se pehle aap ke phone par.**
- C: **NTS, PPSC, FPSC, Army, Police — nayi job aate hi free alert.**

**Sub-headline:** Apna shehar aur taleem chunein. Nayi job aate hi free alert, aur last date se 2 din pehle reminder.

**Primary button:** Free alert lagayein

**Proof row (live numbers only):** ✓ Aaj {n} jobs check ki gayin · ✓ Har job ke saath official link · ✓ Koi fee nahi,
koi CNIC nahi

**Audience line (under the chips):** Matric se Masters tak — Karachi se Gilgit tak.

### 4.2 Why visitors get it in 10 seconds

| Second | Question in their head | Answered by |
|---|---|---|
| 0–3 | "Kya yeh meri jobs ki site hai?" | H1 + "NTS, PPSC, Army, Police" chips |
| 3–7 | "Is mein mera kya faida?" | Sub-line: alert + 2-day reminder |
| 7–10 | "Koi chakkar to nahi?" | Proof row: official link, no fee, no CNIC |

### 4.3 The bundle, in user words (alert landing and wizard success)

1. ✅ Nayi job ka alert — sirf aap ke shehar aur taleem ki
2. ⏰ Last date se 2 din pehle reminder
3. 🎯 Sirf woh posts jin ke aap eligible hain (umar aur taleem)
4. 📄 Roll number slip, test date aur result ki khabar
5. 🔗 Har job ka official advert aur apply link

### 4.4 Page microcopy

| Place | Copy |
|---|---|
| City hub alert card | 🔔 {Karachi} ki har nayi sarkari job ka free alert — [Alert lagayein] |
| Commission hub card | 🔔 Naye {PPSC} advert aur result ka free alert — [Alert lagayein] |
| Listing, next to Apply | [Apply online (official) ↗] [🔔 Reminder lagayein] |
| Listing, days left chip | ⏰ 3 din baqi · Aaj aakhri din · Last date guzar gayi |
| Deadline extended banner | Last date barha di gayi: 11 Oct → 25 Oct |
| Closed listing | Yeh job band ho chuki hai. {Org} ki agli job ka alert lagayein? |
| Eligibility result | ✓ Aap eligible hain · ✗ Umar ki had 30 saal hai (aap 32) · ? Taleem official advert se confirm karein |
| Lifecycle prompt | Jab aap ke test ka roll slip ya result aaye, hum bata dein? [Haan, alert] |
| Wizard step 3 | Sirf email chahiye. Koi password, phone ya CNIC nahi. |
| Wizard success | Aap ka alert lag gaya ✓ Aap ko aisi jobs milengi: |
| Push button | Browser notifications on karein — job aate hi phone par pata chal jayega |
| Empty hub | Abhi {Sialkot} mein koi open job nahi. Alert laga dein — pehli job aate hi bata denge. |
| Footer disclaimer | LastBell ek independent website hai, kisi sarkari idare se taaluq nahi. Hamesha official advert se confirm karein. |
| WhatsApp share text | {Org} – {N} posts, last date {date}. Details aur official link: {url} |

---

## 5. Claude Design prompts

How to use: start a new Claude Design project, paste **Prompt 0** first (it sets the whole system), then each screen
prompt one by one in the same project. Sample data in the prompts is for mockups only; the live site shows database
numbers.

### Prompt 0 — Project brief and design system (paste first)

```
You are designing "LastBell" (tagline: "Last date se pehle, LastBell."), a mobile-first Progressive Web App for
Pakistan that lists GOVERNMENT jobs only (NTS, PPSC, FPSC, Pak Army, Police, FIA, NADRA, WAPDA, city-wise jobs) and
sends free alerts plus a reminder 2 days before each last date.

AUDIENCE: Pakistani government-job seekers, age 18–30, Matric to Masters, many outside big cities, on mid-range Android
phones with slow, prepaid mobile data. They read English job terms (BPS, NTS, last date, apply online) but prefer
simple Roman Urdu for messages. They fear fake adverts and fee scams, and they live on WhatsApp.

COMPETITORS look like this (avoid it): green themes, 8–16 ads per page, popups, scanned advert images instead of text,
"expected last date or as per paper ad". We must feel faster, cleaner and more trustworthy, but still DENSE and
scannable (users expect long lists), never a sparse marketing site. We must never look like an official government
website (no green, no state emblem).

DESIGN SYSTEM (use exactly):
- Colors: brand #0F5C85 (header, links, primary buttons), brand-ink #0B3F5C (pressed, footer), accent amber #F59E0B
  (the bell logo, reminder icon and small highlights only, never as text on white), page background #F8FAFC, cards
  #FFFFFF, text #0F172A, muted text #475569, borders #E2E8F0.
- Status chips (text + background, always with words, never color alone): urgent "3 din baqi" #B91C1C on #FEE2E2;
  closing soon #92400E on #FEF3C7; open #166534 on #DCFCE7; extended/new/result #1E40AF on #DBEAFE; closed #475569 on
  #F1F5F9.
- Typography: system font (Roboto on Android). Body 16px, meta/table 14px, H3 18px, H2 20px, H1 24px mobile / 30px
  desktop, line-height 1.5, weights 400/600/700, tabular numbers for dates and counts.
- Spacing on an 8px scale (4, 8, 12, 16, 24, 32, 48); mobile side padding 16px; touch targets at least 44px; card and
  button radius 8px, chips fully rounded; shadows only on sheets/dialogs.
- Icons: lucide line icons. No stock photos and no illustrations above the fold. The page's largest element is the H1
  text, never an image.
- Language: English for titles, headings, table headers and job data; simple Roman Urdu for value lines, buttons and
  empty states. Never mix both in one sentence. Never use the phrase "sarkari naukri".

RULES: one primary filled button per screen section; no popups or auto-opening dialogs; a disclaimer in every footer
("LastBell ek independent website hai, kisi sarkari idare se taaluq nahi. Hamesha official advert se confirm
karein."); WCAG AA contrast. Design every screen at 360×800 first, then show a 1280px desktop version where asked.

Confirm the system by producing a one-page style guide: color swatches with hex, the type scale, buttons (primary,
secondary, ghost, disabled, loading), all status chips, an input, a chip group, and a ListingCard in its 5 states
(open, closing ≤7 days, urgent ≤3 days, extended, closed).
```

### Prompt 1 — Logo and app icon

```
Design the LastBell logo. Mark: an old school HAND-BELL (wooden handle, metal bell) seen from the side, slightly
tilted as if ringing, with two short motion lines; add a small check tick or a calendar-page corner to say "done
before the deadline". It must NOT look like a phone notification bell. Bell in amber #F59E0B, outline and details in
deep blue #0F5C85. Wordmark "LastBell" (one word, capital B) in a geometric bold sans (Poppins SemiBold or Inter Bold
style), deep blue.
Deliver: horizontal lockup, stacked lockup, mark only, app icon 512×512 (mark centred on #0F5C85, safe zone for a
maskable icon), favicon versions at 48px and 32px (simplified mark that stays readable), and a white monochrome
version on #0B3F5C. Flat vector, no gradients, no 3D. Show the mark at 24px next to the wordmark in a 56px mobile
header to prove it reads small.
```

### Prompt 2 — Home page (mobile 360px, then desktop)

```
Design the LastBell HOME page, mobile 360×800 first.
Header (56px): bell logo + "LastBell" left; search icon and a small filled "Alert" button right.
Hero (must be fully visible above the fold, no image):
- H1: "Sarkari job ki last date ab kabhi miss nahi hogi."
- Sub-line: "Apna shehar aur taleem chunein. Nayi job aate hi free alert, aur last date se 2 din pehle reminder."
- Primary button, full width: "Free alert lagayein"
- Proof row with check icons: "Aaj 214 jobs check ki gayin" · "Har job ke saath official link" · "Koi fee nahi, koi
  CNIC nahi"
- Quick chips (2 rows, horizontally scrollable): Karachi, Lahore, Islamabad, NTS, PPSC, Pak Army, Police, + More
Below the fold, in this order:
1. "⏰ Jald band ho rahi hain (7)" with 3 ListingCards and "Sab dekhein →"
2. "🆕 Aaj ki nayi jobs (12)" with 3 ListingCards
3. Browse grids: "Shehar" (Karachi, Lahore, Islamabad, Rawalpindi, Multan, Faisalabad, Peshawar, Quetta),
   "Commission" (NTS, PPSC, FPSC, SPSC, KPPSC), "Idare" (Pak Army, Police, FIA, NADRA, WAPDA, ASF, MoD), each item with
   a live count
4. "Alert kaise kaam karta hai" — 3 numbered steps: Shehar aur taleem chunein → Email confirm karein (6-digit code) →
   Nayi job aur last-date reminder paayein
5. FAQ accordion (5 questions)
6. Footer: 4 link groups (Shehar, Commission, Idare, Admissions), About, Privacy, Contact, disclaimer.
ListingCard content example: org "NICVD Karachi", title "NICVD Jobs Oct 2026: 15 Posts", facts line "Last date 11
Oct · BPS 7–17 · NTS", chip "⏰ 3 din baqi".
Then show the same page at 1280px: hero left, a compact "closing soon" list on the right, grids below.
```

### Prompt 3 — City hub (example: Karachi)

```
Design the CITY HUB page "Latest Govt Jobs in Karachi 2026", mobile 360px then 1280px.
Top: breadcrumbs "Home › Jobs › Karachi"; H1 "Latest Govt Jobs in Karachi 2026"; meta line "23 open · 5 closing this
week · Last checked aaj 9:40 AM" with a small check-shield icon.
Inline alert card (light brand tint, bell icon): "Karachi ki har nayi sarkari job ka free alert" + button "Alert
lagayein".
Filter chips row: Matric, Inter, Bachelor, Female eligible, BPS ▾ (opens a bottom sheet).
Then a dense list of 20 ListingCards with real-looking Karachi government orgs (KMC, KWSC, Sindh Police, JPMC, NICVD,
Pakistan Steel, Port Qasim), mixed states (open, ≤7 days, ≤3 days, extended), then numbered pagination with real links.
After 10 cards insert a slim alert banner. Then sections: "Female ke liye eligible jobs (4)", "Jald band ho rahi hain",
"Qareeb ke shehar: Hyderabad (Sindh), Thatta", "Karachi ke idare" (org links), FAQ from data ("Karachi mein matric
pass ke liye kitni jobs hain?", "Sab se qareeb last date kaunsi hai?").
Mobile: a slim sticky bottom bar "🔔 Karachi ka alert" that hides on scroll down and shows on scroll up (no overlay).
Also show the EMPTY state for a small city: "Abhi Sialkot mein koi open job nahi. Alert laga dein — pehli job aate hi
bata denge." with one button.
```

### Prompt 4 — Listing page (the conversion page)

```
Design the JOB LISTING page, mobile 360px then 1280px (desktop = main column + 320px sticky right aside holding the
facts and both buttons).
Above the fold on mobile, in this order:
- Breadcrumbs "Home › Jobs › Sindh › NICVD"
- Small org line "National Institute of Cardiovascular Diseases (NICVD), Karachi"
- H1 "NICVD Jobs Oct 2026: 15 Posts, Last Date 11 Oct"
- Row: chip "Open", chip "⏰ 3 din baqi", "Last checked 9:40 AM" with a source/shield icon
- Facts strip, one line each with middle dots: "Last date 11 Oct 2026 · 15 posts · BPS 7–17 · Test: NTS · Karachi"
- Two buttons side by side: primary "Apply online (official) ↗" and secondary with bell "Reminder lagayein"
Below the fold:
- "Aap eligible hain?" mini checker: age input + education dropdown → result line (show eligible, not eligible with
  reason, and "confirm in advert" states)
- Posts table (Post | BPS | Seats | Qualification | Age | Experience) with 6 realistic rows (Staff Nurse BPS-16,
  Computer Operator BPS-12, Lab Technician BPS-14, Ward Boy BPS-3, etc.); on mobile each row becomes a card with an
  accordion for details
- Important dates, Fee (Rs 800 NTS fee), "Online apply kaise karein" numbered steps (4 steps) with the official portal
- Important links table: Apply on official portal, Official advertisement (image/PDF), Test syllabus, Official website
- Test syllabus chips with weightage (English 20%, General Knowledge 20%, Subject 60%)
- Card "Aisi aur jobs ka alert" (prefilled: Karachi, Health) + green WhatsApp share button "WhatsApp par share karein"
- FAQ (from data), Related jobs (same org / city / field), "Ghalti batayein" link, footer disclaimer
Also design 2 variants of the header block: (a) CLOSED: grey "Closed" chip, "Last date guzar gayi (11 Oct)", first
block becomes "NICVD ki agli job ka alert"; (b) EXTENDED: blue banner "Last date barha di gayi: 11 Oct → 25 Oct".
Mobile sticky bottom bar: "Apply online ↗" + "🔔 Reminder".
```

### Prompt 5 — Commission hub with lifecycle (example: PPSC)

```
Design the COMMISSION HUB "PPSC Jobs 2026 – Online Apply, Advertisement & Last Date", mobile then desktop.
Under the H1 add lifecycle tabs as chips that are links: "Open jobs (14)" (active), "Roll number slip", "Result",
"Test date".
Alert card: "Naye PPSC advert aur result ka free alert" + button.
A boxed "PPSC online apply kaise karein" with 5 numbered steps and an "Official PPSC portal ↗" link.
Then the listing list (PPSC posts: Lecturer, Assistant, Tehsildar, Sub-Inspector, Junior Clerk), FAQ, related
commissions (FPSC, SPSC, KPPSC, NTS).
Then design the LIFECYCLE page "NTS Roll Number Slip 2026 – Download Link & Test Date": search box (by organization or
project), a table "Test / Project | Slip status | Test date | Official link ↗", a prompt card "Jab aap ke test ka roll
slip ya result aaye, hum bata dein? [Haan, alert]", "How to download" steps (official site only), FAQ.
```

### Prompt 6 — Alert wizard, sign-in and success

```
Design the ALERT flow as full screens on mobile 360px (and a centred 480px card on desktop).
Progress indicator "1 / 3".
Step 1 "Aap ko kaunsi jobs chahiye?": multi-select chip groups — Shehar/Province (Karachi, Lahore, Islamabad, Punjab,
Sindh, KPK, Balochistan, + search), Taleem (Matric, Inter, Bachelor, Master, Diploma), Field (Health, Education,
Police/Forces, IT, Engineering, Clerical, Any). Pre-selected example: Karachi, Bachelor. Button "Aage".
Step 2 "Sirf woh jobs jin ke aap eligible hain (optional)": Umar (number), Experience (years). Buttons "Aage" and text
link "Skip".
Step 3 "Alert kahan bhejein?": email field, helper "Sirf email chahiye. Koi password, phone ya CNIC nahi.", button
"Code bhejein"; then a 6-box OTP input screen "Aap ke email par 6-digit code bheja gaya" with resend timer.
SUCCESS screen: big check "Aap ka alert lag gaya ✓", the 5-item bundle list (Nayi job ka alert; Last date se 2 din
pehle reminder; Sirf eligible posts; Roll slip, test date aur result ki khabar; Official advert aur apply link), then
"Aap ko aisi jobs milengi:" with 3 ListingCards, then a primary button "Browser notifications on karein" with helper
"Job aate hi phone par pata chal jayega". iPhone variant helper: "Pehle 'Add to Home Screen' karein".
Also the SIGN-IN bottom sheet used when a signed-out user taps "Reminder lagayein" on a listing (email → code, keeps the
page behind it).
```

### Prompt 7 — Inbox, settings and install card

```
Design: (1) ALERTS INBOX "Aap ke alerts": tabs "Naye (5)" / "Sab"; each item is a ListingCard with an unread dot,
received time and days-left chip; "Sab parh liye" action; empty state "Abhi koi naya alert nahi — hum dhyan rakh rahe
hain." (2) SETTINGS: alert preferences as editable chip groups, email digest frequency (Rozana / Haftawar / Band),
push on/off toggle, saved jobs with reminder toggles, sign out. (3) INSTALL CARD shown from the 2nd visit, inline and
dismissible (not a popup): bell icon, "LastBell ko phone par app ki tarah install karein — 1 MB se kam, data bachta
hai", buttons "Install" and "Abhi nahi".
```

### Prompt 8 — WhatsApp share image and email digest

```
Design (1) a 1200×630 OPEN GRAPH image template used when a job link is shared on WhatsApp: white background, top-left
LastBell logo, large org name "NICVD Karachi", big line "15 Posts · Last Date 11 Oct", chip "BPS 7–17 · NTS", amber
bell accent, footer "lastbell.pk". Readable when shown as a small WhatsApp preview. Also a hub variant: "Govt Jobs in
Karachi — 23 open".
(2) the daily EMAIL DIGEST (600px wide, mobile friendly): subject line "Karachi: 4 nayi sarkari jobs, 2 ki last date
is hafte", header with logo, "Aaj ki nayi jobs (4)" list with org, title, last date, days-left chip and "Details →"
button, a "Reminder: in ki last date 2 din mein" block, footer with "Alert badlein" and one-click "Unsubscribe", and
the disclaimer.
```

### Prompt 9 — Trust pages

```
Design the ABOUT page and HOW IT WORKS page, mobile first. About: "LastBell kaun hai?" (independent, not a government
body), "Data kahan se aata hai?" (official portals like NTS, PPSC, FPSC; checked daily; every listing shows 'last
checked' time and the official link), "Hum kya kabhi nahi karte" (no fee, no CNIC, no selling data, no fake jobs),
contact email and "Ghalti batayein" link. How it works: the 3 steps, the 5-item bundle, and a sample alert email
preview. Calm, factual, no stock photos.
```

---

## 6. After the designs come back (checklist)

- [ ] Every screen: is the 10-second test passed at 360×640 (H1 + facts + one CTA visible)?
- [ ] No green brand color, no government emblem, no popups.
- [ ] Status chips have words, not only color; contrast passes AA.
- [ ] Numbers in mockups are clearly sample data; the build uses `/v1/stats` and listing data only.
- [ ] Components map 1:1 to the inventory in [frontend-blueprint.md](frontend-blueprint.md) §8.4.
- [ ] Export: logo SVGs, app icons (192, 512, maskable 512, 180 Apple), favicon.ico, OG template.
