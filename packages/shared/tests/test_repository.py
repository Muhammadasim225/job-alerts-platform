"""Upserts with real normalized records produced by the scraper."""

import copy
import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from shared.models import HubSlug, Listing, Organization
from shared.reference import HUBS, ORGANIZATIONS, sync_reference_data
from shared.repository import backfill_listings, enrich_listing, resolve_organization, upsert_listing

FIXTURES = Path(__file__).parent / "fixtures"


def record(name: str) -> dict:
    return json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))


def test_insert_job_listing(session):
    res = upsert_listing(session, record("record_job_wcla"))
    listing = res.listing
    assert res.is_new and listing.kind == "job" and listing.external_id == "portal-101334"
    assert listing.last_date == date(2026, 9, 28)
    assert [v.post_name for v in listing.vacancies] == ["Deputy Director (Design)", "Computer Operator"]
    co = listing.vacancies[1]
    assert (co.bps_min, co.total_posts, co.field) == (12, 2, "it")
    assert any(s["subject"] == "Fundamentals of IT" for s in co.test_syllabus)
    assert {a.role for a in listing.attachments} == {"advert", "syllabus"}


def test_insert_admission_listing(session):
    listing = upsert_listing(session, record("record_admission_uom")).listing
    assert listing.kind == "admission" and len(listing.programs) == 10 and not listing.vacancies
    assert listing.programs[2].subjects == ["Pharmacy", "Mathematics", "Biotechnology", "Geology", "Computer Science"]
    assert {r["test"] for r in listing.advert_facts["test_requirements"]} == {"GAT-General", "GAT-Subject"}


def test_update_replaces_children_and_reports_changes(session):
    rec = record("record_job_wcla")
    first = upsert_listing(session, rec).listing

    updated = copy.deepcopy(rec)
    updated["last_date"] = "2026-10-05"  # deadline extended
    updated["vacancies"] = updated["vacancies"][:1]
    res = upsert_listing(session, updated)

    assert not res.is_new and res.listing.id == first.id
    assert res.changed_fields == ["last_date"]
    assert len(res.listing.vacancies) == 1


def test_reupsert_same_record_changes_nothing(session):
    rec = record("record_job_wcla")
    upsert_listing(session, rec)
    assert upsert_listing(session, rec).changed_fields == []


# --- data model v2: organization, slug, education, gender ---------------------------


def test_upsert_fills_website_fields(session):
    listing = upsert_listing(session, record("record_job_wcla")).listing
    assert listing.org.name == "Punjab Walled Cities and Heritage Areas Authority"
    assert listing.slug == "punjab-walled-cities-and-heritage-areas-authority-lahore-jobs-sep-2026"
    co = listing.vacancies[1]
    assert co.post_name == "Computer Operator" and co.education_levels == ["intermediate"]
    assert listing.vacancies[0].education_levels == ["bachelor"]


def test_gender_comes_from_advert_facts(session):
    rec = record("record_job_wcla")
    rec["advert_facts"] = {**(rec.get("advert_facts") or {}), "gender": "both"}
    listing = upsert_listing(session, rec).listing
    assert {v.gender for v in listing.vacancies} == {"any"}


def test_same_employer_resolves_to_one_organization(session):
    a = resolve_organization(
        session, "National Institute of Cardiovascular Diseases (NICVD) (Career Opportunities)", kind="job", source="nts"
    )
    b = resolve_organization(
        session, "National Institute of Cardiovascular Diseases (NICVD) (Vacancies Announcement)", kind="job", source="nts"
    )
    c = resolve_organization(session, "NICVD", kind="job", source="nts")
    assert a.id == b.id == c.id and a.slug == "nicvd" and not a.curated


def test_curated_alias_wins(session):
    org = resolve_organization(session, "National Testing Service - Pakistan (Job Opportunities)", kind="job", source="nts")
    assert org.slug == "nts" and org.curated and org.official_url == "https://www.nts.org.pk"
    gat = resolve_organization(session, "Graduate Assessment Test (GAT Subject 2026-VI)", kind="test", source="nts")
    assert gat.slug == "nts"


def test_slug_clash_between_different_employers_gets_a_suffix(session):
    first = resolve_organization(session, "Security Papers Limited (SPL)", kind="job", source="nts")
    other = resolve_organization(session, "Sindh Power Limited (SPL Sindh)", kind="job", source="nts")
    session.add(Organization(slug="xyz", name="XYZ Board", aliases=["xyz board"]))
    session.flush()
    clash = resolve_organization(session, "XYZ Authority (XYZ)", kind="job", source="nts")
    assert first.slug == "spl" and other.id != first.id
    assert clash.slug == "xyz-2" and clash.name == "XYZ Authority"


def test_reference_data_sync_is_idempotent(session):
    sync_reference_data(session)
    sync_reference_data(session)
    session.flush()
    assert session.scalar(select(func.count()).select_from(Organization).where(Organization.curated)) == len(ORGANIZATIONS)
    assert session.scalar(select(func.count()).select_from(HubSlug)) == len(HUBS)
    hyd = session.get(HubSlug, "hyderabad-sindh")
    assert hyd.matches == ["Hyderabad"] and hyd.province == "Sindh" and "karachi" in hyd.nearby


def test_backfill_enriches_old_rows_only(session):
    listing = upsert_listing(session, record("record_job_wcla")).listing
    listing.slug = None
    listing.organization_id = None
    session.flush()
    assert backfill_listings(session) == 1
    assert listing.slug and listing.organization_id
    assert backfill_listings(session) == 0


def test_enrich_listing_is_idempotent(session):
    listing = upsert_listing(session, record("record_admission_uom")).listing
    slug, org_id = listing.slug, listing.organization_id
    enrich_listing(session, listing)
    assert (listing.slug, listing.organization_id) == (slug, org_id)
    assert listing.slug == "university-of-malakand-chakdara-dir-lower-admission-2026"
    assert session.scalar(select(func.count()).select_from(Listing)) == 1
