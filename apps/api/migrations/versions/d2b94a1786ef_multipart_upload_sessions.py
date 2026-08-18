"""Persist resumable multipart upload session ownership."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d2b94a1786ef"
down_revision: str | None = "8a2d7e914bc0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "media_assets",
        sa.Column("upload_strategy", sa.String(length=20), server_default="single", nullable=False),
    )
    op.add_column(
        "media_assets", sa.Column("multipart_upload_id", sa.String(length=500), nullable=True)
    )
    op.add_column("media_assets", sa.Column("multipart_part_size", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_media_assets_upload_strategy",
        "media_assets",
        "upload_strategy IN ('single', 'multipart')",
    )
    op.create_check_constraint(
        "ck_media_assets_multipart_fields",
        "media_assets",
        "(upload_strategy = 'single' AND multipart_upload_id IS NULL "
        "AND multipart_part_size IS NULL) "
        "OR (upload_strategy = 'multipart' AND multipart_upload_id IS NOT NULL "
        "AND multipart_part_size >= 5242880)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_media_assets_multipart_fields", "media_assets", type_="check")
    op.drop_constraint("ck_media_assets_upload_strategy", "media_assets", type_="check")
    op.drop_column("media_assets", "multipart_part_size")
    op.drop_column("media_assets", "multipart_upload_id")
    op.drop_column("media_assets", "upload_strategy")
