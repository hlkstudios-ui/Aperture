"""Add display stills for imported episodes.

Revision ID: 20260817_0024
Revises: 20260817_0023
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0024"
down_revision: str | Sequence[str] | None = "20260817_0023"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("episodes", sa.Column("still_url", sa.String(1000), nullable=True))


def downgrade() -> None:
    op.drop_column("episodes", "still_url")
