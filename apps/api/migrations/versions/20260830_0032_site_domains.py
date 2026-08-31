"""Add owner-managed custom site domains.

Revision ID: 20260830_0032
Revises: 20260827_0031
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260830_0032"
down_revision: str | Sequence[str] | None = "20260827_0031"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "site_brand_configurations",
        sa.Column("domains_revision", sa.Integer(), server_default="0", nullable=False),
    )
    op.create_check_constraint(
        "ck_site_brand_configuration_domains_revision",
        "site_brand_configurations",
        "domains_revision >= 0",
    )

    op.create_table(
        "site_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "site_brand_configuration_id",
            sa.Integer(),
            sa.ForeignKey("site_brand_configurations.id", ondelete="CASCADE"),
            server_default="1",
            nullable=False,
        ),
        sa.Column("hostname", sa.String(253), nullable=False),
        sa.Column("status", sa.String(32), server_default="provisioning", nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("provider_hostname_id", sa.String(64)),
        sa.Column(
            "dns_records", sa.JSON(), server_default=sa.text("'[]'::json"), nullable=False
        ),
        sa.Column("failure_reason", sa.String(64)),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column("edge_published_revision", sa.Integer()),
        sa.Column("verified_at", sa.DateTime(timezone=True)),
        sa.Column("activated_at", sa.DateTime(timezone=True)),
        sa.Column("last_checked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "site_brand_configuration_id = 1", name="ck_site_domains_single_site"
        ),
        sa.CheckConstraint(
            "hostname = lower(hostname)", name="ck_site_domains_lowercase_hostname"
        ),
        sa.CheckConstraint("right(hostname, 1) <> '.'", name="ck_site_domains_no_trailing_dot"),
        sa.CheckConstraint("revision >= 0", name="ck_site_domains_revision"),
        sa.CheckConstraint(
            "edge_published_revision IS NULL OR edge_published_revision >= 0",
            name="ck_site_domains_edge_published_revision",
        ),
        sa.CheckConstraint(
            "status IN ('provisioning', 'pending_dns', 'pending_tls', 'pending_edge', "
            "'active', 'failed', 'removing')",
            name="ck_site_domains_status",
        ),
        sa.CheckConstraint(
            "NOT is_primary OR status = 'active'", name="ck_site_domains_primary_active"
        ),
        sa.UniqueConstraint("provider_hostname_id", name="uq_site_domains_provider_hostname_id"),
    )
    op.create_index(
        "ix_site_domains_site_brand_configuration_id",
        "site_domains",
        ["site_brand_configuration_id"],
    )
    op.create_index("ix_site_domains_hostname", "site_domains", ["hostname"], unique=True)
    op.create_index("ix_site_domains_status", "site_domains", ["status"])
    op.create_index(
        "uq_site_domains_primary",
        "site_domains",
        ["site_brand_configuration_id"],
        unique=True,
        postgresql_where=sa.text("is_primary"),
    )


def downgrade() -> None:
    op.drop_table("site_domains")
    op.drop_constraint(
        "ck_site_brand_configuration_domains_revision",
        "site_brand_configurations",
        type_="check",
    )
    op.drop_column("site_brand_configurations", "domains_revision")
