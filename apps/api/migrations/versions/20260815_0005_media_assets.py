"""media asset uploads

Revision ID: 20260815_0005
Revises: 638bc495ce1d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260815_0005"
down_revision: str | None = "638bc495ce1d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    asset_state = postgresql.ENUM(
        "uploading", "completed", "failed", "cancelled", name="asset_state", create_type=False
    )
    asset_state.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "media_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_by_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("media_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(500), nullable=False, unique=True),
        sa.Column("state", asset_state, nullable=False),
        sa.Column("etag", sa.String(128)),
        sa.Column("failure_reason", sa.String(500)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_media_assets_created_by_admin_id", "media_assets", ["created_by_admin_id"])
    op.create_index("ix_media_assets_state", "media_assets", ["state"])
    op.create_index("ix_media_assets_state_created", "media_assets", ["state", "created_at"])


def downgrade() -> None:
    op.drop_table("media_assets")
    postgresql.ENUM(name="asset_state").drop(op.get_bind(), checkfirst=True)
