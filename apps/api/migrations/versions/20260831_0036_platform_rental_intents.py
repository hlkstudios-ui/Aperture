"""Add the isolated marketplace rental-intent control plane.

Revision ID: 20260831_0036
Revises: 20260831_0035
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0036"
down_revision: str | Sequence[str] | None = "20260831_0035"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APERTURES_TEMPLATE_ID = "a0000000-0000-4000-8000-000000000001"


def upgrade() -> None:
    op.create_table(
        "platform_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("email = lower(email)", name="ck_platform_accounts_email_lowercase"),
    )
    op.create_index("ix_platform_accounts_email", "platform_accounts", ["email"], unique=True)

    op.create_table(
        "platform_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("user_agent", sa.String(500)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "last_seen_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_platform_sessions_token_hash"),
    )
    op.create_index("ix_platform_sessions_account_id", "platform_sessions", ["account_id"])
    op.create_index("ix_platform_sessions_expires_at", "platform_sessions", ["expires_at"])
    op.create_index(
        "ix_platform_sessions_token_hash", "platform_sessions", ["token_hash"], unique=True
    )
    op.create_index(
        "ix_platform_sessions_account_expiry",
        "platform_sessions",
        ["account_id", "expires_at"],
    )

    op.create_table(
        "platform_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.String(500), nullable=False),
        sa.Column("category", sa.String(80), nullable=False),
        sa.Column("thumbnail_url", sa.String(1000)),
        sa.Column(
            "preview_assets",
            postgresql.JSONB(),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("demo_url", sa.String(1000)),
        sa.Column("status", sa.String(24), server_default="preview", nullable=False),
        sa.Column("current_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("current_agreement_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("rental_price_cents", sa.Integer()),
        sa.Column("rental_currency", sa.String(3)),
        sa.Column("rental_interval", sa.String(16)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_platform_templates_slug",
        ),
        sa.CheckConstraint(
            "status IN ('preview', 'published', 'retired')",
            name="ck_platform_templates_status",
        ),
        sa.CheckConstraint(
            "rental_price_cents IS NULL OR rental_price_cents > 0",
            name="ck_platform_templates_price_positive",
        ),
        sa.CheckConstraint(
            "rental_currency IS NULL OR rental_currency ~ '^[A-Z]{3}$'",
            name="ck_platform_templates_currency",
        ),
        sa.CheckConstraint(
            "rental_interval IS NULL OR rental_interval IN ('month', 'year')",
            name="ck_platform_templates_interval",
        ),
        sa.CheckConstraint(
            "status <> 'published' OR (current_version_id IS NOT NULL "
            "AND current_agreement_version_id IS NOT NULL AND rental_price_cents IS NOT NULL "
            "AND rental_currency IS NOT NULL AND rental_interval IS NOT NULL)",
            name="ck_platform_templates_published_complete",
        ),
    )
    op.create_index("ix_platform_templates_slug", "platform_templates", ["slug"], unique=True)
    op.create_index("ix_platform_templates_category", "platform_templates", ["category"])

    op.create_table(
        "platform_template_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.String(32), nullable=False),
        sa.Column("source_commit", sa.String(40), nullable=False),
        sa.Column("release_manifest_sha256", sa.String(64), nullable=False),
        sa.Column(
            "feature_manifest",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "configuration_schema",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("template_id", "id", name="uq_platform_template_versions_template_id"),
        sa.UniqueConstraint(
            "template_id", "version", name="uq_platform_template_versions_template_version"
        ),
        sa.UniqueConstraint("release_manifest_sha256"),
        sa.CheckConstraint(
            "version ~ '^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$'",
            name="ck_platform_template_versions_version",
        ),
        sa.CheckConstraint(
            "source_commit ~ '^[0-9a-f]{40}$'",
            name="ck_platform_template_versions_source_commit",
        ),
        sa.CheckConstraint(
            "release_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_platform_template_versions_manifest_sha256",
        ),
    )
    op.create_index(
        "ix_platform_template_versions_template_id",
        "platform_template_versions",
        ["template_id"],
    )

    op.create_table(
        "rental_agreement_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "template_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_templates.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version", sa.String(64), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("template_id", "id", name="uq_rental_agreements_template_id"),
        sa.UniqueConstraint("template_id", "version", name="uq_rental_agreements_template_version"),
        sa.UniqueConstraint("id", "content_sha256", name="uq_rental_agreements_id_content_hash"),
        sa.CheckConstraint(
            "version ~ '^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$'",
            name="ck_rental_agreements_version",
        ),
        sa.CheckConstraint("length(content) >= 200", name="ck_rental_agreements_content_length"),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_rental_agreements_content_sha256"
        ),
    )
    op.create_index(
        "ix_rental_agreement_versions_template_id",
        "rental_agreement_versions",
        ["template_id"],
    )

    op.create_foreign_key(
        "fk_platform_templates_current_version",
        "platform_templates",
        "platform_template_versions",
        ["id", "current_version_id"],
        ["template_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_foreign_key(
        "fk_platform_templates_current_agreement",
        "platform_templates",
        "rental_agreement_versions",
        ["id", "current_agreement_version_id"],
        ["template_id", "id"],
        ondelete="RESTRICT",
    )

    op.create_table(
        "platform_tenants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(63), nullable=False),
        sa.Column("hosted_hostname", sa.String(253), nullable=False),
        sa.Column("business_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), server_default="reserved", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_platform_tenants_slug",
        ),
        sa.CheckConstraint(
            "hosted_hostname = lower(hosted_hostname) AND right(hosted_hostname, 1) <> '.'",
            name="ck_platform_tenants_hosted_hostname",
        ),
        sa.CheckConstraint("status = 'reserved'", name="ck_platform_tenants_reserved_only"),
    )
    op.create_index("ix_platform_tenants_slug", "platform_tenants", ["slug"], unique=True)
    op.create_index(
        "ix_platform_tenants_hosted_hostname",
        "platform_tenants",
        ["hosted_hostname"],
        unique=True,
    )

    op.create_table(
        "tenant_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("role", sa.String(24), server_default="owner", nullable=False),
        sa.Column("status", sa.String(24), server_default="active", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("tenant_id", "account_id", name="uq_tenant_memberships_tenant_account"),
        sa.CheckConstraint(
            "role IN ('owner', 'administrator', 'member')",
            name="ck_tenant_memberships_role",
        ),
        sa.CheckConstraint("status = 'active'", name="ck_tenant_memberships_active_only"),
    )
    op.create_index("ix_tenant_memberships_tenant_id", "tenant_memberships", ["tenant_id"])
    op.create_index("ix_tenant_memberships_account_id", "tenant_memberships", ["account_id"])
    op.create_index(
        "uq_tenant_memberships_one_owner",
        "tenant_memberships",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )

    op.create_table(
        "legal_acceptances",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("agreement_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agreement_content_sha256", sa.String(64), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ip_address", sa.String(64)),
        sa.Column("user_agent", sa.String(500)),
        sa.UniqueConstraint(
            "account_id",
            "agreement_version_id",
            "id",
            name="uq_legal_acceptances_account_agreement_id",
        ),
        sa.ForeignKeyConstraint(
            ["agreement_version_id", "agreement_content_sha256"],
            ["rental_agreement_versions.id", "rental_agreement_versions.content_sha256"],
            name="fk_legal_acceptances_agreement_hash",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "agreement_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_legal_acceptances_content_sha256",
        ),
    )
    op.create_index("ix_legal_acceptances_account_id", "legal_acceptances", ["account_id"])
    op.create_index(
        "ix_legal_acceptances_agreement_version_id",
        "legal_acceptances",
        ["agreement_version_id"],
    )

    op.create_table(
        "template_rentals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_tenants.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("template_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("template_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("agreement_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("legal_acceptance_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), server_default="awaiting_payment", nullable=False),
        sa.Column("price_cents", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("billing_interval", sa.String(16), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "account_id", "idempotency_key", name="uq_template_rentals_idempotency"
        ),
        sa.UniqueConstraint("tenant_id", name="uq_template_rentals_tenant"),
        sa.UniqueConstraint("legal_acceptance_id", name="uq_template_rentals_legal_acceptance"),
        sa.ForeignKeyConstraint(
            ["template_id", "template_version_id"],
            ["platform_template_versions.template_id", "platform_template_versions.id"],
            name="fk_template_rentals_template_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["template_id", "agreement_version_id"],
            ["rental_agreement_versions.template_id", "rental_agreement_versions.id"],
            name="fk_template_rentals_agreement_version",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["account_id", "agreement_version_id", "legal_acceptance_id"],
            [
                "legal_acceptances.account_id",
                "legal_acceptances.agreement_version_id",
                "legal_acceptances.id",
            ],
            name="fk_template_rentals_acceptance_owner",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.account_id"],
            name="fk_template_rentals_owner_membership",
            ondelete="RESTRICT",
        ),
        sa.CheckConstraint("status = 'awaiting_payment'", name="ck_template_rentals_unpaid_only"),
        sa.CheckConstraint("price_cents > 0", name="ck_template_rentals_price_positive"),
        sa.CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_template_rentals_currency"),
        sa.CheckConstraint(
            "billing_interval IN ('month', 'year')", name="ck_template_rentals_interval"
        ),
        sa.CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_template_rentals_request_fingerprint",
        ),
    )
    op.create_index("ix_template_rentals_account_id", "template_rentals", ["account_id"])
    op.create_index("ix_template_rentals_tenant_id", "template_rentals", ["tenant_id"])
    op.create_index("ix_template_rentals_template_id", "template_rentals", ["template_id"])
    op.create_index("ix_template_rentals_status", "template_rentals", ["status"])
    op.create_index(
        "ix_template_rentals_account_created",
        "template_rentals",
        ["account_id", "created_at"],
    )

    op.create_table(
        "platform_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_type", sa.String(32), nullable=False),
        sa.Column(
            "actor_account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="RESTRICT"),
        ),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("outcome", sa.String(24), nullable=False),
        sa.Column("resource_type", sa.String(64)),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True)),
        sa.Column("idempotency_key", postgresql.UUID(as_uuid=True)),
        sa.Column("ip_address", sa.String(64)),
        sa.Column(
            "detail",
            postgresql.JSONB(),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "actor_type IN ('platform_account', 'system')",
            name="ck_platform_audit_events_actor_type",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'denied', 'failed')",
            name="ck_platform_audit_events_outcome",
        ),
        sa.CheckConstraint(
            "(actor_type = 'system' AND actor_account_id IS NULL) OR "
            "(actor_type = 'platform_account' AND actor_account_id IS NOT NULL)",
            name="ck_platform_audit_events_actor_binding",
        ),
    )
    op.create_index(
        "ix_platform_audit_events_actor_account_id",
        "platform_audit_events",
        ["actor_account_id"],
    )
    op.create_index("ix_platform_audit_events_action", "platform_audit_events", ["action"])
    op.create_index("ix_platform_audit_events_created_at", "platform_audit_events", ["created_at"])
    op.create_index(
        "ix_platform_audit_events_action_created",
        "platform_audit_events",
        ["action", "created_at"],
    )
    op.create_index(
        "ix_platform_audit_events_resource",
        "platform_audit_events",
        ["resource_type", "resource_id"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_immutable_platform_row() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          RAISE EXCEPTION 'immutable platform record cannot be changed';
        END;
        $$
        """
    )
    for table_name in (
        "platform_template_versions",
        "rental_agreement_versions",
        "legal_acceptances",
        "platform_audit_events",
    ):
        op.execute(
            f"""
            CREATE TRIGGER trg_{table_name}_immutable
            BEFORE UPDATE OR DELETE ON {table_name}
            FOR EACH ROW EXECUTE FUNCTION reject_immutable_platform_row()
            """
        )

    op.execute(
        """
        CREATE FUNCTION protect_template_rental_binding() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'template rental records cannot be deleted';
          END IF;
          IF NEW.account_id IS DISTINCT FROM OLD.account_id
             OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
             OR NEW.template_id IS DISTINCT FROM OLD.template_id
             OR NEW.template_version_id IS DISTINCT FROM OLD.template_version_id
             OR NEW.agreement_version_id IS DISTINCT FROM OLD.agreement_version_id
             OR NEW.legal_acceptance_id IS DISTINCT FROM OLD.legal_acceptance_id
             OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.price_cents IS DISTINCT FROM OLD.price_cents
             OR NEW.currency IS DISTINCT FROM OLD.currency
             OR NEW.billing_interval IS DISTINCT FROM OLD.billing_interval
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'template rental binding cannot be changed';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_template_rentals_protect_binding
        BEFORE UPDATE OR DELETE ON template_rentals
        FOR EACH ROW EXECUTE FUNCTION protect_template_rental_binding()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_platform_tenant_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'platform tenant reservations cannot be deleted';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.slug IS DISTINCT FROM OLD.slug
             OR NEW.hosted_hostname IS DISTINCT FROM OLD.hosted_hostname
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'platform tenant reservation identity cannot be changed';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_platform_tenants_protect_identity
        BEFORE UPDATE OR DELETE ON platform_tenants
        FOR EACH ROW EXECUTE FUNCTION protect_platform_tenant_identity()
        """
    )
    op.execute(
        """
        CREATE FUNCTION protect_tenant_membership_binding() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'tenant membership records cannot be deleted';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
             OR NEW.account_id IS DISTINCT FROM OLD.account_id
             OR NEW.role IS DISTINCT FROM OLD.role
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'tenant membership binding cannot be changed';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_tenant_memberships_protect_binding
        BEFORE UPDATE OR DELETE ON tenant_memberships
        FOR EACH ROW EXECUTE FUNCTION protect_tenant_membership_binding()
        """
    )

    template_table = sa.table(
        "platform_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("slug", sa.String()),
        sa.column("name", sa.String()),
        sa.column("description", sa.String()),
        sa.column("category", sa.String()),
        sa.column("preview_assets", postgresql.JSONB()),
        sa.column("status", sa.String()),
    )
    op.bulk_insert(
        template_table,
        [
            {
                "id": APERTURES_TEMPLATE_ID,
                "slug": "apertures",
                "name": "Apertures",
                "description": (
                    "A configurable cinematic streaming storefront with catalog, profiles, "
                    "discovery, Studio management, and optional custom-domain support."
                ),
                "category": "streaming",
                "preview_assets": [],
                "status": "preview",
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("platform_audit_events")
    op.drop_table("template_rentals")
    op.drop_table("legal_acceptances")
    op.drop_table("tenant_memberships")
    op.drop_table("platform_tenants")
    op.drop_constraint(
        "fk_platform_templates_current_agreement", "platform_templates", type_="foreignkey"
    )
    op.drop_constraint(
        "fk_platform_templates_current_version", "platform_templates", type_="foreignkey"
    )
    op.drop_table("rental_agreement_versions")
    op.drop_table("platform_template_versions")
    op.drop_table("platform_templates")
    op.drop_table("platform_sessions")
    op.drop_table("platform_accounts")
    op.execute("DROP FUNCTION IF EXISTS protect_tenant_membership_binding()")
    op.execute("DROP FUNCTION IF EXISTS protect_platform_tenant_identity()")
    op.execute("DROP FUNCTION IF EXISTS protect_template_rental_binding()")
    op.execute("DROP FUNCTION IF EXISTS reject_immutable_platform_row()")
