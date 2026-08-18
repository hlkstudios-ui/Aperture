"""Add one-time password resets and administrator MFA recovery codes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260815_0003"
down_revision = "20260815_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "password_reset_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_password_reset_tokens_user_id", "password_reset_tokens", ["user_id"])
    op.create_index(
        "ix_password_reset_tokens_token_hash",
        "password_reset_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index("ix_password_reset_tokens_expires_at", "password_reset_tokens", ["expires_at"])
    op.create_table(
        "admin_mfa_recovery_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_admin_mfa_recovery_codes_admin_id", "admin_mfa_recovery_codes", ["admin_id"]
    )
    op.create_index(
        "ix_admin_mfa_recovery_codes_code_hash",
        "admin_mfa_recovery_codes",
        ["code_hash"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("admin_mfa_recovery_codes")
    op.drop_table("password_reset_tokens")
