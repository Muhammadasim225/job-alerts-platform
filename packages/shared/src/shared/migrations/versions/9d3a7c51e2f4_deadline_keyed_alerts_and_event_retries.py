"""deadline-keyed alerts and event retries

Alerts become unique per (user, listing, type, deadline) so a reminder for the new
last date can go out after an extension. listing_events get retry bookkeeping
(attempts, next_attempt_at, last_error) for the outbox worker's backoff.

Revision ID: 9d3a7c51e2f4
Revises: 4b8e2f6a1c90
Create Date: 2026-10-10 21:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9d3a7c51e2f4"
down_revision: str | Sequence[str] | None = "4b8e2f6a1c90"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("alerts", sa.Column("deadline", sa.Date(), nullable=True))
    # Existing reminders were for the listing's current last date
    op.execute(
        "UPDATE alerts a SET deadline = l.last_date FROM listings l "
        "WHERE l.id = a.listing_id AND a.alert_type = 'deadline_reminder'"
    )
    op.drop_constraint("uq_alert_user_listing_type", "alerts", type_="unique")
    op.execute(
        "ALTER TABLE alerts ADD CONSTRAINT uq_alert_user_listing_type_deadline "
        "UNIQUE NULLS NOT DISTINCT (user_id, listing_id, alert_type, deadline)"
    )

    op.add_column("listing_events", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column(
        "listing_events",
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.add_column("listing_events", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("listing_events", "last_error")
    op.drop_column("listing_events", "next_attempt_at")
    op.drop_column("listing_events", "attempts")
    op.drop_constraint("uq_alert_user_listing_type_deadline", "alerts", type_="unique")
    op.execute("DELETE FROM alerts a USING alerts b WHERE a.id > b.id AND a.user_id = b.user_id "
               "AND a.listing_id = b.listing_id AND a.alert_type = b.alert_type")
    op.create_unique_constraint("uq_alert_user_listing_type", "alerts", ["user_id", "listing_id", "alert_type"])
    op.drop_column("alerts", "deadline")
