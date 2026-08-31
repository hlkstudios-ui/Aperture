"""Add Studio-managed Explore entries.

Revision ID: 20260827_0030
Revises: 20260823_0029
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260827_0030"
down_revision: str | Sequence[str] | None = "20260823_0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "explore_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("label", sa.String(64), nullable=False),
        sa.Column("description", sa.String(180), server_default="", nullable=False),
        sa.Column("icon", sa.String(16), server_default="↗", nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "criteria",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
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
        sa.CheckConstraint("position >= 0", name="ck_explore_entries_position"),
        sa.UniqueConstraint("position", name="uq_explore_entries_position"),
    )
    op.create_index(
        "uq_explore_entries_label_ci",
        "explore_entries",
        [sa.text("lower(label)")],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("explore_entries")
