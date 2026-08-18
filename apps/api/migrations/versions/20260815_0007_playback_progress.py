"""playback sources and profile progress

Revision ID: 20260815_0007
Revises: 20260815_0006
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0007"
down_revision: str | None = "20260815_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "playback_sources",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "processing_job_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("processing_jobs.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "movie_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("movies.id", ondelete="CASCADE"),
        ),
        sa.Column(
            "episode_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("episodes.id", ondelete="CASCADE"),
        ),
        sa.Column("intro_start_seconds", sa.Float()),
        sa.Column("intro_end_seconds", sa.Float()),
        sa.Column("recap_start_seconds", sa.Float()),
        sa.Column("recap_end_seconds", sa.Float()),
        sa.Column("credits_start_seconds", sa.Float()),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer = 1",
            name="ck_playback_sources_exactly_one_title",
        ),
        sa.CheckConstraint(
            "intro_start_seconds IS NULL OR "
            "(intro_start_seconds >= 0 AND intro_end_seconds > intro_start_seconds)",
            name="ck_playback_sources_intro_range",
        ),
        sa.CheckConstraint(
            "recap_start_seconds IS NULL OR "
            "(recap_start_seconds >= 0 AND recap_end_seconds > recap_start_seconds)",
            name="ck_playback_sources_recap_range",
        ),
        sa.CheckConstraint(
            "credits_start_seconds IS NULL OR credits_start_seconds >= 0",
            name="ck_playback_sources_credits_start",
        ),
        sa.UniqueConstraint("movie_id", name="uq_playback_sources_movie"),
        sa.UniqueConstraint("episode_id", name="uq_playback_sources_episode"),
    )
    op.create_table(
        "watch_progress",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "playback_source_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("playback_sources.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("position_seconds", sa.Float(), nullable=False),
        sa.Column("duration_seconds", sa.Float(), nullable=False),
        sa.Column("percentage", sa.Float(), nullable=False),
        sa.Column("completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "last_watched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("position_seconds >= 0", name="ck_watch_progress_position_nonnegative"),
        sa.CheckConstraint("duration_seconds > 0", name="ck_watch_progress_duration_positive"),
        sa.CheckConstraint(
            "percentage >= 0 AND percentage <= 100", name="ck_watch_progress_percentage"
        ),
        sa.UniqueConstraint(
            "profile_id", "playback_source_id", name="uq_watch_progress_profile_source"
        ),
    )
    op.create_index("ix_watch_progress_profile_id", "watch_progress", ["profile_id"])
    op.create_index(
        "ix_watch_progress_playback_source_id", "watch_progress", ["playback_source_id"]
    )
    op.create_index("ix_watch_progress_last_watched_at", "watch_progress", ["last_watched_at"])


def downgrade() -> None:
    op.drop_table("watch_progress")
    op.drop_table("playback_sources")
