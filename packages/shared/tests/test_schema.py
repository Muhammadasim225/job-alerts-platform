from datetime import date

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from shared.models import Alert, Listing, Preference, User, Vacancy


def test_migrations_create_all_tables(session):
    tables = set(inspect(session.connection()).get_table_names())
    assert {
        "listings",
        "vacancies",
        "programs",
        "attachments",
        "users",
        "preferences",
        "alerts",
        "auth_sessions",
        "push_subscriptions",
        "deliveries",
    } <= tables


def _listing(**kw):
    return Listing(
        source="nts",
        external_id=kw.pop("external_id", "portal-1"),
        url="https://x",
        status="open",
        kind="job",
        title="Some Authority",
        **kw,
    )


def test_listing_with_vacancies_round_trip(session):
    listing = _listing(last_date=date(2026, 10, 8), provinces=["Punjab"], advert_facts={"session": "2026-27"})
    listing.vacancies.append(
        Vacancy(
            position=1,
            post_name="Computer Operator",
            bps=[12],
            bps_min=12,
            bps_max=12,
            test_syllabus=[{"subject": "IT", "weight_percent": 20}],
        )
    )
    session.add(listing)
    session.flush()
    got = session.get(Listing, listing.id)
    assert got.vacancies[0].bps == [12] and got.provinces == ["Punjab"]
    assert got.advert_facts["session"] == "2026-27"


def test_listing_external_id_is_unique_per_source(session):
    session.add(_listing())
    session.flush()
    session.add(_listing())
    with pytest.raises(IntegrityError):
        session.flush()


def test_alert_cannot_be_queued_twice(session):
    user = User(email="a@example.com", preference=Preference())
    listing = _listing()
    session.add_all([user, listing])
    session.flush()
    session.add(Alert(user_id=user.id, listing_id=listing.id, alert_type="new"))
    session.flush()
    session.add(Alert(user_id=user.id, listing_id=listing.id, alert_type="new"))
    with pytest.raises(IntegrityError):
        session.flush()


def test_preference_defaults(session):
    user = User(email="b@example.com", preference=Preference())
    session.add(user)
    session.flush()
    assert user.preference.kinds == ["job"] and user.preference.fields == []


def test_email_is_unique(session):
    session.add(User(email="same@example.com"))
    session.flush()
    session.add(User(email="same@example.com"))
    with pytest.raises(IntegrityError):
        session.flush()
