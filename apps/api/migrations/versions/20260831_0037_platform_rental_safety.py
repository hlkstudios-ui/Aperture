"""Add verified-account and expiring-rental database safety.

Revision ID: 20260831_0037
Revises: 20260831_0036
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260831_0037"
down_revision: str | Sequence[str] | None = "20260831_0036"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _replace_platform_account_lifecycle_function() -> None:
    op.execute(
        """
        CREATE FUNCTION protect_platform_account_lifecycle() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          database_now timestamptz := transaction_timestamp();
          active_reservations bigint;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'platform account records cannot be deleted';
          END IF;

          IF TG_OP = 'INSERT' THEN
            IF NEW.email_verified_at IS NOT NULL
               OR NEW.email_verification_expires_at IS NULL
               OR NEW.email_verification_expires_at <= database_now
               OR NEW.email_verification_expires_at > database_now + INTERVAL '168 hours' THEN
              RAISE EXCEPTION 'new platform account verification state is invalid'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.email IS DISTINCT FROM OLD.email
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'platform account identity cannot be changed';
          END IF;

          IF NEW.active_unpaid_reservation_limit < OLD.active_unpaid_reservation_limit THEN
            SELECT count(*)
            INTO active_reservations
            FROM template_rentals
            WHERE account_id = OLD.id
              AND status = 'awaiting_payment'
              AND reservation_expires_at > database_now;
            IF NEW.active_unpaid_reservation_limit < active_reservations THEN
              RAISE EXCEPTION 'platform account quota is below its active reservations'
                USING ERRCODE = '23514';
            END IF;
          END IF;

          IF OLD.email_verified_at IS NOT NULL THEN
            IF NEW.email_verified_at IS DISTINCT FROM OLD.email_verified_at
               OR NEW.email_verification_expires_at IS NOT NULL THEN
              RAISE EXCEPTION 'platform account verification cannot be reversed or replaced'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF NEW.email_verified_at IS NOT NULL THEN
            IF OLD.email_verification_expires_at IS NULL
               OR OLD.email_verification_expires_at <= database_now
               OR NEW.email_verification_expires_at IS NOT NULL
               OR NEW.email_verified_at > database_now
               OR NEW.email_verified_at < OLD.created_at
               OR NOT EXISTS (
                 SELECT 1
                 FROM platform_email_verification_tokens AS token
                 WHERE token.account_id = OLD.id
                   AND token.state = 'active'
                   AND token.used_at IS NULL
                   AND token.expires_at > database_now
               ) THEN
              RAISE EXCEPTION 'platform account verification transition is invalid'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF NEW.email_verification_expires_at IS DISTINCT FROM
             OLD.email_verification_expires_at THEN
            IF OLD.email_verification_expires_at IS NULL
               OR OLD.email_verification_expires_at > database_now
               OR NEW.email_verification_expires_at IS NULL
               OR NEW.email_verification_expires_at <= database_now
               OR NEW.email_verification_expires_at > database_now + INTERVAL '168 hours'
               OR NEW.password_hash IS NOT DISTINCT FROM OLD.password_hash
               OR NOT NEW.is_active THEN
              RAISE EXCEPTION 'unverified platform account cannot be reclaimed yet'
              USING ERRCODE = '23514';
            END IF;
          ELSIF NEW.password_hash IS DISTINCT FROM OLD.password_hash THEN
            RAISE EXCEPTION 'unverified password can only change during expired reclaim'
              USING ERRCODE = '23514';
          END IF;

          RETURN NEW;
        END;
        $$
        """
    )


def _replace_verification_token_lifecycle_function() -> None:
    op.execute(
        """
        CREATE FUNCTION protect_platform_verification_token_lifecycle() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          database_now timestamptz := transaction_timestamp();
          account_verified_at timestamptz;
          account_verification_expires_at timestamptz;
          account_active boolean;
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'platform email verification tokens cannot be deleted';
          END IF;

          IF TG_OP = 'INSERT' THEN
            SELECT
              email_verified_at,
              email_verification_expires_at,
              is_active
            INTO
              account_verified_at,
              account_verification_expires_at,
              account_active
            FROM platform_accounts
            WHERE id = NEW.account_id
            FOR KEY SHARE;

            IF NOT FOUND
               OR NOT account_active
               OR account_verified_at IS NOT NULL
               OR account_verification_expires_at IS NULL
               OR account_verification_expires_at <= database_now
               OR NEW.state <> 'pending_delivery'
               OR NEW.used_at IS NOT NULL
               OR NEW.expires_at <= database_now
               OR NEW.expires_at > account_verification_expires_at THEN
              RAISE EXCEPTION 'platform email verification token is not issuable'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.account_id IS DISTINCT FROM OLD.account_id
             OR NEW.token_hash IS DISTINCT FROM OLD.token_hash
             OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'platform email verification token binding cannot be changed';
          END IF;

          IF NEW.state = OLD.state THEN
            IF NEW.used_at IS DISTINCT FROM OLD.used_at THEN
              RAISE EXCEPTION 'platform email verification token timestamp cannot be changed'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF OLD.state = 'active' AND NEW.state IN ('used', 'superseded') THEN
            IF NEW.used_at IS NULL
               OR NEW.used_at < OLD.created_at
               OR NEW.used_at > database_now
               OR (NEW.state = 'used' AND OLD.expires_at <= database_now) THEN
              RAISE EXCEPTION 'active verification token terminal transition is invalid'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF OLD.state = 'pending_delivery' AND NEW.state = 'active' THEN
            IF NEW.used_at IS NOT NULL OR OLD.expires_at <= database_now THEN
              RAISE EXCEPTION 'expired pending verification token cannot become active'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          IF OLD.state = 'pending_delivery' AND NEW.state = 'delivery_failed' THEN
            IF NEW.used_at IS NULL
               OR NEW.used_at < OLD.created_at
               OR NEW.used_at > database_now THEN
              RAISE EXCEPTION 'verification delivery failure time is invalid'
                USING ERRCODE = '23514';
            END IF;
            RETURN NEW;
          END IF;

          RAISE EXCEPTION 'platform email verification token transition is invalid'
              USING ERRCODE = '23514';
        END;
        $$
        """
    )


def _create_account_token_consistency() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_platform_account_token_consistency() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          target_account_id uuid;
          account_verified_at timestamptz;
          live_token_count bigint;
          verification_use_count bigint;
        BEGIN
          IF TG_TABLE_NAME = 'platform_accounts' THEN
            target_account_id := NEW.id;
          ELSE
            target_account_id := NEW.account_id;
          END IF;

          SELECT email_verified_at
          INTO account_verified_at
          FROM platform_accounts
          WHERE id = target_account_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'verification token references a missing platform account'
              USING ERRCODE = '23514';
          END IF;

          IF account_verified_at IS NOT NULL THEN
            SELECT count(*)
            INTO live_token_count
            FROM platform_email_verification_tokens
            WHERE account_id = target_account_id
              AND state IN ('active', 'pending_delivery');
            IF live_token_count <> 0 THEN
              RAISE EXCEPTION 'verified platform account cannot retain live verification tokens'
                USING ERRCODE = '23514';
            END IF;
          END IF;

          IF TG_TABLE_NAME = 'platform_accounts' THEN
            IF TG_OP = 'UPDATE'
               AND OLD.email_verified_at IS NULL
               AND NEW.email_verified_at IS NOT NULL THEN
              SELECT count(*)
              INTO verification_use_count
              FROM platform_email_verification_tokens
              WHERE account_id = target_account_id
                AND state = 'used'
                AND used_at = NEW.email_verified_at
                AND created_at <= NEW.email_verified_at
                AND expires_at > NEW.email_verified_at;
              IF verification_use_count <> 1 THEN
                RAISE EXCEPTION 'account verification requires one consumed active token'
                  USING ERRCODE = '23514';
              END IF;
            END IF;
          END IF;

          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_platform_accounts_token_consistency
        AFTER INSERT OR UPDATE ON platform_accounts
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_platform_account_token_consistency()
        """
    )
    op.execute(
        """
        CREATE CONSTRAINT TRIGGER trg_platform_verification_tokens_account_consistency
        AFTER INSERT OR UPDATE ON platform_email_verification_tokens
        DEFERRABLE INITIALLY DEFERRED
        FOR EACH ROW EXECUTE FUNCTION enforce_platform_account_token_consistency()
        """
    )


