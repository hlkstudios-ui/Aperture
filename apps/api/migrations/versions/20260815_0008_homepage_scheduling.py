"""homepage curation and catalog scheduling

Revision ID: 20260815_0008
Revises: 20260815_0007
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0008"
down_revision: str | None = "20260815_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _schedule_columns(table: str) -> None:
    for name in ("publish_at", "unpublish_at", "rights_start_at", "rights_end_at"):
        op.add_column(table, sa.Column(name, sa.DateTime(timezone=True)))
        op.create_index(f"ix_{table}_{name}", table, [name])


def upgrade() -> None:
    _schedule_columns("movies")
    _schedule_columns("series")
    op.create_check_constraint(
        "ck_movies_rights_window",
        "movies",
        "rights_start_at IS NULL OR rights_end_at IS NULL OR rights_end_at > rights_start_at",
    )
    op.create_check_constraint(
        "ck_movies_publish_window",
        "movies",
        "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
    )
    op.create_check_constraint(
        "ck_series_rights_window",
        "series",
        "rights_start_at IS NULL OR rights_end_at IS NULL OR rights_end_at > rights_start_at",
    )
    op.create_check_constraint(
        "ck_series_publish_window",
        "series",
        "publish_at IS NULL OR unpublish_at IS NULL OR unpublish_at > publish_at",
    )

    homepage_source_type = postgresql.ENUM(
        "pinned", "latest_movies", "latest_series", "mixed", name="homepage_source"
    )
    homepage_source_type.create(op.get_bind(), checkfirst=True)
    homepage_source = postgresql.ENUM(
        "pinned",
        "latest_movies",
        "latest_series",
        "mixed",
        name="homepage_source",
        create_type=False,
    )
    op.create_table(
        "homepage_configurations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "draft_hero_movie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("movies.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "draft_hero_series_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("series.id", ondelete="SET NULL"),
        ),
        sa.Column("published_snapshot", sa.JSON()),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(draft_hero_movie_id IS NOT NULL)::integer + "
            "(draft_hero_series_id IS NOT NULL)::integer <= 1",
            name="ck_homepage_configurations_one_draft_hero",
        ),
    )
    op.create_table(
        "homepage_rails",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "configuration_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("homepage_configurations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("eyebrow", sa.String(80)),
        sa.Column("source", homepage_source, server_default="pinned", nullable=False),
        sa.Column("query", sa.String(100)),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True)),
        sa.Column("ends_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_homepage_rails_schedule",
        ),
        sa.UniqueConstraint("configuration_id", "position", name="uq_homepage_rails_position"),
    )
    op.create_index("ix_homepage_rails_configuration_id", "homepage_rails", ["configuration_id"])
    op.create_index("ix_homepage_rails_starts_at", "homepage_rails", ["starts_at"])
    op.create_index("ix_homepage_rails_ends_at", "homepage_rails", ["ends_at"])
    op.create_table(
        "homepage_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "rail_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("homepage_rails.id", ondelete="CASCADE"),
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
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_homepage_items_exactly_one_title",
        ),
        sa.UniqueConstraint("rail_id", "position", name="uq_homepage_items_position"),
        sa.UniqueConstraint("rail_id", "movie_id", name="uq_homepage_items_movie"),
        sa.UniqueConstraint("rail_id", "series_id", name="uq_homepage_items_series"),
    )
    op.create_index("ix_homepage_items_rail_id", "homepage_items", ["rail_id"])


def downgrade() -> None:
    op.drop_table("homepage_items")
    op.drop_table("homepage_rails")
    op.drop_table("homepage_configurations")
    postgresql.ENUM(name="homepage_source").drop(op.get_bind(), checkfirst=True)
    for table in ("series", "movies"):
        op.drop_constraint(f"ck_{table}_publish_window", table, type_="check")
        op.drop_constraint(f"ck_{table}_rights_window", table, type_="check")
        for name in ("rights_end_at", "rights_start_at", "unpublish_at", "publish_at"):
            op.drop_index(f"ix_{table}_{name}", table_name=table)
            op.drop_column(table, name)
