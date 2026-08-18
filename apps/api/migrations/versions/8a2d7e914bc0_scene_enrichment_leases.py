"""Add expiring ownership leases to scene enrichment jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "8a2d7e914bc0"
down_revision: str | None = "3fd8c1166a21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "scene_intelligence_jobs",
        sa.Column("lease_owner", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "scene_intelligence_jobs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_scene_jobs_lease_expiry", "scene_intelligence_jobs", ["lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_scene_jobs_lease_expiry", table_name="scene_intelligence_jobs")
    op.drop_column("scene_intelligence_jobs", "lease_expires_at")
    op.drop_column("scene_intelligence_jobs", "lease_owner")