def _replace_tenant_lifecycle_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_platform_tenant_identity() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          database_now timestamptz := transaction_timestamp();
        BEGIN
          IF TG_OP = 'DELETE' THEN
            RAISE EXCEPTION 'platform tenant reservations cannot be deleted';
          END IF;
          IF NEW.id IS DISTINCT FROM OLD.id
             OR NEW.slug IS DISTINCT FROM OLD.slug
             OR NEW.hosted_hostname IS DISTINCT FROM OLD.hosted_hostname
             OR NEW.business_name IS DISTINCT FROM OLD.business_name
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'platform tenant reservation identity cannot be changed';
          END IF;
          IF OLD.status = 'reserved' AND NEW.status = 'released' THEN
            IF NEW.release_reason <> 'expired'
               OR NEW.released_at IS NULL
               OR NEW.released_at < OLD.created_at
               OR NEW.released_at > database_now THEN
              RAISE EXCEPTION 'platform tenant release transition is invalid'
                USING ERRCODE = '23514';
            END IF;
          ELSIF NEW.status IS DISTINCT FROM OLD.status
                OR NEW.released_at IS DISTINCT FROM OLD.released_at
                OR NEW.release_reason IS DISTINCT FROM OLD.release_reason THEN
            RAISE EXCEPTION 'platform tenant lifecycle can only transition to released once'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )


