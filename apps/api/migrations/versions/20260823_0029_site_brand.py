"""Add owner-controlled, publishable site brand configuration.

Revision ID: 20260823_0029
Revises: 20260821_0028
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260823_0029"
down_revision: str | Sequence[str] | None = "20260821_0028"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "site_brand_assets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("content_type", sa.String(32), nullable=False),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "byte_size > 0 AND byte_size <= 2097152", name="ck_site_brand_asset_size"
        ),
        sa.CheckConstraint(
            "width >= 64 AND width <= 4096 AND height >= 64 AND height <= 4096",
            name="ck_site_brand_asset_dimensions",
        ),
    )
    op.create_index(
        "ix_site_brand_assets_sha256", "site_brand_assets", ["sha256"], unique=True
    )

    op.create_table(
        "site_brand_configurations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "draft_config",
            sa.JSON(),
            server_default=sa.text("'{}'::json"),
            nullable=False,
        ),
        sa.Column("published_snapshot", sa.JSON()),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("published_revision", sa.Integer()),
        sa.Column("current_step", sa.Integer(), server_default="1", nullable=False),
        sa.Column(
            "completed_steps",
            sa.JSON(),
            server_default=sa.text("'[]'::json"),
            nullable=False,
        ),
        sa.Column(
            "draft_logo_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_brand_assets.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "published_logo_asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("site_brand_assets.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("id = 1", name="ck_site_brand_configuration_singleton"),
        sa.CheckConstraint("revision >= 0", name="ck_site_brand_configuration_revision"),
        sa.CheckConstraint(
            "published_revision IS NULL OR published_revision >= 0",
            name="ck_site_brand_configuration_published_revision",
        ),
        sa.CheckConstraint(
            "current_step >= 1 AND current_step <= 5", name="ck_site_brand_current_step"
        ),
    )
    op.create_index(
        "ix_site_brand_configurations_owner_admin_id",
        "site_brand_configurations",
        ["owner_admin_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("site_brand_configurations")
    op.drop_table("site_brand_assets")
