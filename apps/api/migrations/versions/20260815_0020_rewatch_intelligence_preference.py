"""rewatch intelligence preference

Revision ID: 20260815_0020
Revises: 20260815_0019
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0020"
down_revision: str | Sequence[str] | None = "20260815_0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "profile_preferences",
        sa.Column(
            "rewatch_intelligence_enabled",
            sa.Boolean(),
            server_default="true",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("profile_preferences", "rewatch_intelligence_enabled")
