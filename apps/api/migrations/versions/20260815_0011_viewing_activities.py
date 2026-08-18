"""durable profile viewing activity ledger

Revision ID: 20260815_0011
Revises: 20260815_0010
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0011"
down_revision: str | None = "20260815_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "viewing_activities",
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
        sa.Column("activity_number", sa.Integer(), nullable=False),
        sa.Column("is_rewatch", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("watched_seconds", sa.Float(), server_default="0", nullable=False),
        sa.Column("completed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_watched_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint(
            "activity_number > 0", name="ck_viewing_activity_number_positive"
        ),
        sa.CheckConstraint(
            "watched_seconds >= 0", name="ck_viewing_activity_watched_nonnegative"
        ),
        sa.UniqueConstraint(
            "profile_id",
            "playback_source_id",
            "activity_number",
            name="uq_viewing_activities_profile_source_number",
        ),
    )
    op.create_index("ix_viewing_activities_profile_id", "viewing_activities", ["profile_id"])
    op.create_index(
        "ix_viewing_activities_playback_source_id",
        "viewing_activities",
        ["playback_source_id"],
    )
    op.create_index(
        "ix_viewing_activities_profile_started",
        "viewing_activities",
        ["profile_id", "started_at"],
    )
    op.create_index(
        "ix_viewing_activities_profile_completed",
        "viewing_activities",
        ["profile_id", "completed_at"],
    )
    op.execute(
        """
        INSERT INTO viewing_activities (
          id, profile_id, playback_source_id, activity_number, is_rewatch,
          watched_seconds, completed, started_at, last_watched_at, completed_at
        )
        SELECT gen_random_uuid(), profile_id, playback_source_id, 1, false,
          LEAST(position_seconds, duration_seconds), completed, created_at,
          last_watched_at, CASE WHEN completed THEN last_watched_at ELSE NULL END
        FROM watch_progress
        """
    )


def downgrade() -> None:
    op.drop_table("viewing_activities")
