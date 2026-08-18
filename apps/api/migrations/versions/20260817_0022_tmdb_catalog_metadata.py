"""Add external catalog provenance and display artwork.

Revision ID: 20260817_0022
Revises: b7e4c91d2a60
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260817_0022"
down_revision: str | Sequence[str] | None = "b7e4c91d2a60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("movies", "series"):
        op.add_column(table, sa.Column("metadata_provider", sa.String(32), nullable=True))
        op.add_column(table, sa.Column("external_id", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("poster_url", sa.String(1000), nullable=True))
        op.add_column(table, sa.Column("backdrop_url", sa.String(1000), nullable=True))
        op.create_index(f"ix_{table}_metadata_provider", table, ["metadata_provider"])
        op.create_index(f"ix_{table}_external_id", table, ["external_id"])
        op.create_index(
            f"uq_{table}_provider_external_id",
            table,
            ["metadata_provider", "external_id"],
            unique=True,
            postgresql_where=sa.text("metadata_provider IS NOT NULL AND external_id IS NOT NULL"),
        )


def downgrade() -> None:
    for table in ("series", "movies"):
        op.drop_index(f"uq_{table}_provider_external_id", table_name=table)
        op.drop_index(f"ix_{table}_external_id", table_name=table)
        op.drop_index(f"ix_{table}_metadata_provider", table_name=table)
        op.drop_column(table, "backdrop_url")
        op.drop_column(table, "poster_url")
        op.drop_column(table, "external_id")
        op.drop_column(table, "metadata_provider")
