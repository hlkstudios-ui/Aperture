"""billing webhook idempotency

Revision ID: 94f37d54a8bc
Revises: 7f3d28a8d301
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "94f37d54a8bc"
down_revision: str | None = "7f3d28a8d301"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "billing_webhook_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("external_event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=120), nullable=False),
        sa.Column(
            "processed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_event_id"),
    )
    op.create_index("ix_billing_webhook_events_provider", "billing_webhook_events", ["provider"])
    op.create_index(
        "ix_billing_webhook_events_event_type", "billing_webhook_events", ["event_type"]
    )


def downgrade() -> None:
    op.drop_index("ix_billing_webhook_events_event_type", table_name="billing_webhook_events")
    op.drop_index("ix_billing_webhook_events_provider", table_name="billing_webhook_events")
    op.drop_table("billing_webhook_events")
