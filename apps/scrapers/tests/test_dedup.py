import fakeredis
import pytest

from nts import dedup


@pytest.fixture
def r():
    return fakeredis.FakeRedis(decode_responses=True)


def listing(**overrides):
    base = {
        "listing_id": "portal-1",
        "status": "open",
        "title": "Some Authority",
        "deadline_raw": "8th October 2026",
        "detail": {"last_date_raw": "2026-10-08", "attachments": [{"url": "https://x/a.pdf"}], "posts": [{"raw": "Clerk BPS-11"}]},
    }
    return {**base, **overrides}


def test_new_listing_is_processed_once(r):
    item = listing()
    assert dedup.is_new_or_changed(item, r)
    assert not dedup.was_seen_before("portal-1", r)
    dedup.mark_processed(item, r)
    assert dedup.was_seen_before("portal-1", r)
    # Re-scraping the same listing must not trigger it again
    assert not dedup.is_new_or_changed(listing(scraped_at="later"), r)


def test_changed_deadline_or_new_post_triggers_again(r):
    dedup.mark_processed(listing(), r)
    assert dedup.is_new_or_changed(listing(deadline_raw="15th October 2026"), r)
    changed = listing()
    changed["detail"] = {**changed["detail"], "posts": [{"raw": "Clerk BPS-11"}, {"raw": "Driver BPS-4"}]}
    assert dedup.is_new_or_changed(changed, r)


def test_status_change_alone_does_not_retrigger(r):
    dedup.mark_processed(listing(), r)
    closed = listing(status="closed")
    assert not dedup.is_new_or_changed(closed, r)
    dedup.update_status(closed, r)
    assert r.hget("nts:listing:portal-1", "status") == "closed"


def test_forget_listing(r):
    dedup.mark_processed(listing(), r)
    dedup.forget_listing("portal-1", r)
    assert dedup.is_new_or_changed(listing(), r)


def test_file_hash_memory(r):
    assert dedup.known_file_hash("https://x/a.pdf", r) is None
    dedup.remember_file("https://x/a.pdf", "abc", r)
    assert dedup.known_file_hash("https://x/a.pdf", r) == "abc"


def test_claim_blocks_second_dispatch_of_same_version(r):
    item = listing()
    assert dedup.claim(item, r=r)
    assert not dedup.claim(item, r=r)
    # A genuinely new version can be claimed while the old one is in flight
    assert dedup.claim(listing(deadline_raw="15th October 2026"), r=r)
    dedup.release_claim(item, r)
    assert dedup.claim(item, r=r)