def _replace_membership_lifecycle_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_tenant_membership_binding() RETURNS trigger
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
          IF OLD.status = 'active' AND NEW.status = 'released' THEN
            RETURN NEW;
          END IF;
          IF NEW.status IS DISTINCT FROM OLD.status THEN
            RAISE EXCEPTION 'tenant membership can only transition to released once'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )


def _replace_rental_lifecycle_function() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_template_rental_binding() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          database_now timestamptz := transaction_timestamp();
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
             OR NEW.owner_membership_id IS DISTINCT FROM OLD.owner_membership_id
             OR NEW.owner_membership_role IS DISTINCT FROM OLD.owner_membership_role
             OR NEW.idempotency_key IS DISTINCT FROM OLD.idempotency_key
             OR NEW.request_fingerprint IS DISTINCT FROM OLD.request_fingerprint
             OR NEW.price_cents IS DISTINCT FROM OLD.price_cents
             OR NEW.currency IS DISTINCT FROM OLD.currency
             OR NEW.billing_interval IS DISTINCT FROM OLD.billing_interval
             OR NEW.reservation_expires_at IS DISTINCT FROM OLD.reservation_expires_at
             OR NEW.created_at IS DISTINCT FROM OLD.created_at THEN
            RAISE EXCEPTION 'template rental binding cannot be changed';
          END IF;
          IF OLD.status = 'awaiting_payment' AND NEW.status = 'expired' THEN
            IF database_now < OLD.reservation_expires_at
               OR NEW.expired_at IS NULL
               OR NEW.expired_at < OLD.reservation_expires_at
               OR NEW.expired_at > database_now
               OR NEW.status_changed_at IS DISTINCT FROM NEW.expired_at THEN
              RAISE EXCEPTION 'template rental expiration transition is invalid'
                USING ERRCODE = '23514';
            END IF;
          ELSIF NEW.status IS DISTINCT FROM OLD.status
                OR NEW.expired_at IS DISTINCT FROM OLD.expired_at
                OR NEW.status_changed_at IS DISTINCT FROM OLD.status_changed_at THEN
            RAISE EXCEPTION 'template rental can only transition to expired once'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )


