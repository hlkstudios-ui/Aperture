import hashlib
import json
import uuid
from datetime import UTC, datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import select
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


def rental_response(db: Session, rental: TemplateRental) -> TemplateRentalResponse:
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
        created_at=rental.created_at,
    )


def _existing_rental(
    db: Session,
    account_id: uuid.UUID,
    idempotency_key: uuid.UUID,
) -> TemplateRental | None:
    return db.scalar(
        select(TemplateRental).where(
            TemplateRental.account_id == account_id,
            TemplateRental.idempotency_key == idempotency_key,
        )
    )


def create_rental_intent(
    db: Session,
    request: Request,
    account: PlatformAccount,
    idempotency_key: uuid.UUID,
    payload: RentalIntentCreate,
) -> tuple[TemplateRentalResponse, bool]:
    fingerprint = request_fingerprint(payload)
    existing = _existing_rental(db, account.id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency key was already used with different rental details",
            )
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
    existing = _existing_rental(db, account.id, idempotency_key)
    if existing is not None:
        if existing.request_fingerprint != fingerprint:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Idempotency key was already used with different rental details",
            )
        return rental_response(db, existing), True
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
        select(TenantReservation.id).where(TenantReservation.slug == payload.requested_tenant_slug)
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Requested tenant slug is unavailable")

    now = datetime.now(UTC)
    tenant_id = uuid.uuid4()
    acceptance_id = uuid.uuid4()
    rental_id = uuid.uuid4()
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
        account_id=account.id,
        agreement_version_id=agreement.id,
        agreement_content_sha256=agreement.content_sha256,
        accepted_at=now,
        ip_address=request.client.host[:64] if request.client else None,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
    )
    rental = TemplateRental(
        id=rental_id,
        account_id=account.id,
        tenant_id=tenant.id,
        template_id=template.id,
        template_version_id=version.id,
        agreement_version_id=agreement.id,
        legal_acceptance_id=acceptance.id,
        idempotency_key=idempotency_key,
        request_fingerprint=fingerprint,
        status="awaiting_payment",
        price_cents=template.rental_price_cents,
        currency=template.rental_currency,
        billing_interval=template.rental_interval,
    )
    membership = TenantMembership(
        tenant_id=tenant.id,
        account_id=account.id,
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
                    actor_account_id=account.id,
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
                    },
                ),
            ]
        )
        db.commit()
    except IntegrityError:
        db.rollback()
        concurrent = _existing_rental(db, account.id, idempotency_key)
        if concurrent is not None:
            if concurrent.request_fingerprint != fingerprint:
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    "Idempotency key was already used with different rental details",
                ) from None
            return rental_response(db, concurrent), True
        if db.scalar(
            select(TenantReservation.id).where(
                TenantReservation.slug == payload.requested_tenant_slug
            )
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "Requested tenant slug is unavailable",
            ) from None
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Rental intent conflicted with another request",
        ) from None
    db.refresh(rental)
    return rental_response(db, rental), False
