"""verified title relationships

Revision ID: 20260815_0019
Revises: 20260815_0018
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0019"
down_revision: str | Sequence[str] | None = "20260815_0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    relationship_kind = postgresql.ENUM(
        "sequel",
        "prequel",
        "remake",
        "remade_as",
        "adaptation",
        "source_material",
        "influenced_by",
        "influenced",
        "companion",
        name="title_relationship_kind",
        create_type=False,
    )
    relationship_kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "title_relationships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_movie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("target_movie_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", relationship_kind, nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("manually_verified", sa.Boolean(), server_default="false", nullable=False),
        sa.CheckConstraint(
            "source_movie_id <> target_movie_id", name="ck_title_relationships_distinct"
        ),
        sa.ForeignKeyConstraint(["source_movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_movie_id",
            "target_movie_id",
            "kind",
            name="uq_title_relationships_fact",
        ),
    )
    op.create_index(
        "ix_title_relationships_source_movie_id",
        "title_relationships",
        ["source_movie_id"],
    )
    op.create_index(
        "ix_title_relationships_target_movie_id",
        "title_relationships",
        ["target_movie_id"],
    )
    op.create_index("ix_title_relationships_kind", "title_relationships", ["kind"])


def downgrade() -> None:
    op.drop_table("title_relationships")
    postgresql.ENUM(name="title_relationship_kind").drop(op.get_bind(), checkfirst=True)
