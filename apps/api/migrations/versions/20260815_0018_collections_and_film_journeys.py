"""collections and film journeys

Revision ID: 20260815_0018
Revises: 20260815_0017
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0018"
down_revision: str | Sequence[str] | None = "20260815_0017"
branch_labels = None
depends_on = None

uuid = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    collection_kind = postgresql.ENUM(
        "editorial",
        "user_list",
        "franchise",
        "award",
        "director",
        "actor",
        "country",
        "decade",
        "genre",
        "movement",
        "seasonal",
        "themed",
        name="collection_kind",
        create_type=False,
    )
    curation_status = postgresql.ENUM(
        "draft", "published", "archived", name="curation_status", create_type=False
    )
    collection_kind.create(op.get_bind(), checkfirst=True)
    curation_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "collections",
        sa.Column("id", uuid, nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), server_default="", nullable=False),
        sa.Column("kind", collection_kind, nullable=False),
        sa.Column("status", curation_status, nullable=False),
        sa.Column("owner_profile_id", uuid),
        sa.Column("created_by_admin_id", uuid),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(kind = 'user_list') = (owner_profile_id IS NOT NULL)",
            name="ck_collections_owner_kind",
        ),
        sa.ForeignKeyConstraint(["owner_profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_collections_slug", "collections", ["slug"], unique=True)
    op.create_index("ix_collections_kind", "collections", ["kind"])
    op.create_index("ix_collections_status", "collections", ["status"])
    op.create_index("ix_collections_owner_profile_id", "collections", ["owner_profile_id"])
    op.create_table(
        "collection_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("collection_id", uuid, nullable=False),
        sa.Column("movie_id", uuid),
        sa.Column("series_id", uuid),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("note", sa.Text()),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_collection_items_one_title",
        ),
        sa.ForeignKeyConstraint(["collection_id"], ["collections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("collection_id", "position", name="uq_collection_items_position"),
        sa.UniqueConstraint("collection_id", "movie_id", name="uq_collection_items_movie"),
        sa.UniqueConstraint("collection_id", "series_id", name="uq_collection_items_series"),
    )
    op.create_index("ix_collection_items_collection_id", "collection_items", ["collection_id"])
    op.create_table(
        "journeys",
        sa.Column("id", uuid, nullable=False),
        sa.Column("slug", sa.String(200), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", curation_status, nullable=False),
        sa.Column("created_by_admin_id", uuid),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["created_by_admin_id"], ["admins.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_journeys_slug", "journeys", ["slug"], unique=True)
    op.create_index("ix_journeys_status", "journeys", ["status"])
    op.create_table(
        "journey_chapters",
        sa.Column("id", uuid, nullable=False),
        sa.Column("journey_id", uuid, nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("introduction", sa.Text()),
        sa.ForeignKeyConstraint(["journey_id"], ["journeys.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("journey_id", "position", name="uq_journey_chapters_position"),
    )
    op.create_index("ix_journey_chapters_journey_id", "journey_chapters", ["journey_id"])
    op.create_table(
        "journey_items",
        sa.Column("id", uuid, nullable=False),
        sa.Column("chapter_id", uuid, nullable=False),
        sa.Column("movie_id", uuid),
        sa.Column("series_id", uuid),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("introduction", sa.Text()),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_journey_items_one_title",
        ),
        sa.ForeignKeyConstraint(["chapter_id"], ["journey_chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["movie_id"], ["movies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chapter_id", "position", name="uq_journey_items_position"),
    )
    op.create_index("ix_journey_items_chapter_id", "journey_items", ["chapter_id"])
    op.create_table(
        "journey_progress",
        sa.Column("id", uuid, nullable=False),
        sa.Column("profile_id", uuid, nullable=False),
        sa.Column("journey_item_id", uuid, nullable=False),
        sa.Column(
            "completed_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["journey_item_id"], ["journey_items.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "profile_id", "journey_item_id", name="uq_journey_progress_profile_item"
        ),
    )
    op.create_index("ix_journey_progress_profile_id", "journey_progress", ["profile_id"])
    op.create_index("ix_journey_progress_journey_item_id", "journey_progress", ["journey_item_id"])


def downgrade() -> None:
    op.drop_table("journey_progress")
    op.drop_table("journey_items")
    op.drop_table("journey_chapters")
    op.drop_table("journeys")
    op.drop_table("collection_items")
    op.drop_table("collections")
    postgresql.ENUM(name="curation_status").drop(op.get_bind(), checkfirst=True)
    postgresql.ENUM(name="collection_kind").drop(op.get_bind(), checkfirst=True)
