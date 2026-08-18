"""permitted cinephile stills

Revision ID: 20260815_0016
Revises: 20260815_0015
Create Date: 2026-08-15 21:03:46.577367
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260815_0016"
down_revision: str | Sequence[str] | None = "20260815_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("artwork", sa.Column("scene_id", sa.UUID(), nullable=True))
    op.add_column("artwork", sa.Column("timestamp_seconds", sa.Float(), nullable=True))
    op.add_column("artwork", sa.Column("rights_basis", sa.Text(), nullable=True))
    op.add_column(
        "artwork",
        sa.Column("permitted_for_gallery", sa.Boolean(), server_default="false", nullable=False),
    )
    op.create_index(op.f("ix_artwork_scene_id"), "artwork", ["scene_id"], unique=False)
    op.create_foreign_key(
        "fk_artwork_scene_id_scenes",
        "artwork",
        "scenes",
        ["scene_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_check_constraint(
        "ck_artwork_permitted_gallery_metadata",
        "artwork",
        "NOT permitted_for_gallery OR (kind = 'still' AND scene_id IS NOT NULL "
        "AND timestamp_seconds IS NOT NULL AND rights_basis IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_artwork_timestamp_nonnegative",
        "artwork",
        "timestamp_seconds IS NULL OR timestamp_seconds >= 0",
    )


def downgrade() -> None:
    op.drop_constraint("ck_artwork_timestamp_nonnegative", "artwork", type_="check")
    op.drop_constraint("ck_artwork_permitted_gallery_metadata", "artwork", type_="check")
    op.drop_constraint("fk_artwork_scene_id_scenes", "artwork", type_="foreignkey")
    op.drop_index(op.f("ix_artwork_scene_id"), table_name="artwork")
    op.drop_column("artwork", "permitted_for_gallery")
    op.drop_column("artwork", "rights_basis")
    op.drop_column("artwork", "timestamp_seconds")
    op.drop_column("artwork", "scene_id")
