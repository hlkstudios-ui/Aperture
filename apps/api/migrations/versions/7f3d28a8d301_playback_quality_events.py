"""playback quality events

Revision ID: 7f3d28a8d301
Revises: 59d824385095
"""

from collections.abc import Sequence

from alembic import op

revision: str = "7f3d28a8d301"
down_revision: str | Sequence[str] | None = "59d824385095"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

QOE_EVENTS = ("playback_startup", "playback_buffer", "playback_error", "quality_change")
BASE_EVENTS = (
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
    for value in QOE_EVENTS:
        op.execute(f"ALTER TYPE analytics_event_type ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    values = ", ".join(f"'{value}'" for value in QOE_EVENTS)
    op.execute(f"DELETE FROM aggregated_metrics WHERE event_type::text IN ({values})")
    op.execute(f"DELETE FROM analytics_events WHERE event_type::text IN ({values})")
    op.execute(
        "ALTER TABLE analytics_events ALTER COLUMN event_type TYPE text "
        "USING event_type::text"
    )
    op.execute(
        "ALTER TABLE aggregated_metrics ALTER COLUMN event_type TYPE text "
        "USING event_type::text"
    )
    op.execute("DROP TYPE analytics_event_type")
    members = ", ".join(f"'{value}'" for value in BASE_EVENTS)
    op.execute(f"CREATE TYPE analytics_event_type AS ENUM ({members})")
    op.execute(
        "ALTER TABLE analytics_events ALTER COLUMN event_type TYPE analytics_event_type "
        "USING event_type::analytics_event_type"
    )
    op.execute(
        "ALTER TABLE aggregated_metrics ALTER COLUMN event_type TYPE analytics_event_type "
        "USING event_type::analytics_event_type"
    )
