import uuid
from datetime import date, datetime
from enum import StrEnum
from typing import Any

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class MaturityLevel(StrEnum):
    kids = "kids"
    teen = "teen"
    adult = "adult"


class HomepageMode(StrEnum):
    curated = "curated"
    no_algorithm = "no_algorithm"


class SystemRecord(Base):
    __tablename__ = "system_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    password_hash: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    profiles: Mapped[list["Profile"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    sessions: Mapped[list["DeviceSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    oauth_identities: Mapped[list["OAuthIdentity"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class OAuthIdentity(Base):
    __tablename__ = "oauth_identities"
    __table_args__ = (UniqueConstraint("provider", "subject", name="uq_oauth_provider_subject"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(32), index=True)
    subject: Mapped[str] = mapped_column(String(320))
    email_at_link: Mapped[str] = mapped_column(String(320))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped[User] = relationship(back_populates="oauth_identities")


class Profile(Base):
    __tablename__ = "profiles"
    __table_args__ = (Index("ix_profiles_user_name", "user_id", "name", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(50))
    avatar_key: Mapped[str | None] = mapped_column(String(200))
    maturity_level: Mapped[MaturityLevel] = mapped_column(
        Enum(MaturityLevel, name="maturity_level"), default=MaturityLevel.adult
    )
    language: Mapped[str] = mapped_column(String(16), default="en", server_default="en")
    is_kids: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    user: Mapped[User] = relationship(back_populates="profiles")
    preference: Mapped["ProfilePreference"] = relationship(
        back_populates="profile", cascade="all, delete-orphan", uselist=False
    )


class ProfilePreference(Base):
    __tablename__ = "profile_preferences"

    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), primary_key=True
    )
    autoplay_next: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    autoplay_previews: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    preferred_audio_language: Mapped[str | None] = mapped_column(String(16))
    preferred_subtitle_language: Mapped[str | None] = mapped_column(String(16))
    preferred_secondary_subtitle_language: Mapped[str | None] = mapped_column(String(16))
    subtitles_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    timezone: Mapped[str] = mapped_column(String(64), default="UTC", server_default="UTC")
    caption_size: Mapped[str] = mapped_column(String(16), default="medium", server_default="medium")
    caption_background: Mapped[str] = mapped_column(
        String(16), default="shadow", server_default="shadow"
    )
    caption_position: Mapped[str] = mapped_column(
        String(16), default="bottom", server_default="bottom"
    )
    cinephile_mode: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    rewatch_intelligence_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true"
    )
    analytics_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    consent_updated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    homepage_mode: Mapped[HomepageMode] = mapped_column(
        Enum(HomepageMode, name="homepage_mode"),
        default=HomepageMode.curated,
        server_default=HomepageMode.curated.value,
    )
    extra: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")

    profile: Mapped[Profile] = relationship(back_populates="preference")


class DeviceSession(Base):
    __tablename__ = "device_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    active_profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
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

    user: Mapped[User] = relationship(back_populates="sessions")


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    user: Mapped[User] = relationship()


class Admin(Base):
    __tablename__ = "admins"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list["AdminSession"]] = relationship(
        back_populates="admin", cascade="all, delete-orphan"
    )


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), index=True
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    admin: Mapped[Admin] = relationship(back_populates="sessions")


