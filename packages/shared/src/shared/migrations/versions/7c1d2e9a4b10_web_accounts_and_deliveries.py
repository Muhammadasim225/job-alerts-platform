"""web accounts and deliveries

Users move from Telegram chats to website accounts (email login); alerts become an
inbox; notifications go out as deliveries (email digest, Web Push).

Revision ID: 7c1d2e9a4b10
Revises: 23f75cceb59e
Create Date: 2026-10-05 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "7c1d2e9a4b10"
down_revision: str | Sequence[str] | None = "23f75cceb59e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # users: email identity instead of a Telegram chat. Rows from the Telegram era (dev
    # test users only) get an undeliverable placeholder (.invalid is a reserved TLD).
    op.add_column("users", sa.Column("email", sa.String(254), nullable=True))
    op.execute("UPDATE users SET email = 'legacy-' || id || '@users.invalid'")
    op.alter_column("users", "email", nullable=False)
    op.create_unique_constraint("users_email_key", "users", ["email"])
    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("email_alerts", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("push_alerts", sa.Boolean(), server_default="true", nullable=False))
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_column("users", "telegram_chat_id")

    # alerts: inbox read state; the per-alert claim columns move to deliveries.
    # Alerts claimed by the old outbox ("sending"/"failed") go back to pending.
    op.add_column("alerts", sa.Column("read_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE alerts SET status = 'pending' WHERE status IN ('sending', 'failed')")
    op.drop_column("alerts", "claimed_at")
    op.drop_column("alerts", "attempts")
    op.create_index("ix_alerts_user_created", "alerts", ["user_id", "created_at"])

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])

    op.create_table(
        "push_subscriptions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.String(200), nullable=False),
        sa.Column("auth", sa.String(100), nullable=False),
        sa.Column("user_agent", sa.String(200), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("endpoint"),
    )
    op.create_index("ix_push_subscriptions_user_id", "push_subscriptions", ["user_id"])

    op.create_table(
        "deliveries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("alert_ids", postgresql.ARRAY(sa.Integer()), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_deliveries_user_id", "deliveries", ["user_id"])
    op.create_index("ix_deliveries_due", "deliveries", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_table("deliveries")
    op.drop_table("push_subscriptions")
    op.drop_table("auth_sessions")

    op.drop_index("ix_alerts_user_created", table_name="alerts")
    op.add_column("alerts", sa.Column("attempts", sa.Integer(), server_default="0", nullable=False))
    op.add_column("alerts", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_column("alerts", "read_at")

    # Web accounts have no Telegram chat: they cannot be carried back
    op.execute("DELETE FROM users")
    op.add_column("users", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=False))
    op.create_unique_constraint("users_telegram_chat_id_key", "users", ["telegram_chat_id"])
    for col in ("last_login_at", "push_alerts", "email_alerts", "email_verified_at"):
        op.drop_column("users", col)
    op.drop_constraint("users_email_key", "users", type_="unique")
    op.drop_column("users", "email")
