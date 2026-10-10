"""What a notification says: alerts -> digest email / push payload, and the sign-in email.

Every item links to the listing page on the website and to the official source, so a
reader can always check the advert itself.
"""

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import Session

import config
from channels import Email
from shared.models import Alert, Listing, Program, User, Vacancy
from shared.security import sign

MAX_POSTS_PER_ITEM = 5
PUSH_BODY_MAX = 180

_env = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(enabled_extensions=("html",), default_for_string=False),
    undefined=StrictUndefined,
    trim_blocks=True,
    lstrip_blocks=True,
)


@dataclass
class Item:
    alert_type: str  # new | deadline_reminder | updated
    kind: str  # job | admission | test
    title: str
    organization: str | None
    last_date: date | None
    days_left: int | None
    posts: list[str]
    more_posts: int
    web_url: str
    official_url: str


def load_items(session: Session, alert_ids: list[int], today: date | None = None) -> list[Item]:
    """The alerts of a delivery, reminders first, then closing soonest. Four queries."""
    today = today or date.today()
    alerts = session.scalars(select(Alert).where(Alert.id.in_(alert_ids))).all() if alert_ids else []
    listings = {l.id: l for l in session.scalars(select(Listing).where(Listing.id.in_({a.listing_id for a in alerts})))}
    vids = [i for a in alerts for i in a.matched_vacancy_ids]
    pids = [i for a in alerts for i in a.matched_program_ids]
    vnames = (
        dict(session.execute(select(Vacancy.id, Vacancy.post_name).where(Vacancy.id.in_(vids))).tuples().all()) if vids else {}
    )
    pnames = dict(session.execute(select(Program.id, Program.name).where(Program.id.in_(pids))).tuples().all()) if pids else {}

    items = []
    for a in alerts:
        listing = listings.get(a.listing_id)
        if listing is None:
            continue
        posts = [vnames[i] for i in a.matched_vacancy_ids if i in vnames] + [
            pnames[i] for i in a.matched_program_ids if i in pnames
        ]
        days_left = (listing.last_date - today).days if listing.last_date and listing.last_date >= today else None
        items.append(
            Item(
                alert_type=a.alert_type,
                kind=listing.kind,
                title=listing.title,
                organization=listing.organization,
                last_date=listing.last_date,
                days_left=days_left,
                posts=posts[:MAX_POSTS_PER_ITEM],
                more_posts=max(0, len(posts) - MAX_POSTS_PER_ITEM),
                web_url=f"{config.WEB_BASE_URL}/listings/{listing.id}",
                official_url=listing.url,
            )
        )
    items.sort(key=lambda i: (i.alert_type != "deadline_reminder", i.last_date or date.max))
    return items


def _noun(items: list[Item]) -> str:
    kinds = {i.kind for i in items}
    if kinds == {"job"}:
        return "job" if len(items) == 1 else "jobs"
    if kinds <= {"admission", "test"}:
        return "admission" if len(items) == 1 else "admissions"
    return "listing" if len(items) == 1 else "listings"


def digest_subject(items: list[Item]) -> str:
    reminders = [i for i in items if i.alert_type == "deadline_reminder"]
    new = [i for i in items if i.alert_type != "deadline_reminder"]
    if not new:
        if len(reminders) == 1:
            r = reminders[0]
            when = "Last day today" if r.days_left == 0 else f"Last date in {r.days_left} days" if r.days_left else "Closing soon"
            return f"{when}: {r.title}"[:150]
        return f"{len(reminders)} deadlines coming up"
    subject = f"New {_noun(new)}: {new[0].title}" if len(new) == 1 else f"{len(new)} new {_noun(new)} for you"
    if reminders:
        subject += f" (+{len(reminders)} closing soon)"
    return subject[:150]


def unsubscribe_token(user_id: int) -> str:
    return sign({"uid": user_id}, "unsubscribe", config.UNSUBSCRIBE_LINK_DAYS * 86400)


def digest_email(user: User, items: list[Item]) -> Email:
    token = unsubscribe_token(user.id)
    ctx = {
        "user": user,
        "items": items,
        "subject": digest_subject(items),
        "inbox_url": f"{config.WEB_BASE_URL}/alerts",
        "settings_url": f"{config.WEB_BASE_URL}/settings",
        "unsubscribe_url": f"{config.WEB_BASE_URL}/unsubscribe?token={token}",
    }
    return Email(
        to=user.email,
        subject=ctx["subject"],
        text=_env.get_template("digest.txt").render(ctx),
        html=_env.get_template("digest.html").render(ctx),
        headers={
            # RFC 8058 one-click: mail apps show "Unsubscribe" and POST here directly
            "List-Unsubscribe": f"<{config.API_PUBLIC_URL}/v1/email/unsubscribe?token={token}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )


def digest_push(items: list[Item]) -> dict:
    """Payload for the website's service worker (showNotification). Kept well under
    the 4 KB Web Push limit."""
    first = items[0]
    if len(items) == 1:
        body = first.title
        if first.days_left == 0:
            body += " · last day today"
        elif first.days_left is not None:
            body += f" · last date in {first.days_left} days"
        url = first.web_url
    else:
        body = "; ".join(i.title for i in items[:3])
        url = f"{config.WEB_BASE_URL}/alerts"
    return {
        "title": digest_subject(items)[:80],
        "body": body[:PUSH_BODY_MAX],
        "url": url,
        "tag": "lastbell-alerts",  # a newer digest replaces an unread older one
        "count": len(items),
    }


def login_email(email: str, code: str, ttl_minutes: int = 10) -> Email:
    ctx = {"code": code, "ttl_minutes": ttl_minutes, "web_url": config.WEB_BASE_URL}
    return Email(
        to=email,
        subject=f"{code} is your LastBell sign-in code",
        text=_env.get_template("login_code.txt").render(ctx),
        html=_env.get_template("login_code.html").render(ctx),
    )
