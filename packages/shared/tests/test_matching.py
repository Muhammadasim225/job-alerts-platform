"""Matching and alert queueing on real records (WCLA job, University of Malakand admission)."""

import json
from datetime import date
from pathlib import Path

from sqlalchemy import func, select

from shared.matching import match_listing, matches_for_user, queue_alerts_for_listing, queue_deadline_reminders
from shared.models import Alert, Preference, User
from shared.repository import upsert_listing

FIXTURES = Path(__file__).parent / "fixtures"
TODAY = date(2026, 9, 20)  # before the WCLA (28 Sep) and UOM (5 Oct) deadlines


def store(session, name, **overrides):
    rec = json.loads((FIXTURES / f"{name}.json").read_text(encoding="utf8"))
    rec.update({"status": "open", **overrides})
    return upsert_listing(session, rec).listing


def user(session, chat_id, **pref):
    u = User(telegram_chat_id=chat_id, preference=Preference(**pref))
    session.add(u)
    session.flush()
    return u


def names(listing, m):
    return [v.post_name for v in listing.vacancies if v.id in m.vacancy_ids]


def test_it_graduate_in_punjab_gets_computer_operator_only(session):
    wcla = store(session, "record_job_wcla")
    pref = Preference(kinds=["job"], fields=["it"], provinces=["Punjab"], age=22)
    m = match_listing(wcla, pref, TODAY)
    assert names(wcla, m) == ["Computer Operator"]


def test_bps_range_filters_posts(session):
    wcla = store(session, "record_job_wcla")
    assert names(wcla, match_listing(wcla, Preference(kinds=["job"], bps_min=16, bps_max=20), TODAY)) == ["Deputy Director (Design)"]
    assert match_listing(wcla, Preference(kinds=["job"], bps_min=1, bps_max=10), TODAY) is None


def test_age_and_experience_limits(session):
    wcla = store(session, "record_job_wcla")
    # 30 years old: too old for Computer Operator (18-25), fine for Deputy Director (26-40)
    assert names(wcla, match_listing(wcla, Preference(kinds=["job"], age=30), TODAY)) == ["Deputy Director (Design)"]
    # Fresh graduate: Deputy Director needs five years
    fresh = Preference(kinds=["job"], age=26, max_experience_years=0)
    assert match_listing(wcla, fresh, TODAY) is None  # 26 is too old for Computer Operator too


def test_province_kind_and_deadline(session):
    wcla = store(session, "record_job_wcla")
    assert match_listing(wcla, Preference(kinds=["job"], provinces=["Sindh"]), TODAY) is None
    assert match_listing(wcla, Preference(kinds=["admission"]), TODAY) is None
    assert match_listing(wcla, Preference(kinds=["job"]), date(2026, 9, 29)) is None  # past last date


def test_keyword_matches_post_name(session):
    wcla = store(session, "record_job_wcla")
    assert names(wcla, match_listing(wcla, Preference(kinds=["job"], keywords=["operator"]), TODAY)) == ["Computer Operator"]


def test_admission_programmes_by_level_and_subject(session):
    uom = store(session, "record_admission_uom")
    phd_cs = Preference(kinds=["admission"], program_levels=["PhD"], keywords=["computer"])
    m = match_listing(uom, phd_cs, TODAY)
    assert [p.name for p in uom.programs if p.id in m.program_ids] == ["Computer Science (PhD Program)"]
    mphil = Preference(kinds=["admission"], program_levels=["MPhil"], keywords=["geology"])
    m = match_listing(uom, mphil, TODAY)
    assert [p.name for p in uom.programs if p.id in m.program_ids] == ["GAT-C (MS/ MPhil Program)"]


def test_alerts_are_queued_once(session):
    wcla = store(session, "record_job_wcla")
    it_user = user(session, 1001, kinds=["job"], fields=["it"])
    user(session, 1002, kinds=["admission"])  # does not want jobs
    assert queue_alerts_for_listing(session, wcla.id, today=TODAY) == 1
    assert queue_alerts_for_listing(session, wcla.id, today=TODAY) == 0  # re-run: no duplicate
    alert = session.scalar(select(Alert).where(Alert.user_id == it_user.id))
    assert alert.status == "pending" and len(alert.matched_vacancy_ids) == 1


def test_inactive_users_get_nothing(session):
    wcla = store(session, "record_job_wcla")
    u = user(session, 1003, kinds=["job"])
    u.is_active = False
    session.flush()
    assert queue_alerts_for_listing(session, wcla.id, today=TODAY) == 0


def test_matches_for_user_lists_live_listings(session):
    store(session, "record_job_wcla")
    store(session, "record_admission_uom")
    u = user(session, 1004, kinds=["job", "admission"], keywords=["computer"])
    got = matches_for_user(session, u, today=TODAY)
    assert len(got) == 2  # Computer Operator post + Computer Science programmes


def test_deadline_reminder_only_for_users_alerted_before(session):
    wcla = store(session, "record_job_wcla")  # last date 2026-09-28
    u = user(session, 1005, kinds=["job"])
    queue_alerts_for_listing(session, wcla.id, today=TODAY)
    session.execute(Alert.__table__.update().values(status="sent"))
    user(session, 1006, kinds=["job"])  # joined later, never alerted

    assert queue_deadline_reminders(session, days_before=2, today=date(2026, 9, 26)) == 1
    assert queue_deadline_reminders(session, days_before=2, today=date(2026, 9, 26)) == 0
    reminders = session.scalar(select(func.count()).select_from(Alert).where(Alert.alert_type == "deadline_reminder"))
    assert reminders == 1
    assert session.scalar(select(Alert.user_id).where(Alert.alert_type == "deadline_reminder")) == u.id
