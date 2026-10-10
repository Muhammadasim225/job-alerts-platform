"""data model v2: organizations, hubs, slugs, deadline history, saved listings, events

Adds what the website needs: canonical organizations and hub slugs, per-listing slug,
apply URL and deadline time, per-post education levels and gender, the deadline-change
history, saved listings (reminders) and the listing_events outbox. Existing rows are
filled in by shared.migrate after the upgrade (reference data + listing enrichment).

Revision ID: 4b8e2f6a1c90
Revises: 7c1d2e9a4b10
Create Date: 2026-10-10 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "4b8e2f6a1c90"
down_revision: str | Sequence[str] | None = "7c1d2e9a4b10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("short_name", sa.String(40), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False, server_default="org"),
        sa.Column("aliases", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("official_url", sa.Text(), nullable=True),
        sa.Column("curated", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index("ix_organizations_aliases", "organizations", ["aliases"], postgresql_using="gin")

    op.create_table(
        "hub_slugs",
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("matches", postgresql.ARRAY(sa.Text()), nullable=False, server_default="{}"),
        sa.Column("province", sa.Text(), nullable=True),
        sa.Column("nearby", postgresql.ARRAY(sa.String(80)), nullable=False, server_default="{}"),
        sa.PrimaryKeyConstraint("slug"),
    )

    op.add_column("listings", sa.Column("organization_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "listings_organization_id_fkey", "listings", "organizations", ["organization_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_listings_organization_id", "listings", ["organization_id"])
    op.add_column("listings", sa.Column("slug", sa.String(100), nullable=True))
    op.add_column("listings", sa.Column("apply_url", sa.Text(), nullable=True))
    op.add_column("listings", sa.Column("last_date_at", sa.DateTime(timezone=True), nullable=True))

    op.add_column(
        "vacancies",
        sa.Column("education_levels", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
    )
    op.add_column("vacancies", sa.Column("gender", sa.String(10), nullable=True))

    op.create_table(
        "deadline_changes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("old_date", sa.Date(), nullable=True),
        sa.Column("new_date", sa.Date(), nullable=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deadline_changes_listing_id", "deadline_changes", ["listing_id"])

    op.create_table(
        "saved_listings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("remind", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "listing_id", name="uq_saved_user_listing"),
    )
    op.create_index("ix_saved_listings_user_id", "saved_listings", ["user_id"])
    op.create_index("ix_saved_listings_listing_id", "saved_listings", ["listing_id"])

    op.create_table(
        "listing_events",
        sa.Column("id", sa.BigInteger(), nullable=False),
        sa.Column("listing_id", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["listing_id"], ["listings.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_listing_events_listing_id", "listing_events", ["listing_id"])
    op.create_index(
        "ix_listing_events_unprocessed", "listing_events", ["id"], postgresql_where=sa.text("processed_at IS NULL")
    )


def downgrade() -> None:
    op.drop_table("listing_events")
    op.drop_table("saved_listings")
    op.drop_table("deadline_changes")
    op.drop_column("vacancies", "gender")
    op.drop_column("vacancies", "education_levels")
    op.drop_column("listings", "last_date_at")
    op.drop_column("listings", "apply_url")
    op.drop_column("listings", "slug")
    op.drop_index("ix_listings_organization_id", table_name="listings")
    op.drop_constraint("listings_organization_id_fkey", "listings", type_="foreignkey")
    op.drop_column("listings", "organization_id")
    op.drop_table("hub_slugs")
    op.drop_index("ix_organizations_aliases", table_name="organizations")
    op.drop_table("organizations")
