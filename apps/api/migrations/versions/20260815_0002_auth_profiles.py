"""Add customer, profile, session, administrator, and audit models."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "20260815_0002"
down_revision = "20260815_0001"
branch_labels = None
depends_on = None

maturity_level = postgresql.ENUM("kids", "teen", "adult", name="maturity_level", create_type=False)


def upgrade() -> None:
    maturity_level.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("mfa_secret_encrypted", sa.Text()),
        sa.Column("mfa_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "profiles",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("avatar_key", sa.String(200)),
        sa.Column("maturity_level", maturity_level, nullable=False),
        sa.Column("language", sa.String(16), server_default="en", nullable=False),
        sa.Column("is_kids", sa.Boolean(), server_default="false", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_profiles_user_id", "profiles", ["user_id"])
    op.create_index("ix_profiles_user_name", "profiles", ["user_id", "name"], unique=True)
    op.create_table(
        "profile_preferences",
        sa.Column("profile_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("autoplay_next", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("autoplay_previews", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("preferred_audio_language", sa.String(16)),
        sa.Column("preferred_subtitle_language", sa.String(16)),
        sa.Column("subtitles_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("cinephile_mode", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("extra", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("profile_id"),
    )
    op.create_table(
        "device_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("active_profile_id", postgresql.UUID(as_uuid=True)),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_seen_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["active_profile_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_device_sessions_user_id", "device_sessions", ["user_id"])
    op.create_index("ix_device_sessions_token_hash", "device_sessions", ["token_hash"], unique=True)
    op.create_index("ix_device_sessions_expires_at", "device_sessions", ["expires_at"])
    op.create_table(
        "admin_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("admin_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["admin_id"], ["admins.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_admin_sessions_admin_id", "admin_sessions", ["admin_id"])
    op.create_index("ix_admin_sessions_token_hash", "admin_sessions", ["token_hash"], unique=True)
    op.create_index("ix_admin_sessions_expires_at", "admin_sessions", ["expires_at"])
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column("actor_id", postgresql.UUID(as_uuid=True)),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("detail", sa.JSON(), server_default="{}", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_logs_actor_type", "audit_logs", ["actor_type"])
    op.create_index("ix_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("audit_logs")
    op.drop_table("admin_sessions")
    op.drop_table("device_sessions")
    op.drop_table("profile_preferences")
    op.drop_table("profiles")
    op.drop_table("admins")
    op.drop_table("users")
    maturity_level.drop(op.get_bind(), checkfirst=True)
