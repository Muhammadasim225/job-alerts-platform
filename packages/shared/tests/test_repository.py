"""Upserts with real normalized records produced by the scraper."""

import copy
import json
from datetime import date
from pathlib import Path

from shared.repository import upsert_listing

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
