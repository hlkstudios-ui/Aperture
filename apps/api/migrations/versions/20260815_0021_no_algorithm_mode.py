"""profile homepage mode

Revision ID: 20260815_0021
Revises: 20260815_0020
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0021"
down_revision: str | Sequence[str] | None = "20260815_0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    homepage_mode = sa.Enum("curated", "no_algorithm", name="homepage_mode")
    homepage_mode.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "profile_preferences",
        sa.Column("homepage_mode", homepage_mode, server_default="curated", nullable=False),
    )


def downgrade() -> None:
    op.drop_column("profile_preferences", "homepage_mode")
    sa.Enum(name="homepage_mode").drop(op.get_bind(), checkfirst=True)
