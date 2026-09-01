import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class PlatformAccount(Base):
    """A renter identity in the marketplace control plane, separate from cell viewers/admins."""

    __tablename__ = "platform_accounts"
    __table_args__ = (
        CheckConstraint("email = lower(email)", name="ck_platform_accounts_email_lowercase"),
        CheckConstraint(
            "(email_verified_at IS NULL AND email_verification_expires_at IS NOT NULL) OR "
            "(email_verified_at IS NOT NULL AND email_verification_expires_at IS NULL)",
            name="ck_platform_accounts_email_verification_state",
        ),
        CheckConstraint(
            "active_unpaid_reservation_limit BETWEEN 0 AND 5",
            name="ck_platform_accounts_unpaid_reservation_limit",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    email_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    email_verification_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), index=True
    )
    active_unpaid_reservation_limit: Mapped[int] = mapped_column(
        SmallInteger, default=1, server_default="1"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["PlatformSession"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )
    email_verification_tokens: Mapped[list["PlatformEmailVerificationToken"]] = relationship(
        back_populates="account", cascade="all, delete-orphan"
    )


class PlatformSession(Base):
    __tablename__ = "platform_sessions"
    __table_args__ = (
        CheckConstraint("token_hash ~ '^[0-9a-f]{64}$'", name="ck_platform_sessions_token_hash"),
        Index("ix_platform_sessions_account_expiry", "account_id", "expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[PlatformAccount] = relationship(back_populates="sessions")


class PlatformEmailVerificationToken(Base):
    """A one-use platform verification credential; only its SHA-256 digest is persisted."""

    __tablename__ = "platform_email_verification_tokens"
    __table_args__ = (
        CheckConstraint(
            "token_hash ~ '^[0-9a-f]{64}$'",
            name="ck_platform_email_verification_tokens_hash",
        ),
        CheckConstraint(
            "expires_at > created_at",
            name="ck_platform_email_verification_tokens_expiry",
        ),
        CheckConstraint(
            "state IN ('active', 'pending_delivery', 'used', 'superseded', "
            "'delivery_failed')",
            name="ck_platform_email_verification_tokens_state",
        ),
        CheckConstraint(
            "(state IN ('active', 'pending_delivery') AND used_at IS NULL) OR "
            "(state IN ('used', 'superseded', 'delivery_failed') "
            "AND used_at IS NOT NULL)",
            name="ck_platform_email_verification_tokens_state_timestamps",
        ),
        Index(
            "uq_platform_email_verification_tokens_active_account",
            "account_id",
            unique=True,
            postgresql_where=text("state = 'active'"),
        ),
        Index(
            "uq_platform_email_verification_tokens_pending_account",
            "account_id",
            unique=True,
            postgresql_where=text("state = 'pending_delivery'"),
        ),
        Index(
            "ix_platform_email_verification_tokens_pending_created",
            "created_at",
            "id",
            postgresql_where=text("state = 'pending_delivery'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    state: Mapped[str] = mapped_column(
        String(24), default="pending_delivery", server_default="pending_delivery", index=True
    )
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    account: Mapped[PlatformAccount] = relationship(back_populates="email_verification_tokens")


class PlatformTemplate(Base):
    __tablename__ = "platform_templates"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_platform_templates_slug",
        ),
        CheckConstraint(
            "status IN ('preview', 'published', 'retired')",
            name="ck_platform_templates_status",
        ),
        CheckConstraint(
            "rental_price_cents IS NULL OR rental_price_cents > 0",
            name="ck_platform_templates_price_positive",
        ),
        CheckConstraint(
            "rental_currency IS NULL OR rental_currency ~ '^[A-Z]{3}$'",
            name="ck_platform_templates_currency",
        ),
        CheckConstraint(
            "rental_interval IS NULL OR rental_interval IN ('month', 'year')",
            name="ck_platform_templates_interval",
        ),
        CheckConstraint(
            "status <> 'published' OR (current_version_id IS NOT NULL "
            "AND current_agreement_version_id IS NOT NULL AND rental_price_cents IS NOT NULL "
            "AND rental_currency IS NOT NULL AND rental_interval IS NOT NULL)",
            name="ck_platform_templates_published_complete",
        ),
        ForeignKeyConstraint(
            ["id", "current_version_id"],
            ["platform_template_versions.template_id", "platform_template_versions.id"],
            name="fk_platform_templates_current_version",
            ondelete="RESTRICT",
            use_alter=True,
        ),
        ForeignKeyConstraint(
            ["id", "current_agreement_version_id"],
            ["rental_agreement_versions.template_id", "rental_agreement_versions.id"],
            name="fk_platform_templates_current_agreement",
            ondelete="RESTRICT",
            use_alter=True,
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(63), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500))
    category: Mapped[str] = mapped_column(String(80), index=True)
    thumbnail_url: Mapped[str | None] = mapped_column(String(1000))
    preview_assets: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default=text("'[]'::jsonb")
    )
    demo_url: Mapped[str | None] = mapped_column(String(1000))
    status: Mapped[str] = mapped_column(String(24), default="preview", server_default="preview")
    current_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    current_agreement_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rental_price_cents: Mapped[int | None] = mapped_column(Integer)
    rental_currency: Mapped[str | None] = mapped_column(String(3))
    rental_interval: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    versions: Mapped[list["PlatformTemplateVersion"]] = relationship(
        back_populates="template",
        foreign_keys="PlatformTemplateVersion.template_id",
        cascade="all, delete-orphan",
    )
    agreements: Mapped[list["RentalAgreementVersion"]] = relationship(
        back_populates="template",
        foreign_keys="RentalAgreementVersion.template_id",
        cascade="all, delete-orphan",
    )


class PlatformTemplateVersion(Base):
    """An immutable, published binding to one reviewed release artifact manifest."""

    __tablename__ = "platform_template_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "id", name="uq_platform_template_versions_template_id"),
        UniqueConstraint(
            "template_id", "version", name="uq_platform_template_versions_template_version"
        ),
        CheckConstraint(
            "version ~ '^[0-9A-Za-z][0-9A-Za-z.+-]{0,31}$'",
            name="ck_platform_template_versions_version",
        ),
        CheckConstraint(
            "source_commit ~ '^[0-9a-f]{40}$'",
            name="ck_platform_template_versions_source_commit",
        ),
        CheckConstraint(
            "release_manifest_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_platform_template_versions_manifest_sha256",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_templates.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[str] = mapped_column(String(32))
    source_commit: Mapped[str] = mapped_column(String(40))
    release_manifest_sha256: Mapped[str] = mapped_column(String(64), unique=True)
    feature_manifest: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    configuration_schema: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    template: Mapped[PlatformTemplate] = relationship(
        back_populates="versions", foreign_keys=[template_id]
    )


class RentalAgreementVersion(Base):
    """Immutable published rental terms; drafts must not enter this table."""

    __tablename__ = "rental_agreement_versions"
    __table_args__ = (
        UniqueConstraint("template_id", "id", name="uq_rental_agreements_template_id"),
        UniqueConstraint("template_id", "version", name="uq_rental_agreements_template_version"),
        UniqueConstraint("id", "content_sha256", name="uq_rental_agreements_id_content_hash"),
        CheckConstraint(
            "version ~ '^[0-9A-Za-z][0-9A-Za-z.+-]{0,63}$'",
            name="ck_rental_agreements_version",
        ),
        CheckConstraint("length(content) >= 200", name="ck_rental_agreements_content_length"),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_rental_agreements_content_sha256"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_templates.id", ondelete="RESTRICT"), index=True
    )
    version: Mapped[str] = mapped_column(String(64))
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    template: Mapped[PlatformTemplate] = relationship(
        back_populates="agreements", foreign_keys=[template_id]
    )


class TenantReservation(Base):
    """A logical tenant reservation with trigger-protected identity, not a cell or domain."""

    __tablename__ = "platform_tenants"
    __table_args__ = (
        CheckConstraint(
            "slug ~ '^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$'",
            name="ck_platform_tenants_slug",
        ),
        CheckConstraint(
            "hosted_hostname = lower(hosted_hostname) AND right(hosted_hostname, 1) <> '.'",
            name="ck_platform_tenants_hosted_hostname",
        ),
        CheckConstraint(
            "(status = 'reserved' AND released_at IS NULL AND release_reason IS NULL) OR "
            "(status = 'released' AND released_at IS NOT NULL AND release_reason = 'expired')",
            name="ck_platform_tenants_lifecycle",
        ),
        Index(
            "uq_platform_tenants_active_slug",
            "slug",
            unique=True,
            postgresql_where=text("status = 'reserved'"),
        ),
        Index(
            "uq_platform_tenants_active_hostname",
            "hosted_hostname",
            unique=True,
            postgresql_where=text("status = 'reserved'"),
        ),
        Index("ix_platform_tenants_slug_created", "slug", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    slug: Mapped[str] = mapped_column(String(63), index=True)
    hosted_hostname: Mapped[str] = mapped_column(String(253), index=True)
    business_name: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(24), default="reserved", server_default="reserved")
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    release_reason: Mapped[str | None] = mapped_column(String(24))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TenantMembership(Base):
    """A tenant role whose principal/role binding is protected after creation."""

    __tablename__ = "tenant_memberships"
    __table_args__ = (
        UniqueConstraint("tenant_id", "account_id", name="uq_tenant_memberships_tenant_account"),
        UniqueConstraint(
            "id",
            "tenant_id",
            "account_id",
            "role",
            name="uq_tenant_memberships_owner_binding",
        ),
        CheckConstraint(
            "role = 'owner'",
            name="ck_tenant_memberships_role",
        ),
        CheckConstraint(
            "status IN ('active', 'released')",
            name="ck_tenant_memberships_lifecycle",
        ),
        Index(
            "uq_tenant_memberships_one_owner",
            "tenant_id",
            unique=True,
            postgresql_where=text("role = 'owner'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_tenants.id", ondelete="RESTRICT"), index=True
    )
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="RESTRICT"), index=True
    )
    role: Mapped[str] = mapped_column(String(24), default="owner", server_default="owner")
    status: Mapped[str] = mapped_column(String(24), default="active", server_default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class LegalAcceptance(Base):
    __tablename__ = "legal_acceptances"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "agreement_version_id",
            "id",
            name="uq_legal_acceptances_account_agreement_id",
        ),
        ForeignKeyConstraint(
            ["agreement_version_id", "agreement_content_sha256"],
            ["rental_agreement_versions.id", "rental_agreement_versions.content_sha256"],
            name="fk_legal_acceptances_agreement_hash",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "agreement_content_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_legal_acceptances_content_sha256",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="RESTRICT"), index=True
    )
    agreement_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    agreement_content_sha256: Mapped[str] = mapped_column(String(64))
    accepted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(500))


