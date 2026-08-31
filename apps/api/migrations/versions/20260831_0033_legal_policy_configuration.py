"""Add the owner-only legal policy information draft.

Revision ID: 20260831_0033
Revises: 20260830_0032
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0033"
down_revision: str | Sequence[str] | None = "20260830_0032"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "legal_policy_configurations",
        sa.Column(
            "site_brand_configuration_id",
            sa.Integer(),
            sa.ForeignKey("site_brand_configurations.id", ondelete="CASCADE"),
            server_default="1",
            primary_key=True,
        ),
        sa.Column("legal_operator_name", sa.String(200)),
        sa.Column("country_code", sa.String(2)),
        sa.Column("region", sa.String(120)),
        sa.Column("support_email", sa.String(320)),
        sa.Column("privacy_email", sa.String(320)),
        sa.Column("copyright_email", sa.String(320)),
        sa.Column("minimum_user_age", sa.Integer()),
        sa.Column("governing_law_jurisdiction", sa.String(200)),
        sa.Column("revision", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "site_brand_configuration_id = 1",
            name="ck_legal_policy_configuration_single_site",
        ),
        sa.CheckConstraint("revision >= 0", name="ck_legal_policy_configuration_revision"),
        sa.CheckConstraint(
            "country_code IS NULL OR "
            "(length(country_code) = 2 AND country_code = upper(country_code))",
            name="ck_legal_policy_configuration_country_code",
        ),
        sa.CheckConstraint(
            "minimum_user_age IS NULL OR minimum_user_age BETWEEN 0 AND 120",
            name="ck_legal_policy_configuration_minimum_user_age",
        ),
    )


def downgrade() -> None:
    op.drop_table("legal_policy_configurations")
