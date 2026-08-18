"""Track externally reported ongoing series status.

Revision ID: 20260817_0023
Revises: 20260817_0022
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0023"
down_revision: str | Sequence[str] | None = "20260817_0022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("series", sa.Column("is_ongoing", sa.Boolean(), nullable=True))
    op.create_index("ix_series_is_ongoing", "series", ["is_ongoing"])


def downgrade() -> None:
    op.drop_index("ix_series_is_ongoing", table_name="series")
    op.drop_column("series", "is_ongoing")
