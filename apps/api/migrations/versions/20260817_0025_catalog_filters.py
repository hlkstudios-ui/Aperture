"""Add filterable format and studio metadata.

Revision ID: 20260817_0025
Revises: 20260817_0024
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260817_0025"
down_revision: str | Sequence[str] | None = "20260817_0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("movies", "series"):
        op.add_column(table, sa.Column("content_format", sa.String(32), nullable=True))
        op.add_column(
            table,
            sa.Column(
                "studios",
                postgresql.JSONB(astext_type=sa.Text()),
                server_default=sa.text("'[]'::jsonb"),
                nullable=False,
            ),
        )
        op.create_index(f"ix_{table}_content_format", table, ["content_format"])


def downgrade() -> None:
    for table in ("series", "movies"):
        op.drop_index(f"ix_{table}_content_format", table_name=table)
        op.drop_column(table, "studios")
        op.drop_column(table, "content_format")
