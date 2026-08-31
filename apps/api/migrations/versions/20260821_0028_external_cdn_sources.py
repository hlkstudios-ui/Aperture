"""Add licensed external CDN playback sources.

Revision ID: 20260821_0028
Revises: 20260818_0027
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260821_0028"
down_revision = "20260818_0027"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("playback_sources", "processing_job_id", nullable=True)
    op.add_column("playback_sources", sa.Column("external_manifest_url", sa.String(2000)))
    op.add_column("playback_sources", sa.Column("external_format", sa.String(16)))
    op.add_column("playback_sources", sa.Column("duration_seconds", sa.Float()))
    op.add_column("playback_sources", sa.Column("rights_basis", sa.String(500)))
    op.add_column("playback_sources", sa.Column("rights_reference", sa.String(500)))
    op.add_column("playback_sources", sa.Column("rights_start_at", sa.DateTime(timezone=True)))
    op.add_column("playback_sources", sa.Column("rights_end_at", sa.DateTime(timezone=True)))
    op.add_column(
        "playback_sources",
        sa.Column("allowed_territories", postgresql.JSONB(), server_default="[]", nullable=False),
    )
    op.add_column(
        "playback_sources",
        sa.Column("is_active", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index("ix_playback_sources_is_active", "playback_sources", ["is_active"])
    op.create_index("ix_playback_sources_rights_start_at", "playback_sources", ["rights_start_at"])
    op.create_index("ix_playback_sources_rights_end_at", "playback_sources", ["rights_end_at"])
    op.create_check_constraint(
        "ck_playback_sources_exactly_one_origin",
        "playback_sources",
        "(processing_job_id IS NOT NULL)::integer + "
        "(external_manifest_url IS NOT NULL)::integer = 1",
    )
    op.create_check_constraint(
        "ck_playback_sources_external_rights_evidence",
        "playback_sources",
        "external_manifest_url IS NULL OR "
        "(rights_basis IS NOT NULL AND rights_reference IS NOT NULL)",
    )
    op.execute("UPDATE playback_sources SET is_active = true WHERE processing_job_id IS NOT NULL")


def downgrade() -> None:
    op.drop_constraint(
        "ck_playback_sources_external_rights_evidence", "playback_sources", type_="check"
    )
    op.drop_constraint("ck_playback_sources_exactly_one_origin", "playback_sources", type_="check")
    op.drop_index("ix_playback_sources_rights_end_at", table_name="playback_sources")
    op.drop_index("ix_playback_sources_rights_start_at", table_name="playback_sources")
    op.drop_index("ix_playback_sources_is_active", table_name="playback_sources")
    for column in (
        "is_active",
        "allowed_territories",
        "rights_end_at",
        "rights_start_at",
        "rights_reference",
        "rights_basis",
        "duration_seconds",
        "external_format",
        "external_manifest_url",
    ):
        op.drop_column("playback_sources", column)
    op.alter_column("playback_sources", "processing_job_id", nullable=False)