class AdminMfaRecoveryCode(Base):
    __tablename__ = "admin_mfa_recovery_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="CASCADE"), index=True
    )
    code_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_type: Mapped[str] = mapped_column(String(32), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), index=True)
    action: Mapped[str] = mapped_column(String(100), index=True)
    outcome: Mapped[str] = mapped_column(String(32))
    ip_address: Mapped[str | None] = mapped_column(String(64))
    detail: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class SiteBrandAsset(Base):
    __tablename__ = "site_brand_assets"
    __table_args__ = (
        CheckConstraint("byte_size > 0 AND byte_size <= 2097152", name="ck_site_brand_asset_size"),
        CheckConstraint(
            "width >= 64 AND width <= 4096 AND height >= 64 AND height <= 4096",
            name="ck_site_brand_asset_dimensions",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    content_type: Mapped[str] = mapped_column(String(32))
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    byte_size: Mapped[int] = mapped_column(Integer)
    width: Mapped[int] = mapped_column(Integer)
    height: Mapped[int] = mapped_column(Integer)
    revision: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SiteBrandConfiguration(Base):
    __tablename__ = "site_brand_configurations"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_site_brand_configuration_singleton"),
        CheckConstraint("revision >= 0", name="ck_site_brand_configuration_revision"),
        CheckConstraint(
            "published_revision IS NULL OR published_revision >= 0",
            name="ck_site_brand_configuration_published_revision",
        ),
        CheckConstraint(
            "current_step >= 1 AND current_step <= 5", name="ck_site_brand_current_step"
        ),
        CheckConstraint(
            "domains_revision >= 0", name="ck_site_brand_configuration_domains_revision"
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    owner_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), unique=True, index=True
    )
    draft_config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    published_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    published_revision: Mapped[int | None] = mapped_column(Integer)
    current_step: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    completed_steps: Mapped[list[int]] = mapped_column(JSON, default=list, server_default="[]")
    domains_revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    draft_logo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("site_brand_assets.id", ondelete="SET NULL")
    )
    published_logo_asset_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("site_brand_assets.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    owner_admin: Mapped[Admin] = relationship(foreign_keys=[owner_admin_id])
    draft_logo_asset: Mapped[SiteBrandAsset | None] = relationship(
        foreign_keys=[draft_logo_asset_id]
    )
    published_logo_asset: Mapped[SiteBrandAsset | None] = relationship(
        foreign_keys=[published_logo_asset_id]
    )
    domains: Mapped[list["SiteDomain"]] = relationship(
        back_populates="site_brand_configuration", cascade="all, delete-orphan"
    )


class ViewerPaymentConnection(Base):
    """Non-secret payment-provider state for one isolated Aperture tenant cell."""

    __tablename__ = "viewer_payment_connections"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_viewer_payment_connection_singleton"),
        CheckConstraint(
            "provider IN ('disabled', 'stripe_connect')",
            name="ck_viewer_payment_connection_provider",
        ),
        CheckConstraint(
            "access_mode IN ('free', 'subscription_required')",
            name="ck_viewer_payment_connection_access_mode",
        ),
        CheckConstraint("revision >= 0", name="ck_viewer_payment_connection_revision"),
        CheckConstraint(
            "access_mode <> 'subscription_required' OR charges_enabled",
            name="ck_viewer_payment_connection_subscription_requires_charges",
        ),
        CheckConstraint(
            "provider <> 'disabled' OR "
            "(stripe_connected_account_id IS NULL AND livemode IS NULL AND "
            "NOT details_submitted AND NOT charges_enabled AND NOT payouts_enabled)",
            name="ck_viewer_payment_connection_disabled_state",
        ),
        CheckConstraint(
            "provider <> 'stripe_connect' OR stripe_connected_account_id IS NOT NULL",
            name="ck_viewer_payment_connection_stripe_account",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1, server_default="1")
    owner_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), unique=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(32), default="disabled", server_default="disabled")
    access_mode: Mapped[str] = mapped_column(String(32), default="free", server_default="free")
    stripe_connected_account_id: Mapped[str | None] = mapped_column(String(255), unique=True)
    livemode: Mapped[bool | None] = mapped_column(Boolean)
    details_submitted: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    charges_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    payouts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    requirements_due: Mapped[list[str]] = mapped_column(JSON, default=list, server_default="[]")
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    owner_admin: Mapped[Admin] = relationship(foreign_keys=[owner_admin_id])


