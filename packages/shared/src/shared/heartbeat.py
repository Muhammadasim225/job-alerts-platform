"""Dead-man's-switch pings (Healthchecks.io or any compatible URL).

Each scheduled job pings its URL when it finishes ("/fail" when it failed). If the
pings stop, Healthchecks raises the alarm: a scraper that silently stops would
otherwise kill the product without anyone noticing. A ping never raises and gives up
after a few seconds, so monitoring can never break the job it watches.
"""

import logging
import urllib.request

log = logging.getLogger(__name__)
TIMEOUT_S = 5


def ping(url: str | None, *, ok: bool = True, message: str = "") -> bool:
    """POST to url (or url/fail). No URL configured = no-op. Returns True if sent."""
    if not url:
        return False
    target = url.rstrip("/") + ("" if ok else "/fail")
    try:
        req = urllib.request.Request(target, data=message[:10_000].encode(), method="POST")
        with urllib.request.urlopen(req, timeout=TIMEOUT_S):
            return True
    except Exception as exc:  # monitoring must never break the job
        log.warning("Heartbeat ping failed: %s", type(exc).__name__)
        return False