class TemplateRental(Base):
    """A lifecycle row whose accepted offer, identity, and price binding never change."""

    __tablename__ = "template_rentals"
    __table_args__ = (
        UniqueConstraint("account_id", "idempotency_key", name="uq_template_rentals_idempotency"),
        UniqueConstraint("tenant_id", name="uq_template_rentals_tenant"),
        UniqueConstraint("legal_acceptance_id", name="uq_template_rentals_legal_acceptance"),
        ForeignKeyConstraint(
            ["template_id", "template_version_id"],
            ["platform_template_versions.template_id", "platform_template_versions.id"],
            name="fk_template_rentals_template_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["template_id", "agreement_version_id"],
            ["rental_agreement_versions.template_id", "rental_agreement_versions.id"],
            name="fk_template_rentals_agreement_version",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["account_id", "agreement_version_id", "legal_acceptance_id"],
            [
                "legal_acceptances.account_id",
                "legal_acceptances.agreement_version_id",
                "legal_acceptances.id",
            ],
            name="fk_template_rentals_acceptance_owner",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "account_id"],
            ["tenant_memberships.tenant_id", "tenant_memberships.account_id"],
            name="fk_template_rentals_owner_membership",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_membership_id", "tenant_id", "account_id", "owner_membership_role"],
            [
                "tenant_memberships.id",
                "tenant_memberships.tenant_id",
                "tenant_memberships.account_id",
                "tenant_memberships.role",
            ],
            name="fk_template_rentals_exact_owner_membership",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "owner_membership_role = 'owner'",
            name="ck_template_rentals_owner_membership_role",
        ),
        CheckConstraint(
            "status IN ('awaiting_payment', 'expired')",
            name="ck_template_rentals_lifecycle_status",
        ),
        CheckConstraint(
            "status_changed_at >= created_at AND "
            "((status = 'awaiting_payment' AND expired_at IS NULL) OR "
            "(status = 'expired' AND expired_at IS NOT NULL "
            "AND status_changed_at = expired_at))",
            name="ck_template_rentals_lifecycle_timestamps",
        ),
        CheckConstraint(
            "reservation_expires_at > created_at",
            name="ck_template_rentals_reservation_expiry",
        ),
        CheckConstraint("price_cents > 0", name="ck_template_rentals_price_positive"),
        CheckConstraint("currency ~ '^[A-Z]{3}$'", name="ck_template_rentals_currency"),
        CheckConstraint(
            "billing_interval IN ('month', 'year')", name="ck_template_rentals_interval"
        ),
        CheckConstraint(
            "request_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_template_rentals_request_fingerprint",
        ),
        Index("ix_template_rentals_account_created", "account_id", "created_at"),
        Index(
            "ix_template_rentals_active_account_expiry",
            "account_id",
            "reservation_expires_at",
            postgresql_where=text("status = 'awaiting_payment'"),
        ),
        Index(
            "ix_template_rentals_due_expiry",
            "reservation_expires_at",
            "id",
            postgresql_where=text("status = 'awaiting_payment'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="RESTRICT"), index=True
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("platform_tenants.id", ondelete="RESTRICT"), index=True
    )
    template_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), index=True)
    template_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    agreement_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    legal_acceptance_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    owner_membership_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    owner_membership_role: Mapped[str] = mapped_column(
        String(24), default="owner", server_default="owner"
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    request_fingerprint: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(
        String(32), default="awaiting_payment", server_default="awaiting_payment", index=True
    )
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    billing_interval: Mapped[str] = mapped_column(String(16))
    reservation_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    status_changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PlatformAuditEvent(Base):
    __tablename__ = "platform_audit_events"
    __table_args__ = (
        CheckConstraint(
            "actor_type IN ('platform_account', 'system')",
            name="ck_platform_audit_events_actor_type",
        ),
        CheckConstraint(
            "outcome IN ('succeeded', 'denied', 'failed')",
            name="ck_platform_audit_events_outcome",
        ),
        CheckConstraint(
            "(actor_type = 'system' AND actor_account_id IS NULL) OR "
            "(actor_type = 'platform_account' AND actor_account_id IS NOT NULL)",
            name="ck_platform_audit_events_actor_binding",
        ),
        Index("ix_platform_audit_events_action_created", "action", "created_at"),
        Index("ix_platform_audit_events_resource", "resource_type", "resource_id"),
        Index(
            "uq_platform_audit_events_rental_expired",
            "resource_id",
            unique=True,
            postgresql_where=text(
                "resource_type = 'template_rental' "
                "AND action = 'template_rental.intent_expired'"
            ),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_type: Mapped[str] = mapped_column(String(32))
    actor_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("platform_accounts.id", ondelete="RESTRICT"), index=True
    )
    action: Mapped[str] = mapped_column(String(100), index=True)
    outcome: Mapped[str] = mapped_column(String(24))
    resource_type: Mapped[str | None] = mapped_column(String(64))
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    idempotency_key: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(
        JSONB, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
