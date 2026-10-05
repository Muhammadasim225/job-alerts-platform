# notifier — email digests and Web Push

A small Celery worker (queue `notify`) that turns a user's alerts into notifications and sends the website's sign-in
codes. It has no scraping or OCR code, so it stays light and can be scaled on its own.

```
scraper: listing stored -> matching -> alerts (pending)
Beat, every 2 min: notify.dispatch
    -> shared.notifications.dispatch(): settled alerts -> one delivery per user per channel
    -> take_due(): new, retry-due and stale deliveries -> notify.deliver(id), one task each
notify.deliver: claim (SKIP LOCKED) -> render -> SMTP / Web Push -> sent | retry | failed | skipped
```

## What users get

- **Email digest:** one email per batch, e.g. "3 new jobs for you", listing each job with its matched posts, last
  date, days left, a link to the listing page and a link to the **official advert**. Deadline reminders are marked
  "CLOSING SOON" and listed first. The email has a plain-text and an HTML version, and RFC 8058 one-click unsubscribe
  headers (`List-Unsubscribe`), which Gmail and Outlook show as an "Unsubscribe" button.
- **Web Push:** one notification per batch on every registered browser (phone or desktop), opening the listing, or the
  inbox when there are several. A newer push replaces an unread older one (`tag`).
- **Sign-in codes** (`notify.send_login_code`) from the API, retried quickly because the user is waiting.

## Reliability

- **Sent once.** A delivery is claimed in Postgres (`FOR UPDATE SKIP LOCKED`) and the claim is committed before the
  network call. A second worker, or a redelivered message, finds nothing to send.
- **Retries** are stored in Postgres, not in the broker: after 1 min, 5 min, 30 min and 2 h, then the delivery fails. A
  lost broker message is enqueued again by a later dispatch run.
- **Permanent errors are not retried:** an SMTP 5xx (except 552, mailbox full), or a push rejected with 400 or 413.
- **Dead browsers are removed.** A push endpoint answering 404 or 410 has its subscription deleted.
- **Switching off works at once.** If a user turns email or push off after dispatch, the delivery is skipped.
- **No secrets in logs.** Sign-in task arguments are redacted in logs and Flower, and scrubbed from Sentry events.

## Tasks

| Task | When | What |
|---|---|---|
| `notify.dispatch` | every 2 min (Beat) | Batch settled alerts and enqueue due deliveries. An empty run takes about 25 ms |
| `notify.deliver` | per delivery | Send one email digest or one push (to all of the user's browsers) |
| `notify.send_login_code` | API sign-in | Email a 6-digit code |
| `notify.housekeeping` | 03:30 daily (Beat) | Drop expired sessions, and finished deliveries older than 90 days |

There is one Beat in the system (`scraper-beat`), and it schedules these tasks by name. Scaling notifiers
(`docker compose up -d --scale notifier=3`) never multiplies them.

## Settings (`.env`)

| Variable | Meaning |
|---|---|
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_SECURITY` (`none`/`starttls`/`ssl`), `SMTP_USER`, `SMTP_PASSWORD` | Mail server. Locally Mailpit (`mailpit:1025`) |
| `EMAIL_FROM`, `EMAIL_REPLY_TO` | Sender |
| `VAPID_PRIVATE_KEY`, `VAPID_PUBLIC_KEY`, `VAPID_SUBJECT` | Web Push keys. Generate once with `uv run python vapid.py`; the API hands the public one to browsers |
| `WEB_BASE_URL`, `API_PUBLIC_URL` | Links in messages |
| `APP_SECRET` | Signs unsubscribe links. Must match the API |
| `NOTIFY_CONCURRENCY` (8), `DELIVER_RATE_LIMIT` (e.g. `20/s`) | Throughput. Keep it under the email provider's limit |

## Running locally

```bash
docker compose up -d --build notifier mailpit
docker compose logs -f notifier
docker compose exec notifier celery -A celery_app call notify.dispatch --queue notify   # dispatch now
```

Every email lands in **Mailpit at http://localhost:8025**. Nothing leaves the machine.

## Going live

- **Email:** point `SMTP_*` at a provider (Brevo, Resend, Amazon SES and others). Set SPF, DKIM and DMARC on the
  sending domain, or the emails go to spam.
- **Web Push** needs the website on HTTPS, and a service worker that shows the payload:

```js
self.addEventListener("push", (e) => {
  const d = e.data.json();
  e.waitUntil(self.registration.showNotification(d.title, { body: d.body, tag: d.tag, data: { url: d.url } }));
});
self.addEventListener("notificationclick", (e) => { e.notification.close(); e.waitUntil(clients.openWindow(e.notification.data.url)); });
```

## Tests

```bash
docker compose up -d postgres
cd apps/notifier && uv run pytest   # throwaway <db>_notifytest database, fake SMTP and push transports
```
