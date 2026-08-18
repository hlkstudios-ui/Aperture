"""bounded analytics events and daily aggregates

Revision ID: 20260815_0010
Revises: 20260815_0009
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0010"
down_revision: str | None = "20260815_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVENTS = (
    "impression",
    "detail_open",
    "play_start",
    "progress",
    "pause",
    "seek",
    "completion",
    "search",
    "search_click",
    "my_list",
    "rating",
    "scenelens_open",
    "ask_movie",
)


def upgrade() -> None:
    source = postgresql.ENUM(*EVENTS, name="analytics_event_type")
    source.create(op.get_bind(), checkfirst=True)
    event_type = postgresql.ENUM(*EVENTS, name="analytics_event_type", create_type=False)
    op.create_table(
        "analytics_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "profile_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "device_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("device_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("dedupe_key", sa.String(200), nullable=False, unique=True),
        sa.Column("event_type", event_type, nullable=False),
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
        sa.Column("position_seconds", sa.Float()),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("query", sa.String(200)),
        sa.Column("result_count", sa.Integer()),
        sa.Column("value", sa.Float()),
        sa.Column("properties", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("is_bot", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_internal", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer <= 1",
            name="ck_analytics_events_one_title",
        ),
        sa.CheckConstraint(
            "position_seconds IS NULL OR position_seconds >= 0", name="ck_analytics_position"
        ),
        sa.CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0", name="ck_analytics_duration"
        ),
        sa.CheckConstraint(
            "result_count IS NULL OR result_count >= 0", name="ck_analytics_result_count"
        ),
    )
    op.create_index("ix_analytics_events_profile_id", "analytics_events", ["profile_id"])
    op.create_index(
        "ix_analytics_events_device_session_id", "analytics_events", ["device_session_id"]
    )
    op.create_index("ix_analytics_events_event_type", "analytics_events", ["event_type"])
    op.create_index("ix_analytics_events_movie_id", "analytics_events", ["movie_id"])
    op.create_index("ix_analytics_events_episode_id", "analytics_events", ["episode_id"])
    op.create_index("ix_analytics_events_occurred_at", "analytics_events", ["occurred_at"])
    op.create_index("ix_analytics_events_received_at", "analytics_events", ["received_at"])
    op.create_index(
        "ix_analytics_events_type_occurred", "analytics_events", ["event_type", "occurred_at"]
    )
    op.create_index(
        "ix_analytics_events_profile_occurred", "analytics_events", ["profile_id", "occurred_at"]
    )
    op.create_table(
        "aggregated_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("event_type", event_type, nullable=False),
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
        sa.Column("event_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unique_profiles", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_value", sa.Float(), server_default="0", nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer <= 1",
            name="ck_aggregated_metrics_one_title",
        ),
        sa.UniqueConstraint(
            "day",
            "event_type",
            "movie_id",
            "episode_id",
            name="uq_aggregated_metrics_dimension",
            postgresql_nulls_not_distinct=True,
        ),
    )
    op.create_index("ix_aggregated_metrics_day_type", "aggregated_metrics", ["day", "event_type"])


def downgrade() -> None:
    op.drop_table("aggregated_metrics")
    op.drop_table("analytics_events")
    postgresql.ENUM(name="analytics_event_type").drop(op.get_bind(), checkfirst=True)
