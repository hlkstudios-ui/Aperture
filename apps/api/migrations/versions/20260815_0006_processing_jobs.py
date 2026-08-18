"""media processing jobs

Revision ID: 20260815_0006
Revises: 20260815_0005
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0006"
down_revision: str | None = "20260815_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    state = postgresql.ENUM(
        "queued",
        "probing",
        "processing",
        "validating",
        "ready",
        "failed",
        name="processing_state",
        create_type=False,
    )
    state.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("media_assets.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("state", state, nullable=False),
        sa.Column("progress_percent", sa.Integer(), server_default="0", nullable=False),
        sa.Column("source_metadata", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("rendition_status", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("audio_tracks", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("subtitle_tracks", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("chapters", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("duration_seconds", sa.Float()),
        sa.Column("manifest_key", sa.String(500)),
        sa.Column("thumbnail_key", sa.String(500)),
        sa.Column("sprite_key", sa.String(500)),
        sa.Column("error_message", sa.String(1000)),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_processing_jobs_state", "processing_jobs", ["state"])
    op.create_index("ix_processing_jobs_state_created", "processing_jobs", ["state", "created_at"])


def downgrade() -> None:
    op.drop_table("processing_jobs")
    postgresql.ENUM(name="processing_state").drop(op.get_bind(), checkfirst=True)
