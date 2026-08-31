"""Add the isolated-cell viewer payment connection boundary.

Revision ID: 20260831_0034
Revises: 20260831_0033
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0034"
down_revision: str | Sequence[str] | None = "20260831_0033"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "viewer_payment_connections",
        sa.Column("id", sa.Integer(), server_default="1", primary_key=True),
        sa.Column(
            "owner_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(32), server_default="disabled", nullable=False),
        sa.Column("access_mode", sa.String(32), server_default="free", nullable=False),
        sa.Column("stripe_connected_account_id", sa.String(255)),
        sa.Column("livemode", sa.Boolean()),
        sa.Column("details_submitted", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("charges_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("payouts_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("requirements_due", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("id = 1", name="ck_viewer_payment_connection_singleton"),
        sa.CheckConstraint(
            "provider IN ('disabled', 'stripe_connect')",
            name="ck_viewer_payment_connection_provider",
        ),
        sa.CheckConstraint(
            "access_mode IN ('free', 'subscription_required')",
            name="ck_viewer_payment_connection_access_mode",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_viewer_payment_connection_revision"),
        sa.CheckConstraint(
            "access_mode <> 'subscription_required' OR charges_enabled",
            name="ck_viewer_payment_connection_subscription_requires_charges",
        ),
        sa.CheckConstraint(
            "provider <> 'disabled' OR "
            "(stripe_connected_account_id IS NULL AND livemode IS NULL AND "
            "NOT details_submitted AND NOT charges_enabled AND NOT payouts_enabled)",
            name="ck_viewer_payment_connection_disabled_state",
        ),
        sa.CheckConstraint(
            "provider <> 'stripe_connect' OR stripe_connected_account_id IS NOT NULL",
            name="ck_viewer_payment_connection_stripe_account",
        ),
        sa.UniqueConstraint("owner_admin_id"),
        sa.UniqueConstraint("stripe_connected_account_id"),
    )
    op.create_index(
        "ix_viewer_payment_connections_owner_admin_id",
        "viewer_payment_connections",
        ["owner_admin_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_viewer_payment_connections_owner_admin_id",
        table_name="viewer_payment_connections",
    )
    op.drop_table("viewer_payment_connections")
