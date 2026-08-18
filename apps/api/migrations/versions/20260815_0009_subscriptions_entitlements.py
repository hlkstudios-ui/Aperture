"""subscription, entitlement, and payment reference architecture

Revision ID: 20260815_0009
Revises: 20260815_0008
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0009"
down_revision: str | None = "20260815_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def enum(name: str, *values: str):
    source = postgresql.ENUM(*values, name=name)
    source.create(op.get_bind(), checkfirst=True)
    return postgresql.ENUM(*values, name=name, create_type=False)


def upgrade() -> None:
    billing_interval = enum("billing_interval", "month", "year")
    subscription_status = enum(
        "subscription_status",
        "incomplete",
        "trialing",
        "active",
        "past_due",
        "canceled",
        "expired",
    )
    payment_status = enum("payment_status", "pending", "succeeded", "failed", "refunded")
    op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), server_default="CAD", nullable=False),
        sa.Column("interval", billing_interval, nullable=False),
        sa.Column("max_streams", sa.Integer(), server_default="1", nullable=False),
        sa.Column("max_resolution", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("price_cents >= 0", name="ck_plans_price_nonnegative"),
        sa.CheckConstraint("max_streams > 0", name="ck_plans_max_streams_positive"),
    )
    op.create_index("ix_plans_code", "plans", ["code"], unique=True)
    op.create_index("ix_plans_is_active", "plans", ["is_active"])
    op.bulk_insert(
        sa.table(
            "plans",
            sa.column("id", postgresql.UUID(as_uuid=True)),
            sa.column("code"),
            sa.column("name"),
            sa.column("description"),
            sa.column("price_cents"),
            sa.column("currency"),
            sa.column("interval"),
            sa.column("max_streams"),
            sa.column("max_resolution"),
            sa.column("is_active"),
        ),
        [
            {
                "id": "10000000-0000-4000-8000-000000000001",
                "code": "essential-monthly",
                "name": "Essential",
                "description": "One stream with the complete film catalog.",
                "price_cents": 999,
                "currency": "CAD",
                "interval": "month",
                "max_streams": 1,
                "max_resolution": "1080p",
                "is_active": True,
            },
            {
                "id": "10000000-0000-4000-8000-000000000002",
                "code": "cinephile-monthly",
                "name": "Cinephile",
                "description": "Four streams and highest available quality.",
                "price_cents": 1499,
                "currency": "CAD",
                "interval": "month",
                "max_streams": 4,
                "max_resolution": "4K",
                "is_active": True,
            },
        ],
    )
    op.create_table(
        "subscriptions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plan_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plans.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("status", subscription_status, nullable=False),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("provider_customer_ref", sa.String(255)),
        sa.Column("provider_subscription_ref", sa.String(255), unique=True),
        sa.Column("current_period_start", sa.DateTime(timezone=True)),
        sa.Column("current_period_end", sa.DateTime(timezone=True)),
        sa.Column("cancel_at_period_end", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("canceled_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL OR "
            "current_period_end > current_period_start",
            name="ck_subscriptions_period",
        ),
    )
    op.create_index("ix_subscriptions_status", "subscriptions", ["status"])
    op.create_index("ix_subscriptions_user_status", "subscriptions", ["user_id", "status"])
    op.create_index(
        "ix_subscriptions_provider_customer_ref", "subscriptions", ["provider_customer_ref"]
    )
    op.create_table(
        "payment_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(64), nullable=False),
        sa.Column("external_reference", sa.String(255), nullable=False, unique=True),
        sa.Column("status", payment_status, nullable=False),
        sa.Column("amount_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("amount_cents >= 0", name="ck_payments_amount_nonnegative"),
    )
    op.create_index(
        "ix_payment_references_subscription_id", "payment_references", ["subscription_id"]
    )
    op.create_index("ix_payment_references_occurred_at", "payment_references", ["occurred_at"])
    op.create_table(
        "entitlements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "subscription_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("subscriptions.id", ondelete="CASCADE"),
        ),
        sa.Column("key", sa.String(100), nullable=False),
        sa.Column("value", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("source", sa.String(64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_entitlements_window",
        ),
    )
    op.create_index("ix_entitlements_user_key", "entitlements", ["user_id", "key"])


def downgrade() -> None:
    op.drop_table("entitlements")
    op.drop_table("payment_references")
    op.drop_table("subscriptions")
    op.drop_table("plans")
    for name in ("payment_status", "subscription_status", "billing_interval"):
        postgresql.ENUM(name=name).drop(op.get_bind(), checkfirst=True)