class LegalPolicyConfiguration(Base):
    __tablename__ = "legal_policy_configurations"
    __table_args__ = (
        CheckConstraint(
            "site_brand_configuration_id = 1",
            name="ck_legal_policy_configuration_single_site",
        ),
        CheckConstraint("revision >= 0", name="ck_legal_policy_configuration_revision"),
        CheckConstraint(
            "country_code IS NULL OR "
            "(length(country_code) = 2 AND country_code = upper(country_code))",
            name="ck_legal_policy_configuration_country_code",
        ),
        CheckConstraint(
            "minimum_user_age IS NULL OR minimum_user_age BETWEEN 0 AND 120",
            name="ck_legal_policy_configuration_minimum_user_age",
        ),
    )

    site_brand_configuration_id: Mapped[int] = mapped_column(
        ForeignKey("site_brand_configurations.id", ondelete="CASCADE"),
        primary_key=True,
        default=1,
        server_default="1",
    )
    legal_operator_name: Mapped[str | None] = mapped_column(String(200))
    country_code: Mapped[str | None] = mapped_column(String(2))
    region: Mapped[str | None] = mapped_column(String(120))
    support_email: Mapped[str | None] = mapped_column(String(320))
    privacy_email: Mapped[str | None] = mapped_column(String(320))
    copyright_email: Mapped[str | None] = mapped_column(String(320))
    minimum_user_age: Mapped[int | None] = mapped_column(Integer)
    governing_law_jurisdiction: Mapped[str | None] = mapped_column(String(200))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SiteDomainStatus(StrEnum):
    provisioning = "provisioning"
    pending_dns = "pending_dns"
    pending_tls = "pending_tls"
    pending_edge = "pending_edge"
    active = "active"
    failed = "failed"
    removing = "removing"


