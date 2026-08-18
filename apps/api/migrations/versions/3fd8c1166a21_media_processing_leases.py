"""Add expiring ownership leases to media processing jobs."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "3fd8c1166a21"
down_revision: str | None = "94f37d54a8bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "processing_jobs", sa.Column("lease_owner", postgresql.UUID(as_uuid=True), nullable=True)
    )
    op.add_column(
        "processing_jobs", sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.create_index(
        "ix_processing_jobs_lease_expiry", "processing_jobs", ["lease_expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_processing_jobs_lease_expiry", table_name="processing_jobs")
    op.drop_column("processing_jobs", "lease_expires_at")
    op.drop_column("processing_jobs", "lease_owner")
