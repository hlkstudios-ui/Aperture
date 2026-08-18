"""Persist explicit optional analytics consent."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "4d91c8a7f2e0"
down_revision: str | Sequence[str] | None = "d2b94a1786ef"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "profile_preferences",
        sa.Column("analytics_enabled", sa.Boolean(), server_default="false", nullable=False),
    )
    op.add_column(
        "profile_preferences",
        sa.Column("consent_updated_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("profile_preferences", "consent_updated_at")
    op.drop_column("profile_preferences", "analytics_enabled")
