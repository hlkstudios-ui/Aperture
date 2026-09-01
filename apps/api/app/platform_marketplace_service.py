import hashlib
import json
import math
import uuid
from datetime import UTC, datetime, timedelta

from fastapi import HTTPException, Request, status
from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import get_settings
from app.platform_models import (
    LegalAcceptance,
    PlatformAccount,
    PlatformAuditEvent,
    PlatformTemplate,
    PlatformTemplateVersion,
    RentalAgreementVersion,
    TemplateRental,
    TenantMembership,
    TenantReservation,
)
from app.platform_schemas import (
    PlatformTemplateDetail,
    PlatformTemplatePricing,
    PlatformTemplateSummary,
    PlatformTemplateVersionPublic,
    RentalAcceptanceResponse,
    RentalAgreementPublic,
    RentalIntentCreate,
    RentalTemplateResponse,
    RentalTenantResponse,
    TemplateRentalResponse,
)

RESERVED_TENANT_SLUGS = frozenset(
    {
        "admin",
        "api",
        "app",
        "aperture",
        "apertures",
        "cdn",
        "customers",
        "mail",
        "media",
        "origin",
        "platform",
        "smtp",
        "status",
        "storage",
        "studio",
        "support",
        "www",
    }
)
EXPECTED_RENTAL_CONFLICT_CONSTRAINTS = frozenset(
    {
        "uq_template_rentals_idempotency",
        "uq_platform_tenants_active_slug",
        "uq_platform_tenants_active_hostname",
    }
)


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    value = getattr(diagnostics, "constraint_name", None)
    return value if isinstance(value, str) else None