def _create_rental_insert_safety() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_template_rental_insert_safety() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          database_now timestamptz := transaction_timestamp();
          account_active boolean;
          account_verified_at timestamptz;
          reservation_limit smallint;
          active_reservations bigint;
        BEGIN
          SELECT
            is_active,
            email_verified_at,
            active_unpaid_reservation_limit
          INTO
            account_active,
            account_verified_at,
            reservation_limit
          FROM platform_accounts
          WHERE id = NEW.account_id
          FOR UPDATE;

          IF NOT FOUND
             OR NOT account_active
             OR account_verified_at IS NULL
             OR account_verified_at > database_now THEN
            RAISE EXCEPTION 'verified active platform account required for rental intent'
              USING ERRCODE = '23514';
          END IF;
          IF NEW.status <> 'awaiting_payment'
             OR NEW.expired_at IS NOT NULL
             OR NEW.reservation_expires_at <= database_now
             OR NEW.status_changed_at < NEW.created_at
             OR NEW.status_changed_at > database_now THEN
            RAISE EXCEPTION 'new rental intent lifecycle is invalid'
              USING ERRCODE = '23514';
          END IF;

          SELECT count(*)
          INTO active_reservations
          FROM template_rentals
          WHERE account_id = NEW.account_id
            AND status = 'awaiting_payment'
            AND reservation_expires_at > database_now;

          IF active_reservations >= reservation_limit THEN
            RAISE EXCEPTION 'active unpaid rental reservation quota exceeded'
              USING ERRCODE = '23514';
          END IF;
          RETURN NEW;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_template_rentals_insert_safety
        BEFORE INSERT ON template_rentals
        FOR EACH ROW EXECUTE FUNCTION enforce_template_rental_insert_safety()
        """
    )


def _create_deferred_lifecycle_consistency() -> None:
    op.execute(
        """
        CREATE FUNCTION enforce_platform_rental_lifecycle_consistency() RETURNS trigger
        LANGUAGE plpgsql AS $$
        DECLARE
          target_tenant_id uuid;
          tenant_row platform_tenants%ROWTYPE;
          rental_row template_rentals%ROWTYPE;
          membership_row tenant_memberships%ROWTYPE;
          expiration_audit_count bigint;
        BEGIN
          IF TG_TABLE_NAME = 'platform_tenants' THEN
            target_tenant_id := NEW.id;
          ELSE
            target_tenant_id := NEW.tenant_id;
          END IF;

          SELECT * INTO tenant_row
          FROM platform_tenants
          WHERE id = target_tenant_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'rental lifecycle references a missing tenant'
              USING ERRCODE = '23514';
          END IF;

          SELECT * INTO rental_row
          FROM template_rentals
          WHERE tenant_id = target_tenant_id;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'tenant reservation must be bound to exactly one rental intent'
              USING ERRCODE = '23514';
          END IF;

          SELECT * INTO membership_row
          FROM tenant_memberships
          WHERE id = rental_row.owner_membership_id
            AND tenant_id = rental_row.tenant_id
            AND account_id = rental_row.account_id
            AND role = rental_row.owner_membership_role;
          IF NOT FOUND THEN
            RAISE EXCEPTION 'rental intent must be bound to its exact owner membership'
              USING ERRCODE = '23514';
          END IF;

          IF rental_row.status = 'awaiting_payment' THEN
            IF tenant_row.status <> 'reserved'
               OR tenant_row.released_at IS NOT NULL
               OR tenant_row.release_reason IS NOT NULL
               OR membership_row.status <> 'active'
               OR rental_row.expired_at IS NOT NULL THEN
              RAISE EXCEPTION 'active rental reservation lifecycle is inconsistent'
                USING ERRCODE = '23514';
            END IF;
          ELSIF rental_row.status = 'expired' THEN
            IF tenant_row.status <> 'released'
               OR tenant_row.release_reason <> 'expired'
               OR tenant_row.released_at IS DISTINCT FROM rental_row.expired_at
               OR membership_row.status <> 'released'
               OR rental_row.status_changed_at IS DISTINCT FROM rental_row.expired_at THEN
              RAISE EXCEPTION 'expired rental reservation lifecycle is inconsistent'
                USING ERRCODE = '23514';
            END IF;
            SELECT count(*)
            INTO expiration_audit_count
            FROM platform_audit_events
            WHERE actor_type = 'system'
              AND actor_account_id IS NULL
              AND action = 'template_rental.intent_expired'
              AND outcome = 'succeeded'
              AND resource_type = 'template_rental'
              AND resource_id = rental_row.id
              AND idempotency_key = rental_row.idempotency_key;
            IF expiration_audit_count <> 1 THEN
              RAISE EXCEPTION 'expired rental reservation requires its system audit event'
                USING ERRCODE = '23514';
            END IF;
          ELSE
            RAISE EXCEPTION 'unsupported rental reservation lifecycle state'
              USING ERRCODE = '23514';
          END IF;

          RETURN NULL;
        END;
        $$
        """
    )
    trigger_events = {
        "platform_tenants": "INSERT OR UPDATE",
        "tenant_memberships": "INSERT OR UPDATE",
        "template_rentals": "INSERT OR UPDATE",
    }
    for table_name, trigger_event in trigger_events.items():
        op.execute(
            f"""
            CREATE CONSTRAINT TRIGGER trg_{table_name}_rental_lifecycle_consistency
            AFTER {trigger_event} ON {table_name}
            DEFERRABLE INITIALLY DEFERRED
            FOR EACH ROW EXECUTE FUNCTION enforce_platform_rental_lifecycle_consistency()
            """
        )


def _create_0036_lifecycle_functions() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION protect_template_rental_binding() RETURNS trigger
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
        CREATE OR REPLACE FUNCTION protect_platform_tenant_identity() RETURNS trigger
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
        CREATE OR REPLACE FUNCTION protect_tenant_membership_binding() RETURNS trigger
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


def upgrade() -> None:
    op.execute(
        "LOCK TABLE platform_accounts, template_rentals, platform_tenants, "
        "tenant_memberships, legal_acceptances IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM platform_accounts) THEN
            RAISE EXCEPTION
              '20260831_0037 requires platform_accounts to be empty; migrate identities explicitly'
              USING ERRCODE = '55000';
          END IF;
          IF EXISTS (SELECT 1 FROM template_rentals) THEN
            RAISE EXCEPTION
              '20260831_0037 requires template_rentals to be empty; migrate rentals explicitly'
              USING ERRCODE = '55000';
          END IF;
          IF EXISTS (SELECT 1 FROM platform_tenants)
             OR EXISTS (SELECT 1 FROM tenant_memberships)
             OR EXISTS (SELECT 1 FROM legal_acceptances) THEN
            RAISE EXCEPTION
              '20260831_0037 found orphaned rental-intent records; reconcile before upgrade'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$
        """
    )

    op.add_column(
        "platform_accounts",
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_accounts",
        sa.Column("email_verification_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_accounts",
        sa.Column(
            "active_unpaid_reservation_limit",
            sa.SmallInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_platform_accounts_email_verification_state",
        "platform_accounts",
        "(email_verified_at IS NULL AND email_verification_expires_at IS NOT NULL) OR "
        "(email_verified_at IS NOT NULL AND email_verification_expires_at IS NULL)",
    )
    op.create_check_constraint(
        "ck_platform_accounts_unpaid_reservation_limit",
        "platform_accounts",
        "active_unpaid_reservation_limit BETWEEN 0 AND 5",
    )
    op.create_index(
        "ix_platform_accounts_email_verified_at",
        "platform_accounts",
        ["email_verified_at"],
    )
    op.create_index(
        "ix_platform_accounts_email_verification_expires_at",
        "platform_accounts",
        ["email_verification_expires_at"],
    )

    op.create_table(
        "platform_email_verification_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("platform_accounts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.String(24),
            server_default="pending_delivery",
            nullable=False,
        ),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_platform_email_verification_tokens_hash",
        ),
        sa.CheckConstraint(
            "expires_at > created_at",
            name="ck_platform_email_verification_tokens_expiry",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'pending_delivery', 'used', 'superseded', "
            "'delivery_failed')",
            name="ck_platform_email_verification_tokens_state",
        ),
        sa.CheckConstraint(
            "(state IN ('active', 'pending_delivery') AND used_at IS NULL) OR "
            "(state IN ('used', 'superseded', 'delivery_failed') "
            "AND used_at IS NOT NULL)",
            name="ck_platform_email_verification_tokens_state_timestamps",
        ),
    )
    op.create_index(
        "ix_platform_email_verification_tokens_account_id",
        "platform_email_verification_tokens",
        ["account_id"],
    )
    op.create_index(
        "ix_platform_email_verification_tokens_token_hash",
        "platform_email_verification_tokens",
        ["token_hash"],
        unique=True,
    )
    op.create_index(
        "ix_platform_email_verification_tokens_expires_at",
        "platform_email_verification_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_platform_email_verification_tokens_state",
        "platform_email_verification_tokens",
        ["state"],
    )
    op.create_index(
        "uq_platform_email_verification_tokens_active_account",
        "platform_email_verification_tokens",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.create_index(
        "uq_platform_email_verification_tokens_pending_account",
        "platform_email_verification_tokens",
        ["account_id"],
        unique=True,
        postgresql_where=sa.text("state = 'pending_delivery'"),
    )
    op.create_index(
        "ix_platform_email_verification_tokens_pending_created",
        "platform_email_verification_tokens",
        ["created_at", "id"],
        postgresql_where=sa.text("state = 'pending_delivery'"),
    )
    _replace_verification_token_lifecycle_function()
    op.execute(
        """
        CREATE TRIGGER trg_platform_email_verification_tokens_protect_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON platform_email_verification_tokens
        FOR EACH ROW EXECUTE FUNCTION protect_platform_verification_token_lifecycle()
        """
    )

    op.add_column(
        "platform_tenants",
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "platform_tenants",
        sa.Column("release_reason", sa.String(24), nullable=True),
    )
    op.drop_constraint(
        "ck_platform_tenants_reserved_only",
        "platform_tenants",
        type_="check",
    )
    op.create_check_constraint(
        "ck_platform_tenants_lifecycle",
        "platform_tenants",
        "(status = 'reserved' AND released_at IS NULL AND release_reason IS NULL) OR "
        "(status = 'released' AND released_at IS NOT NULL AND release_reason = 'expired')",
    )
    op.drop_index("ix_platform_tenants_slug", table_name="platform_tenants")
    op.drop_index("ix_platform_tenants_hosted_hostname", table_name="platform_tenants")
    op.create_index("ix_platform_tenants_slug", "platform_tenants", ["slug"])
    op.create_index(
        "ix_platform_tenants_hosted_hostname",
        "platform_tenants",
        ["hosted_hostname"],
    )
    op.create_index(
        "ix_platform_tenants_released_at",
        "platform_tenants",
        ["released_at"],
    )
    op.create_index(
        "ix_platform_tenants_slug_created",
        "platform_tenants",
        ["slug", "created_at"],
    )
    op.create_index(
        "uq_platform_tenants_active_slug",
        "platform_tenants",
        ["slug"],
        unique=True,
        postgresql_where=sa.text("status = 'reserved'"),
    )
    op.create_index(
        "uq_platform_tenants_active_hostname",
        "platform_tenants",
        ["hosted_hostname"],
        unique=True,
        postgresql_where=sa.text("status = 'reserved'"),
    )
    _replace_tenant_lifecycle_function()

    op.drop_constraint(
        "ck_tenant_memberships_role",
        "tenant_memberships",
        type_="check",
    )
    op.drop_constraint(
        "ck_tenant_memberships_active_only",
        "tenant_memberships",
        type_="check",
    )
    op.create_unique_constraint(
        "uq_tenant_memberships_owner_binding",
        "tenant_memberships",
        ["id", "tenant_id", "account_id", "role"],
    )
    op.create_check_constraint(
        "ck_tenant_memberships_role",
        "tenant_memberships",
        "role = 'owner'",
    )
    op.create_check_constraint(
        "ck_tenant_memberships_lifecycle",
        "tenant_memberships",
        "status IN ('active', 'released')",
    )
    _replace_membership_lifecycle_function()

    op.add_column(
        "template_rentals",
        sa.Column("owner_membership_id", postgresql.UUID(as_uuid=True), nullable=False),
    )
    op.add_column(
        "template_rentals",
        sa.Column(
            "owner_membership_role",
            sa.String(24),
            server_default="owner",
            nullable=False,
        ),
    )
    op.add_column(
        "template_rentals",
        sa.Column("reservation_expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "template_rentals",
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column(
        "template_rentals",
        sa.Column("expired_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_constraint(
        "ck_template_rentals_unpaid_only",
        "template_rentals",
        type_="check",
    )
    op.create_foreign_key(
        "fk_template_rentals_exact_owner_membership",
        "template_rentals",
        "tenant_memberships",
        ["owner_membership_id", "tenant_id", "account_id", "owner_membership_role"],
        ["id", "tenant_id", "account_id", "role"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_template_rentals_owner_membership_role",
        "template_rentals",
        "owner_membership_role = 'owner'",
    )
    op.create_check_constraint(
        "ck_template_rentals_lifecycle_status",
        "template_rentals",
        "status IN ('awaiting_payment', 'expired')",
    )
    op.create_check_constraint(
        "ck_template_rentals_lifecycle_timestamps",
        "template_rentals",
        "status_changed_at >= created_at AND "
        "((status = 'awaiting_payment' AND expired_at IS NULL) OR "
        "(status = 'expired' AND expired_at IS NOT NULL AND status_changed_at = expired_at))",
    )
    op.create_check_constraint(
        "ck_template_rentals_reservation_expiry",
        "template_rentals",
        "reservation_expires_at > created_at",
    )
    op.create_index(
        "ix_template_rentals_reservation_expires_at",
        "template_rentals",
        ["reservation_expires_at"],
    )
    op.create_index(
        "ix_template_rentals_expired_at",
        "template_rentals",
        ["expired_at"],
    )
    op.create_index(
        "ix_template_rentals_active_account_expiry",
        "template_rentals",
        ["account_id", "reservation_expires_at"],
        postgresql_where=sa.text("status = 'awaiting_payment'"),
    )
    op.create_index(
        "ix_template_rentals_due_expiry",
        "template_rentals",
        ["reservation_expires_at", "id"],
        postgresql_where=sa.text("status = 'awaiting_payment'"),
    )
    _replace_rental_lifecycle_function()
    _create_rental_insert_safety()
    _create_deferred_lifecycle_consistency()
    _replace_platform_account_lifecycle_function()
    op.execute(
        """
        CREATE TRIGGER trg_platform_accounts_protect_lifecycle
        BEFORE INSERT OR UPDATE OR DELETE ON platform_accounts
        FOR EACH ROW EXECUTE FUNCTION protect_platform_account_lifecycle()
        """
    )
    _create_account_token_consistency()

    op.create_index(
        "uq_platform_audit_events_rental_expired",
        "platform_audit_events",
        ["resource_id"],
        unique=True,
        postgresql_where=sa.text(
            "resource_type = 'template_rental' "
            "AND action = 'template_rental.intent_expired'"
        ),
    )


def downgrade() -> None:
    op.execute(
        "LOCK TABLE platform_accounts, platform_email_verification_tokens, template_rentals, "
        "platform_tenants, tenant_memberships, legal_acceptances, platform_audit_events "
        "IN ACCESS EXCLUSIVE MODE"
    )
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM template_rentals
            WHERE status <> 'awaiting_payment' OR expired_at IS NOT NULL
          ) OR EXISTS (
            SELECT 1 FROM platform_tenants
            WHERE status <> 'reserved'
               OR released_at IS NOT NULL
               OR release_reason IS NOT NULL
          ) OR EXISTS (
            SELECT 1 FROM tenant_memberships
            WHERE status <> 'active'
          ) THEN
            RAISE EXCEPTION
              'cannot downgrade: terminal rental reservation history is not representable in 0036'
              USING ERRCODE = '55000';
          END IF;
          IF EXISTS (SELECT 1 FROM platform_email_verification_tokens)
             OR EXISTS (SELECT 1 FROM platform_accounts) THEN
            RAISE EXCEPTION
              'cannot downgrade: platform identity or verification history would be discarded'
              USING ERRCODE = '55000';
          END IF;
        END;
        $$
        """
    )

    op.drop_index(
        "uq_platform_audit_events_rental_expired",
        table_name="platform_audit_events",
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_verification_tokens_account_consistency "
        "ON platform_email_verification_tokens"
    )
    op.execute(
        "DROP TRIGGER IF EXISTS trg_platform_accounts_token_consistency ON platform_accounts"
    )
    op.execute("DROP FUNCTION IF EXISTS enforce_platform_account_token_consistency()")
    op.execute("DROP TRIGGER trg_platform_accounts_protect_lifecycle ON platform_accounts")
    op.execute("DROP FUNCTION protect_platform_account_lifecycle()")

    for table_name in ("platform_tenants", "tenant_memberships", "template_rentals"):
        op.execute(
            f"DROP TRIGGER trg_{table_name}_rental_lifecycle_consistency "
            f"ON {table_name}"
        )
    op.execute("DROP FUNCTION enforce_platform_rental_lifecycle_consistency()")
    op.execute("DROP TRIGGER trg_template_rentals_insert_safety ON template_rentals")
    op.execute("DROP FUNCTION enforce_template_rental_insert_safety()")
    _create_0036_lifecycle_functions()

    op.drop_index(
        "ix_template_rentals_due_expiry",
        table_name="template_rentals",
    )
    op.drop_index(
        "ix_template_rentals_active_account_expiry",
        table_name="template_rentals",
    )
    op.drop_index(
        "ix_template_rentals_expired_at",
        table_name="template_rentals",
    )
    op.drop_index(
        "ix_template_rentals_reservation_expires_at",
        table_name="template_rentals",
    )
    op.drop_constraint(
        "ck_template_rentals_reservation_expiry",
        "template_rentals",
        type_="check",
    )
    op.drop_constraint(
        "ck_template_rentals_lifecycle_timestamps",
        "template_rentals",
        type_="check",
    )
    op.drop_constraint(
        "ck_template_rentals_lifecycle_status",
        "template_rentals",
        type_="check",
    )
    op.drop_constraint(
        "ck_template_rentals_owner_membership_role",
        "template_rentals",
        type_="check",
    )
    op.drop_constraint(
        "fk_template_rentals_exact_owner_membership",
        "template_rentals",
        type_="foreignkey",
    )
    op.drop_column("template_rentals", "expired_at")
    op.drop_column("template_rentals", "status_changed_at")
    op.drop_column("template_rentals", "reservation_expires_at")
    op.drop_column("template_rentals", "owner_membership_role")
    op.drop_column("template_rentals", "owner_membership_id")
    op.create_check_constraint(
        "ck_template_rentals_unpaid_only",
        "template_rentals",
        "status = 'awaiting_payment'",
    )

    op.drop_constraint(
        "ck_tenant_memberships_lifecycle",
        "tenant_memberships",
        type_="check",
    )
    op.drop_constraint(
        "ck_tenant_memberships_role",
        "tenant_memberships",
        type_="check",
    )
    op.drop_constraint(
        "uq_tenant_memberships_owner_binding",
        "tenant_memberships",
        type_="unique",
    )
    op.create_check_constraint(
        "ck_tenant_memberships_role",
        "tenant_memberships",
        "role IN ('owner', 'administrator', 'member')",
    )
    op.create_check_constraint(
        "ck_tenant_memberships_active_only",
        "tenant_memberships",
        "status = 'active'",
    )

    op.drop_index("uq_platform_tenants_active_hostname", table_name="platform_tenants")
    op.drop_index("uq_platform_tenants_active_slug", table_name="platform_tenants")
    op.drop_index("ix_platform_tenants_slug_created", table_name="platform_tenants")
    op.drop_index("ix_platform_tenants_released_at", table_name="platform_tenants")
    op.drop_index("ix_platform_tenants_hosted_hostname", table_name="platform_tenants")
    op.drop_index("ix_platform_tenants_slug", table_name="platform_tenants")
    op.create_index(
        "ix_platform_tenants_hosted_hostname",
        "platform_tenants",
        ["hosted_hostname"],
        unique=True,
    )
    op.create_index(
        "ix_platform_tenants_slug",
        "platform_tenants",
        ["slug"],
        unique=True,
    )
    op.drop_constraint(
        "ck_platform_tenants_lifecycle",
        "platform_tenants",
        type_="check",
    )
    op.drop_column("platform_tenants", "release_reason")
    op.drop_column("platform_tenants", "released_at")
    op.create_check_constraint(
        "ck_platform_tenants_reserved_only",
        "platform_tenants",
        "status = 'reserved'",
    )

    op.execute(
        "DROP TRIGGER trg_platform_email_verification_tokens_protect_lifecycle "
        "ON platform_email_verification_tokens"
    )
    op.execute("DROP FUNCTION protect_platform_verification_token_lifecycle()")
    op.drop_table("platform_email_verification_tokens")

    op.drop_index(
        "ix_platform_accounts_email_verification_expires_at",
        table_name="platform_accounts",
    )
    op.drop_index(
        "ix_platform_accounts_email_verified_at",
        table_name="platform_accounts",
    )
    op.drop_constraint(
        "ck_platform_accounts_unpaid_reservation_limit",
        "platform_accounts",
        type_="check",
    )
    op.drop_constraint(
        "ck_platform_accounts_email_verification_state",
        "platform_accounts",
        type_="check",
    )
    op.drop_column("platform_accounts", "active_unpaid_reservation_limit")
    op.drop_column("platform_accounts", "email_verification_expires_at")
    op.drop_column("platform_accounts", "email_verified_at")