class SiteDomain(Base):
    __tablename__ = "site_domains"
    __table_args__ = (
        CheckConstraint("site_brand_configuration_id = 1", name="ck_site_domains_single_site"),
        CheckConstraint("hostname = lower(hostname)", name="ck_site_domains_lowercase_hostname"),
        CheckConstraint("right(hostname, 1) <> '.'", name="ck_site_domains_no_trailing_dot"),
        CheckConstraint("revision >= 0", name="ck_site_domains_revision"),
        CheckConstraint(
            "edge_published_revision IS NULL OR edge_published_revision >= 0",
            name="ck_site_domains_edge_published_revision",
        ),
        CheckConstraint(
            "status IN ('provisioning', 'pending_dns', 'pending_tls', 'pending_edge', "
            "'active', 'failed', 'removing')",
            name="ck_site_domains_status",
        ),
        CheckConstraint(
            "NOT is_primary OR status = 'active'", name="ck_site_domains_primary_active"
        ),
        Index(
            "uq_site_domains_primary",
            "site_brand_configuration_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    site_brand_configuration_id: Mapped[int] = mapped_column(
        ForeignKey("site_brand_configurations.id", ondelete="CASCADE"),
        default=1,
        server_default="1",
        index=True,
    )
    hostname: Mapped[str] = mapped_column(String(253), unique=True, index=True)
    status: Mapped[str] = mapped_column(
        String(32), default=SiteDomainStatus.provisioning, server_default="provisioning", index=True
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    provider: Mapped[str] = mapped_column(String(32))
    provider_hostname_id: Mapped[str | None] = mapped_column(String(64), unique=True)
    dns_records: Mapped[list[dict[str, str]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    failure_reason: Mapped[str | None] = mapped_column(String(64))
    revision: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    edge_published_revision: Mapped[int | None] = mapped_column(Integer)
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    site_brand_configuration: Mapped[SiteBrandConfiguration] = relationship(
        back_populates="domains"
    )


class AssetState(StrEnum):
    uploading = "uploading"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class MediaAsset(Base):
    __tablename__ = "media_assets"
    __table_args__ = (
        Index("ix_media_assets_state_created", "state", "created_at"),
        CheckConstraint(
            "upload_strategy IN ('single', 'multipart')",
            name="ck_media_assets_upload_strategy",
        ),
        CheckConstraint(
            "(upload_strategy = 'single' AND multipart_upload_id IS NULL "
            "AND multipart_part_size IS NULL) OR "
            "(upload_strategy = 'multipart' AND multipart_upload_id IS NOT NULL "
            "AND multipart_part_size >= 5242880)",
            name="ck_media_assets_multipart_fields",
        ),
        CheckConstraint(
            "malware_scan_status IN ('pending', 'scanning', 'clean', 'infected', 'error')",
            name="ck_media_assets_malware_scan_status",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("admins.id", ondelete="RESTRICT"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    media_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(BigInteger)
    checksum_sha256: Mapped[str] = mapped_column(String(64))
    storage_key: Mapped[str] = mapped_column(String(500), unique=True)
    state: Mapped[AssetState] = mapped_column(
        Enum(AssetState, name="asset_state"), default=AssetState.uploading, index=True
    )
    etag: Mapped[str | None] = mapped_column(String(128))
    failure_reason: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    upload_strategy: Mapped[str] = mapped_column(
        String(20), default="single", server_default="single"
    )
    multipart_upload_id: Mapped[str | None] = mapped_column(String(500))
    multipart_part_size: Mapped[int | None] = mapped_column(Integer)
    malware_scan_status: Mapped[str] = mapped_column(
        String(16), default="pending", server_default="pending"
    )
    malware_scan_engine: Mapped[str | None] = mapped_column(String(32))
    malware_scan_signature: Mapped[str | None] = mapped_column(String(200))
    malware_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ProcessingState(StrEnum):
    queued = "queued"
    probing = "probing"
    processing = "processing"
    validating = "validating"
    ready = "ready"
    failed = "failed"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"
    __table_args__ = (
        Index("ix_processing_jobs_state_created", "state", "created_at"),
        Index("ix_processing_jobs_lease_expiry", "lease_expires_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("media_assets.id", ondelete="CASCADE"), unique=True
    )
    state: Mapped[ProcessingState] = mapped_column(
        Enum(ProcessingState, name="processing_state"),
        default=ProcessingState.queued,
        index=True,
    )
    progress_percent: Mapped[int] = mapped_column(default=0, server_default="0")
    source_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    rendition_status: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    audio_tracks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    subtitle_tracks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    chapters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, server_default="[]")
    duration_seconds: Mapped[float | None]
    manifest_key: Mapped[str | None] = mapped_column(String(500))
    thumbnail_key: Mapped[str | None] = mapped_column(String(500))
    sprite_key: Mapped[str | None] = mapped_column(String(500))
    error_message: Mapped[str | None] = mapped_column(String(1000))
    attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    lease_owner: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    asset: Mapped[MediaAsset] = relationship()


class PlaybackSource(Base):
    __tablename__ = "playback_sources"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer = 1",
            name="ck_playback_sources_exactly_one_title",
        ),
        CheckConstraint(
            "intro_start_seconds IS NULL OR "
            "(intro_start_seconds >= 0 AND intro_end_seconds > intro_start_seconds)",
            name="ck_playback_sources_intro_range",
        ),
        CheckConstraint(
            "recap_start_seconds IS NULL OR "
            "(recap_start_seconds >= 0 AND recap_end_seconds > recap_start_seconds)",
            name="ck_playback_sources_recap_range",
        ),
        CheckConstraint(
            "credits_start_seconds IS NULL OR credits_start_seconds >= 0",
            name="ck_playback_sources_credits_start",
        ),
        CheckConstraint(
            "(processing_job_id IS NOT NULL)::integer + "
            "(external_manifest_url IS NOT NULL)::integer = 1",
            name="ck_playback_sources_exactly_one_origin",
        ),
        CheckConstraint(
            "external_manifest_url IS NULL OR "
            "(rights_basis IS NOT NULL AND rights_reference IS NOT NULL)",
            name="ck_playback_sources_external_rights_evidence",
        ),
        Index(
            "uq_playback_sources_legacy_movie",
            "movie_id",
            unique=True,
            postgresql_where=text("edition_id IS NULL AND movie_id IS NOT NULL"),
        ),
        Index(
            "uq_playback_sources_legacy_episode",
            "episode_id",
            unique=True,
            postgresql_where=text("edition_id IS NULL AND episode_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    processing_job_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("processing_jobs.id", ondelete="CASCADE"), unique=True
    )
    external_manifest_url: Mapped[str | None] = mapped_column(String(2000))
    external_format: Mapped[str | None] = mapped_column(String(16))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    rights_basis: Mapped[str | None] = mapped_column(String(500))
    rights_reference: Mapped[str | None] = mapped_column(String(500))
    rights_start_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    rights_end_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    allowed_territories: Mapped[list[str]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false", index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE")
    )
    edition_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("editions.id", ondelete="CASCADE"), unique=True, index=True
    )
    intro_start_seconds: Mapped[float | None] = mapped_column(Float)
    intro_end_seconds: Mapped[float | None] = mapped_column(Float)
    recap_start_seconds: Mapped[float | None] = mapped_column(Float)
    recap_end_seconds: Mapped[float | None] = mapped_column(Float)
    credits_start_seconds: Mapped[float | None] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    processing_job: Mapped[ProcessingJob | None] = relationship()


class WatchProgress(Base):
    __tablename__ = "watch_progress"
    __table_args__ = (
        UniqueConstraint(
            "profile_id", "playback_source_id", name="uq_watch_progress_profile_source"
        ),
        CheckConstraint("position_seconds >= 0", name="ck_watch_progress_position_nonnegative"),
        CheckConstraint("duration_seconds > 0", name="ck_watch_progress_duration_positive"),
        CheckConstraint(
            "percentage >= 0 AND percentage <= 100", name="ck_watch_progress_percentage"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    position_seconds: Mapped[float] = mapped_column(Float)
    duration_seconds: Mapped[float] = mapped_column(Float)
    percentage: Mapped[float] = mapped_column(Float)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    last_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ViewingActivity(Base):
    __tablename__ = "viewing_activities"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "playback_source_id",
            "activity_number",
            name="uq_viewing_activities_profile_source_number",
        ),
        CheckConstraint("activity_number > 0", name="ck_viewing_activity_number_positive"),
        CheckConstraint("watched_seconds >= 0", name="ck_viewing_activity_watched_nonnegative"),
        Index("ix_viewing_activities_profile_started", "profile_id", "started_at"),
        Index("ix_viewing_activities_profile_completed", "profile_id", "completed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    activity_number: Mapped[int] = mapped_column(Integer)
    is_rewatch: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    watched_seconds: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    completed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_watched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class SceneBookmark(Base):
    __tablename__ = "scene_bookmarks"
    __table_args__ = (
        CheckConstraint("timestamp_seconds >= 0", name="ck_scene_bookmarks_timestamp"),
        Index("ix_scene_bookmarks_profile_source", "profile_id", "playback_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), index=True
    )
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    title: Mapped[str] = mapped_column(String(180))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SceneNote(Base):
    __tablename__ = "scene_notes"
    __table_args__ = (
        CheckConstraint("timestamp_seconds >= 0", name="ck_scene_notes_timestamp"),
        Index("ix_scene_notes_profile_source", "profile_id", "playback_source_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    scene_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scenes.id", ondelete="SET NULL"), index=True
    )
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class AskMovieLog(Base):
    __tablename__ = "ask_movie_logs"
    __table_args__ = (
        CheckConstraint("timestamp_seconds >= 0", name="ck_ask_movie_logs_timestamp"),
        Index("ix_ask_movie_logs_profile_created", "profile_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    playback_source_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("playback_sources.id", ondelete="CASCADE"), index=True
    )
    version_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("scene_intelligence_versions.id", ondelete="SET NULL"), index=True
    )
    timestamp_seconds: Mapped[float] = mapped_column(Float)
    spoiler_mode: Mapped[str] = mapped_column(String(20))
    question_sha256: Mapped[str] = mapped_column(String(64))
    intent: Mapped[str] = mapped_column(String(50))
    outcome: Mapped[str] = mapped_column(String(30))
    provenance: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, server_default="[]"
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HomepageSource(StrEnum):
    pinned = "pinned"
    latest_movies = "latest_movies"
    latest_series = "latest_series"
    mixed = "mixed"


class HomepageConfiguration(Base):
    __tablename__ = "homepage_configurations"
    __table_args__ = (
        CheckConstraint(
            "(draft_hero_movie_id IS NOT NULL)::integer + "
            "(draft_hero_series_id IS NOT NULL)::integer <= 1",
            name="ck_homepage_configurations_one_draft_hero",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    draft_hero_movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="SET NULL")
    )
    draft_hero_series_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("series.id", ondelete="SET NULL")
    )
    published_snapshot: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    rails: Mapped[list["HomepageRail"]] = relationship(
        cascade="all, delete-orphan", order_by="HomepageRail.position"
    )


class HomepageRail(Base):
    __tablename__ = "homepage_rails"
    __table_args__ = (
        UniqueConstraint("configuration_id", "position", name="uq_homepage_rails_position"),
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_homepage_rails_schedule",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    configuration_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("homepage_configurations.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120))
    eyebrow: Mapped[str | None] = mapped_column(String(80))
    source: Mapped[HomepageSource] = mapped_column(
        Enum(HomepageSource, name="homepage_source"), default=HomepageSource.pinned
    )
    query: Mapped[str | None] = mapped_column(String(100))
    position: Mapped[int] = mapped_column(Integer)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    items: Mapped[list["HomepageItem"]] = relationship(
        cascade="all, delete-orphan", order_by="HomepageItem.position"
    )


class HomepageItem(Base):
    __tablename__ = "homepage_items"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (series_id IS NOT NULL)::integer = 1",
            name="ck_homepage_items_exactly_one_title",
        ),
        UniqueConstraint("rail_id", "position", name="uq_homepage_items_position"),
        UniqueConstraint("rail_id", "movie_id", name="uq_homepage_items_movie"),
        UniqueConstraint("rail_id", "series_id", name="uq_homepage_items_series"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    rail_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("homepage_rails.id", ondelete="CASCADE"), index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    series_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"))
    position: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingInterval(StrEnum):
    month = "month"
    year = "year"


class SubscriptionStatus(StrEnum):
    incomplete = "incomplete"
    trialing = "trialing"
    active = "active"
    past_due = "past_due"
    canceled = "canceled"
    expired = "expired"


class PaymentStatus(StrEnum):
    pending = "pending"
    succeeded = "succeeded"
    failed = "failed"
    refunded = "refunded"


class Plan(Base):
    __tablename__ = "plans"
    __table_args__ = (
        CheckConstraint("price_cents >= 0", name="ck_plans_price_nonnegative"),
        CheckConstraint("max_streams > 0", name="ck_plans_max_streams_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(String(500))
    price_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3), default="CAD", server_default="CAD")
    interval: Mapped[BillingInterval] = mapped_column(
        Enum(BillingInterval, name="billing_interval")
    )
    max_streams: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    max_resolution: Mapped[str] = mapped_column(String(16), default="1080p")
    is_active: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default="true", index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Subscription(Base):
    __tablename__ = "subscriptions"
    __table_args__ = (
        CheckConstraint(
            "current_period_start IS NULL OR current_period_end IS NULL OR "
            "current_period_end > current_period_start",
            name="ck_subscriptions_period",
        ),
        Index("ix_subscriptions_user_status", "user_id", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    plan_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("plans.id", ondelete="RESTRICT"))
    status: Mapped[SubscriptionStatus] = mapped_column(
        Enum(SubscriptionStatus, name="subscription_status"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    provider_customer_ref: Mapped[str | None] = mapped_column(String(255), index=True)
    provider_subscription_ref: Mapped[str | None] = mapped_column(String(255), unique=True)
    current_period_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    current_period_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    cancel_at_period_end: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    canceled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    plan: Mapped[Plan] = relationship()


class PaymentReference(Base):
    __tablename__ = "payment_references"
    __table_args__ = (CheckConstraint("amount_cents >= 0", name="ck_payments_amount_nonnegative"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64))
    external_reference: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[PaymentStatus] = mapped_column(Enum(PaymentStatus, name="payment_status"))
    amount_cents: Mapped[int] = mapped_column(Integer)
    currency: Mapped[str] = mapped_column(String(3))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class BillingWebhookEvent(Base):
    __tablename__ = "billing_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_event_id: Mapped[str] = mapped_column(String(255), unique=True)
    event_type: Mapped[str] = mapped_column(String(120), index=True)
    processed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Entitlement(Base):
    __tablename__ = "entitlements"
    __table_args__ = (
        CheckConstraint(
            "starts_at IS NULL OR ends_at IS NULL OR ends_at > starts_at",
            name="ck_entitlements_window",
        ),
        Index("ix_entitlements_user_key", "user_id", "key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    subscription_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("subscriptions.id", ondelete="CASCADE")
    )
    key: Mapped[str] = mapped_column(String(100))
    value: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    source: Mapped[str] = mapped_column(String(64))
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnalyticsEventType(StrEnum):
    impression = "impression"
    detail_open = "detail_open"
    play_start = "play_start"
    progress = "progress"
    pause = "pause"
    seek = "seek"
    completion = "completion"
    search = "search"
    search_click = "search_click"
    my_list = "my_list"
    rating = "rating"
    scenelens_open = "scenelens_open"
    ask_movie = "ask_movie"
    playback_startup = "playback_startup"
    playback_buffer = "playback_buffer"
    playback_error = "playback_error"
    quality_change = "quality_change"


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer <= 1",
            name="ck_analytics_events_one_title",
        ),
        CheckConstraint(
            "position_seconds IS NULL OR position_seconds >= 0", name="ck_analytics_position"
        ),
        CheckConstraint(
            "duration_seconds IS NULL OR duration_seconds > 0", name="ck_analytics_duration"
        ),
        CheckConstraint(
            "result_count IS NULL OR result_count >= 0", name="ck_analytics_result_count"
        ),
        Index("ix_analytics_events_type_occurred", "event_type", "occurred_at"),
        Index("ix_analytics_events_profile_occurred", "profile_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    profile_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("profiles.id", ondelete="CASCADE"), index=True
    )
    device_session_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("device_sessions.id", ondelete="CASCADE"), index=True
    )
    client_event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    dedupe_key: Mapped[str] = mapped_column(String(200), unique=True)
    event_type: Mapped[AnalyticsEventType] = mapped_column(
        Enum(AnalyticsEventType, name="analytics_event_type"), index=True
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("movies.id", ondelete="CASCADE"), index=True
    )
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE"), index=True
    )
    position_seconds: Mapped[float | None] = mapped_column(Float)
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    query: Mapped[str | None] = mapped_column(String(200))
    result_count: Mapped[int | None] = mapped_column(Integer)
    value: Mapped[float | None] = mapped_column(Float)
    properties: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, server_default="{}")
    is_bot: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


class AggregatedMetric(Base):
    __tablename__ = "aggregated_metrics"
    __table_args__ = (
        CheckConstraint(
            "(movie_id IS NOT NULL)::integer + (episode_id IS NOT NULL)::integer <= 1",
            name="ck_aggregated_metrics_one_title",
        ),
        UniqueConstraint(
            "day",
            "event_type",
            "movie_id",
            "episode_id",
            name="uq_aggregated_metrics_dimension",
            postgresql_nulls_not_distinct=True,
        ),
        Index("ix_aggregated_metrics_day_type", "day", "event_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    day: Mapped[date] = mapped_column(Date)
    event_type: Mapped[AnalyticsEventType] = mapped_column(
        Enum(AnalyticsEventType, name="analytics_event_type", create_type=False)
    )
    movie_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("movies.id", ondelete="CASCADE"))
    episode_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("episodes.id", ondelete="CASCADE")
    )
    event_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    unique_profiles: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    total_value: Mapped[float] = mapped_column(Float, default=0, server_default="0")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# Import catalog mappings so Alembic and metadata discovery see the complete domain.
from app import catalog_models as catalog_models  # noqa: E402, F401
from app import club_models as club_models  # noqa: E402, F401
from app import community_models as community_models  # noqa: E402, F401
from app import curation_models as curation_models  # noqa: E402, F401
from app import explore_models as explore_models  # noqa: E402, F401
from app import scene_models as scene_models  # noqa: E402, F401
