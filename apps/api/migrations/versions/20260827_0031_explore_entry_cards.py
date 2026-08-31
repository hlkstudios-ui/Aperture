"""Add ordered catalog cards to Studio-managed Explore entries.

Revision ID: 20260827_0031
Revises: 20260827_0030
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0031"
down_revision: str | Sequence[str] | None = "20260827_0030"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explore_entry_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "entry_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("explore_entries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "movie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "series_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("series.id", ondelete="CASCADE"),
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_explore_entry_cards_exactly_one_title",
        ),
        sa.CheckConstraint("position >= 0", name="ck_explore_entry_cards_position"),
        sa.UniqueConstraint("entry_id", "position", name="uq_explore_entry_cards_position"),
        sa.UniqueConstraint("entry_id", "movie_id", name="uq_explore_entry_cards_movie"),
        sa.UniqueConstraint("entry_id", "series_id", name="uq_explore_entry_cards_series"),
    )
    op.create_index(
        "ix_explore_entry_cards_entry_id",
        "explore_entry_cards",
        ["entry_id"],
    )
    op.create_index(
        "ix_explore_entry_cards_movie_id",
        "explore_entry_cards",
        ["movie_id"],
    )
    op.create_index(
        "ix_explore_entry_cards_series_id",
        "explore_entry_cards",
        ["series_id"],
    )


def downgrade() -> None:
    op.drop_table("explore_entry_cards")
