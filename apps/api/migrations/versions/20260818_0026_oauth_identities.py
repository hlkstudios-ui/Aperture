"""Add external OAuth identities and allow passwordless accounts.

Revision ID: 20260818_0026
Revises: 20260817_0025
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260818_0026"
down_revision: str | Sequence[str] | None = "20260817_0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=True)
    op.create_table(
        "oauth_identities",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(320), nullable=False),
        sa.Column("email_at_link", sa.String(320), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_login_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),
    )
    op.create_index("ix_oauth_identities_user_id", "oauth_identities", ["user_id"])
    op.create_index("ix_oauth_identities_provider", "oauth_identities", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_oauth_identities_provider", table_name="oauth_identities")
    op.drop_index("ix_oauth_identities_user_id", table_name="oauth_identities")
    op.drop_table("oauth_identities")
    op.alter_column("users", "password_hash", existing_type=sa.Text(), nullable=False)