def request_fingerprint(payload: RentalIntentCreate) -> str:
    canonical = json.dumps(
        payload.model_dump(mode="json"),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def _version(db: Session, template: PlatformTemplate) -> PlatformTemplateVersion | None:
    if template.current_version_id is None:
        return None
    return db.scalar(
        select(PlatformTemplateVersion).where(
            PlatformTemplateVersion.id == template.current_version_id,
            PlatformTemplateVersion.template_id == template.id,
        )
    )


def _agreement(db: Session, template: PlatformTemplate) -> RentalAgreementVersion | None:
    if template.current_agreement_version_id is None:
        return None
    return db.scalar(
        select(RentalAgreementVersion).where(
            RentalAgreementVersion.id == template.current_agreement_version_id,
            RentalAgreementVersion.template_id == template.id,
        )
    )


def _publication(
    db: Session,
    template: PlatformTemplate,
) -> tuple[PlatformTemplateVersion | None, RentalAgreementVersion | None, bool]:
    version = _version(db, template)
    agreement = _agreement(db, template)
    now = datetime.now(UTC)
    content_hash_valid = bool(
        agreement
        and hashlib.sha256(agreement.content.encode()).hexdigest() == agreement.content_sha256
    )
    available = bool(
        template.status == "published"
        and version is not None
        and agreement is not None
        and version.published_at <= now
        and agreement.published_at <= now
        and content_hash_valid
        and template.rental_price_cents is not None
        and template.rental_currency is not None
        and template.rental_interval is not None
    )
    return version, agreement, available


def template_response(
    db: Session,
    template: PlatformTemplate,
    *,
    detail: bool,
) -> PlatformTemplateSummary | PlatformTemplateDetail:
    version, agreement, available = _publication(db, template)
    version_response = (
        PlatformTemplateVersionPublic(
            id=version.id,
            version=version.version,
            feature_manifest=version.feature_manifest,
            configuration_schema=version.configuration_schema,
        )
        if version is not None and version.published_at <= datetime.now(UTC)
        else None
    )
    pricing = (
        PlatformTemplatePricing(
            price_cents=template.rental_price_cents,
            currency=template.rental_currency,
            interval=template.rental_interval,
        )
        if template.rental_price_cents is not None
        and template.rental_currency is not None
        and template.rental_interval is not None
        else None
    )
    values = {
        "id": template.id,
        "slug": template.slug,
        "name": template.name,
        "description": template.description,
        "category": template.category,
        "thumbnail_url": template.thumbnail_url,
        "preview_assets": template.preview_assets,
        "demo_url": template.demo_url,
        "status": template.status,
        "current_version": version_response,
        "starting_price": pricing,
        "rental_available": available,
        "unavailable_reason": None if available else "Template rental is not available yet.",
    }
    if not detail:
        return PlatformTemplateSummary(**values)
    agreement_response = (
        RentalAgreementPublic(
            id=agreement.id,
            version=agreement.version,
            title=agreement.title,
            content=agreement.content,
            content_sha256=agreement.content_sha256,
            published_at=agreement.published_at,
        )
        if agreement is not None
        and agreement.published_at <= datetime.now(UTC)
        and hashlib.sha256(agreement.content.encode()).hexdigest() == agreement.content_sha256
        else None
    )
    return PlatformTemplateDetail(**values, rental_agreement=agreement_response)


def rental_response(
    db: Session,
    rental: TemplateRental,
) -> TemplateRentalResponse:
    tenant = db.get(TenantReservation, rental.tenant_id)
    template = db.get(PlatformTemplate, rental.template_id)
    version = db.get(PlatformTemplateVersion, rental.template_version_id)
    agreement = db.get(RentalAgreementVersion, rental.agreement_version_id)
    acceptance = db.get(LegalAcceptance, rental.legal_acceptance_id)
    if any(item is None for item in (tenant, template, version, agreement, acceptance)):
        raise RuntimeError("Platform rental references are incomplete")
    assert tenant is not None
    assert template is not None
    assert version is not None
    assert agreement is not None
    assert acceptance is not None
    if rental.status == "expired" and tenant.status != "released":
        raise RuntimeError("Expired platform rental has an active tenant reservation")
    if rental.status == "awaiting_payment" and tenant.status != "reserved":
        raise RuntimeError("Active platform rental has a released tenant reservation")
    return TemplateRentalResponse(
        id=rental.id,
        status=rental.status,
        tenant=RentalTenantResponse(
            id=tenant.id,
            slug=tenant.slug,
            business_name=tenant.business_name,
            hosted_hostname=tenant.hosted_hostname,
            status=tenant.status,
        ),
        template=RentalTemplateResponse(
            id=template.id,
            slug=template.slug,
            name=template.name,
            version_id=version.id,
            version=version.version,
        ),
        price_snapshot=PlatformTemplatePricing(
            price_cents=rental.price_cents,
            currency=rental.currency,
            interval=rental.billing_interval,
        ),
        legal_acceptance=RentalAcceptanceResponse(
            id=acceptance.id,
            agreement_version_id=agreement.id,
            version=agreement.version,
            content_sha256=acceptance.agreement_content_sha256,
            accepted_at=acceptance.accepted_at,
        ),
        next_action=(
            "start_new_rental_request"
            if rental.status == "expired"
            else "platform_billing_unavailable"
        ),
        reservation_active=rental.status == "awaiting_payment",
        reservation_expires_at=rental.reservation_expires_at,
        status_changed_at=rental.status_changed_at,
        expired_at=rental.expired_at,
        created_at=rental.created_at,
    )


def _existing_rental(
    db: Session,
    account_id: uuid.UUID,
    idempotency_key: uuid.UUID,
) -> TemplateRental | None:
    return db.scalar(
        select(TemplateRental)
        .where(
            TemplateRental.account_id == account_id,
            TemplateRental.idempotency_key == idempotency_key,
        )
        .with_for_update()
    )


def _database_now(db: Session) -> datetime:
    now = db.scalar(select(func.transaction_timestamp()))
    if not isinstance(now, datetime):
        raise RuntimeError("Database clock is unavailable")
    return now


def _expire_rental(
    db: Session,
    rental: TemplateRental,
    *,
    now: datetime,
) -> bool:
    if rental.status != "awaiting_payment" or rental.reservation_expires_at > now:
        return False
    tenant = db.scalar(
        select(TenantReservation)
        .where(TenantReservation.id == rental.tenant_id)
        .with_for_update()
    )
    membership = db.scalar(
        select(TenantMembership)
        .where(
            TenantMembership.id == rental.owner_membership_id,
            TenantMembership.tenant_id == rental.tenant_id,
            TenantMembership.account_id == rental.account_id,
            TenantMembership.role == "owner",
        )
        .with_for_update()
    )
    if tenant is None or membership is None:
        raise RuntimeError("Rental expiry references are incomplete")
    if tenant.status != "reserved" or membership.status != "active":
        raise RuntimeError("Rental expiry lifecycle is inconsistent")
    rental.status = "expired"
    rental.status_changed_at = now
    rental.expired_at = now
    tenant.status = "released"
    tenant.released_at = now
    tenant.release_reason = "expired"
    membership.status = "released"
    db.add(
        PlatformAuditEvent(
            actor_type="system",
            actor_account_id=None,
            action="template_rental.intent_expired",
            outcome="succeeded",
            resource_type="template_rental",
            resource_id=rental.id,
            idempotency_key=rental.idempotency_key,
            detail={
                "schema_version": 1,
                "tenant_id": str(tenant.id),
                "status": "expired",
            },
        )
    )
    return True


def reconcile_expired_rental_intents(
    db: Session,
    *,
    limit: int = 100,
    account_id: uuid.UUID | None = None,
    tenant_slug: str | None = None,
    now: datetime | None = None,
    skip_locked: bool = True,
) -> int:
    if not 1 <= limit <= 500:
        raise ValueError("Expiry reconciliation limit must be between 1 and 500")
    observed_at = now or _database_now(db)
    statement = (
        select(TemplateRental)
        .join(TenantReservation, TenantReservation.id == TemplateRental.tenant_id)
        .where(
            TemplateRental.status == "awaiting_payment",
            TemplateRental.reservation_expires_at <= observed_at,
        )
    )
    filters = []
    if account_id is not None:
        filters.append(TemplateRental.account_id == account_id)
    if tenant_slug is not None:
        filters.append(TenantReservation.slug == tenant_slug)
    if filters:
        statement = statement.where(or_(*filters))
    rentals = list(
        db.scalars(
            statement.order_by(
                TemplateRental.reservation_expires_at,
                TemplateRental.id,
            )
            .limit(limit)
            .with_for_update(of=TemplateRental, skip_locked=skip_locked)
        )
    )
    return sum(_expire_rental(db, rental, now=observed_at) for rental in rentals)


def _quota_error(db: Session, account: PlatformAccount, now: datetime) -> HTTPException:
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(TemplateRental)
            .where(
                TemplateRental.account_id == account.id,
                TemplateRental.status == "awaiting_payment",
                TemplateRental.reservation_expires_at > now,
            )
        )
        or 0
    )
    if active_count < account.active_unpaid_reservation_limit:
        raise RuntimeError("Quota error was requested while capacity remained")
    earliest = db.scalar(
        select(func.min(TemplateRental.reservation_expires_at)).where(
            TemplateRental.account_id == account.id,
            TemplateRental.status == "awaiting_payment",
            TemplateRental.reservation_expires_at > now,
        )
    )
    retry_after = (
        max(1, math.ceil((earliest - now).total_seconds()))
        if isinstance(earliest, datetime)
        else 3600
    )
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        detail={
            "code": "active_unpaid_reservation_quota_exceeded",
            "message": "Complete or let the active rental request expire before starting another.",
            "limit": account.active_unpaid_reservation_limit,
            "active_count": active_count,
        },
        headers={"Retry-After": str(min(retry_after, 604800))},
    )


def create_rental_intent(
    db: Session,
    request: Request,
    account: PlatformAccount,
    idempotency_key: uuid.UUID,
    payload: RentalIntentCreate,
) -> tuple[TemplateRentalResponse, bool]:
    fingerprint = request_fingerprint(payload)
    locked_account = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_account is None or not locked_account.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform account is unavailable")
    if locked_account.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "platform_email_verification_required",
                "message": "Verify the platform account email before reserving a template.",
            },
        )
    account_id = locked_account.id
    now = _database_now(db)
    existing = _existing_rental(db, account_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency key was already used with different rental details",
            )
        if _expire_rental(db, existing, now=now):
            db.commit()
        return rental_response(db, existing), True

    if payload.requested_tenant_slug in RESERVED_TENANT_SLUGS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Requested tenant slug is reserved")

    template = db.scalar(
        select(PlatformTemplate)
        .where(PlatformTemplate.slug == payload.template_slug)
        .with_for_update()
    )
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template was not found")
    # The template row serializes offers for this template. A concurrent request may have
    # committed while this transaction waited for the lock, so resolve the idempotency record
    # again before treating its now-reserved slug as a conflict.
    reconcile_expired_rental_intents(
        db,
        account_id=account_id,
        tenant_slug=payload.requested_tenant_slug,
        now=now,
        skip_locked=False,
    )
    db.flush()
    existing = _existing_rental(db, account_id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency key was already used with different rental details",
            )
        if _expire_rental(db, existing, now=now):
            db.commit()
        return rental_response(db, existing), True
    active_count = (
        db.scalar(
            select(func.count())
            .select_from(TemplateRental)
            .where(
                TemplateRental.account_id == account_id,
                TemplateRental.status == "awaiting_payment",
                TemplateRental.reservation_expires_at > now,
            )
        )
        or 0
    )
    if active_count >= locked_account.active_unpaid_reservation_limit:
        raise _quota_error(db, locked_account, now)
    version, agreement, available = _publication(db, template)
    if not available or version is None or agreement is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Template is not available for rent")
    if template.current_version_id != payload.template_version_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Template version changed; review the current rental offer",
        )
    if (
        template.current_agreement_version_id != payload.agreement_version_id
        or agreement.version != payload.agreement_version
        or agreement.content_sha256 != payload.agreement_sha256
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Rental agreement changed; review and accept the current terms",
        )
    if db.scalar(
        select(TenantReservation.id).where(
            TenantReservation.slug == payload.requested_tenant_slug,
            TenantReservation.status == "reserved",
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Requested tenant slug is unavailable")

    tenant_id = uuid.uuid4()
    acceptance_id = uuid.uuid4()
    rental_id = uuid.uuid4()
    membership_id = uuid.uuid4()
    hosted_hostname = (
        f"{payload.requested_tenant_slug}.{get_settings().platform_tenant_base_domain}"
    )
    if len(hosted_hostname) > 253:
        raise RuntimeError("Configured tenant base domain produces an invalid hostname")
    tenant = TenantReservation(
        id=tenant_id,
        slug=payload.requested_tenant_slug,
        hosted_hostname=hosted_hostname,
        business_name=payload.business_name,
        status="reserved",
    )
    acceptance = LegalAcceptance(
        id=acceptance_id,
        account_id=account_id,
        agreement_version_id=agreement.id,
        agreement_content_sha256=agreement.content_sha256,
        accepted_at=now,
        ip_address=request.client.host[:64] if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
    rental = TemplateRental(
        id=rental_id,
        account_id=account_id,
        tenant_id=tenant.id,
        template_id=template.id,
        template_version_id=version.id,
        agreement_version_id=agreement.id,
        legal_acceptance_id=acceptance.id,
        owner_membership_id=membership_id,
        owner_membership_role="owner",
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        status="awaiting_payment",
        price_cents=template.rental_price_cents,
        currency=template.rental_currency,
        billing_interval=template.rental_interval,
        reservation_expires_at=now
        + timedelta(hours=get_settings().platform_rental_intent_hours),
        status_changed_at=now,
        created_at=now,
    )
    membership = TenantMembership(
        id=membership_id,
        tenant_id=tenant.id,
        account_id=account_id,
        role="owner",
        status="active",
    )
    db.add_all([tenant, acceptance])
    try:
        # These rows are prerequisites for the rental's restrictive foreign keys. Explicitly
        # flush them in the same transaction because the models intentionally expose no writable
        # ORM relationships that could otherwise direct unit-of-work ordering.
        db.flush()
        db.add(membership)
        db.flush()
        db.add_all(
            [
                rental,
                PlatformAuditEvent(
                    actor_type="platform_account",
                    actor_account_id=account_id,
                    action="template_rental.intent_created",
                    outcome="succeeded",
                    resource_type="template_rental",
                    resource_id=rental.id,
                    idempotency_key=idempotency_key,
                    ip_address=request.client.host[:64] if request.client else None,
                    detail={
                        "schema_version": 1,
                        "tenant_id": str(tenant.id),
                        "template_id": str(template.id),
                        "template_version_id": str(version.id),
                        "agreement_version_id": str(agreement.id),
                        "status": "awaiting_payment",
                        "reservation_expires_at": rental.reservation_expires_at.isoformat(),
                    },
                ),
            ]
        )
        db.commit()
    except IntegrityError as error:
        constraint_name = _constraint_name(error)
        db.rollback()
        if constraint_name not in EXPECTED_RENTAL_CONFLICT_CONSTRAINTS:
            raise
        if constraint_name == "uq_template_rentals_idempotency":
            concurrent = _existing_rental(db, account_id, idempotency_key)
            if concurrent is None:
                raise
            if concurrent.request_fingerprint != fingerprint:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Idempotency key was already used with different rental details",
                ) from None
            return rental_response(db, concurrent), True
        if constraint_name in {
            "uq_platform_tenants_active_slug",
            "uq_platform_tenants_active_hostname",
        }:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Requested tenant slug is unavailable",
            ) from None
        raise
    db.refresh(rental)
    return rental_response(db, rental), False
