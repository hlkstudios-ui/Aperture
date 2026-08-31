from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.config import Settings, get_settings
from app.custom_domain_provider import (
    CloudflareCustomHostnamesClient,
    DomainProviderError,
    DomainProviderNotFound,
)
from app.models import Admin, AuditLog, SiteBrandConfiguration, SiteDomain, SiteDomainStatus
from app.site_brand_service import get_or_claim_configuration
from app.site_domain_schemas import (
    SiteDomainCollectionResponse,
    SiteDomainCreateRequest,
    SiteDomainMutationRequest,
    SiteDomainPublicResponse,
)
from app.site_domain_service import (
    apply_provider_hostname,
    collection_response,
    get_owned_domain,
    normalize_hostname,
    preferred_public_origin,
    sync_activation_edge_allowlist,
    sync_active_edge_allowlist,
    turnstile_required_hostnames,
    validate_custom_hostname,
)

public_router = APIRouter(prefix="/site/domain", tags=["site domain"])
router = APIRouter(
    prefix="/admin/site/domains",
    tags=["administrator site domains"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


@public_router.get("", response_model=SiteDomainPublicResponse)
def get_public_site_domain(
    response: Response, db: DbSession
) -> SiteDomainPublicResponse:
    response.headers["Cache-Control"] = "public, max-age=60, stale-while-revalidate=300"
    return SiteDomainPublicResponse(primary_origin=preferred_public_origin(db))


def _audit(
    db: DbSession,
    request: Request,
    admin: Admin,
    action: str,
    detail: dict[str, Any] | None = None,
    *,
    outcome: str = "succeeded",
) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome=outcome,
            ip_address=request.client.host if request.client else None,
            detail=detail or {},
        )
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store, max-age=0, must-revalidate"
    response.headers["Pragma"] = "no-cache"


def _configuration(
    db: DbSession, request: Request, admin: Admin
) -> SiteBrandConfiguration:
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
        db.commit()
        db.refresh(configuration)
    return configuration


def _provider() -> tuple[CloudflareCustomHostnamesClient, Settings, str]:
    settings = get_settings()
    if not settings.custom_domains_available:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Custom domains are not configured",
        )
    try:
        cname_target = normalize_hostname(settings.custom_domain_cname_target or "")
        provider = CloudflareCustomHostnamesClient.from_settings(settings)
    except ValueError as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Custom domains are not configured",
        ) from error
    return provider, settings, cname_target


def _lock_configuration(
    db: DbSession, configuration: SiteBrandConfiguration
) -> SiteBrandConfiguration:
    locked = db.scalar(
        select(SiteBrandConfiguration)
        .where(SiteBrandConfiguration.id == configuration.id)
        .execution_options(populate_existing=True)
        .with_for_update()
    )
    if locked is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Site configuration changed")
    return locked


def _check_revision(domain: SiteDomain, expected: int) -> None:
    if domain.revision != expected:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Custom domain changed; reload before trying again",
        )


def _provider_failure() -> HTTPException:
    return HTTPException(
        status.HTTP_503_SERVICE_UNAVAILABLE,
        "The custom domain provider is temporarily unavailable",
    )


def _compensate_created_hostname(
    provider: CloudflareCustomHostnamesClient, provider_hostname_id: str
) -> None:
    try:
        provider.delete_hostname(provider_hostname_id)
    except Exception:
        # Compensation must never replace the persistence error that caused it.
        pass


def _record_provider_failure(
    db: DbSession,
    configuration: SiteBrandConfiguration,
    domain: SiteDomain,
    error: DomainProviderError,
    request: Request,
    admin: Admin,
    action: str,
    *,
    fail_domain: bool = False,
) -> None:
    if fail_domain:
        domain.status = SiteDomainStatus.failed
        domain.is_primary = False
    domain.failure_reason = error.code
    domain.last_checked_at = datetime.now(UTC)
    domain.revision += 1
    configuration.domains_revision += 1
    _audit(
        db,
        request,
        admin,
        action,
        {"domain_id": str(domain.id), "hostname": domain.hostname, "reason": error.code},
        outcome="failed",
    )
    db.commit()


def _activate_pending_domain(
    db: DbSession,
    configuration: SiteBrandConfiguration,
    domain: SiteDomain,
    provider: CloudflareCustomHostnamesClient,
    request: Request,
    admin: Admin,
) -> None:
    configuration = _lock_configuration(db, configuration)
    domain = get_owned_domain(db, domain.id, for_update=True)
    if domain.status != SiteDomainStatus.pending_edge:
        return

    settings = get_settings()
    if settings.captcha_required:
        try:
            provider.reconcile_turnstile_domains(
                required=turnstile_required_hostnames(
                    db, include={domain.hostname}
                )
            )
        except DomainProviderError as error:
            domain.failure_reason = error.code
            domain.last_checked_at = datetime.now(UTC)
            domain.revision += 1
            configuration.domains_revision += 1
            _audit(
                db,
                request,
                admin,
                "site_domain.turnstile_activation",
                {
                    "domain_id": str(domain.id),
                    "hostname": domain.hostname,
                    "reason": error.code,
                },
                outcome="failed",
            )
            db.commit()
            raise _provider_failure() from error

    # Keep the candidate pending until existing aliases and then the candidate are admitted.
    configuration.domains_revision += 1
    try:
        sync_activation_edge_allowlist(db, configuration, domain, provider)
    except DomainProviderError as error:
        compensation_failed = False
        try:
            provider.delete_domain_allowlist(domain.hostname)
        except DomainProviderError:
            compensation_failed = True
        domain.status = SiteDomainStatus.pending_edge
        domain.activated_at = None
        domain.edge_published_revision = None
        domain.failure_reason = (
            "edge_reconciliation_required" if compensation_failed else error.code
        )
        domain.revision += 1
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_activation",
            {
                "domain_id": str(domain.id),
                "hostname": domain.hostname,
                "reason": domain.failure_reason,
            },
            outcome="failed",
        )
        db.commit()
        if compensation_failed:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Edge admission could not be confirmed; reconciliation is required",
            ) from error
        raise _provider_failure() from error
    domain.status = SiteDomainStatus.active
    domain.activated_at = domain.activated_at or datetime.now(UTC)
    domain.failure_reason = None
    domain.revision += 1
    _audit(
        db,
        request,
        admin,
        "site_domain.activated",
        {"domain_id": str(domain.id), "hostname": domain.hostname},
    )
    try:
        db.commit()
    except Exception:
        db.rollback()
        compensation_failed = False
        try:
            provider.delete_domain_allowlist(domain.hostname)
        except Exception:
            compensation_failed = True
        try:
            configuration = _lock_configuration(db, configuration)
            domain = get_owned_domain(db, domain.id, for_update=True)
            domain.status = SiteDomainStatus.pending_edge
            domain.activated_at = None
            domain.edge_published_revision = None
            domain.failure_reason = (
                "edge_reconciliation_required"
                if compensation_failed
                else "activation_persistence_failed"
            )
            domain.revision += 1
            configuration.domains_revision += 1
            _audit(
                db,
                request,
                admin,
                "site_domain.activation_persistence",
                {
                    "domain_id": str(domain.id),
                    "hostname": domain.hostname,
                    "reason": domain.failure_reason,
                },
                outcome="failed",
            )
            db.commit()
        except Exception:
            db.rollback()
        raise


def _sync_after_refresh(
    db: DbSession,
    configuration: SiteBrandConfiguration,
    domain: SiteDomain,
    provider: CloudflareCustomHostnamesClient,
    previous_status: str,
    request: Request,
    admin: Admin,
) -> None:
    if domain.status == SiteDomainStatus.pending_edge:
        _activate_pending_domain(db, configuration, domain, provider, request, admin)
        return
    try:
        if domain.status != SiteDomainStatus.active:
            provider.delete_domain_allowlist(domain.hostname)
        sync_active_edge_allowlist(db, configuration, provider)
    except DomainProviderError as error:
        domain.failure_reason = error.code
        domain.revision += 1
        configuration.domains_revision += 1
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {
                "domain_id": str(domain.id),
                "hostname": domain.hostname,
                "previous_status": previous_status,
                "reason": error.code,
            },
            outcome="failed",
        )
        db.commit()
        raise _provider_failure() from error
    db.commit()


@router.get("", response_model=SiteDomainCollectionResponse)
def list_site_domains(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    return collection_response(db, configuration)


@router.post(
    "",
    response_model=SiteDomainCollectionResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_site_domain(
    payload: SiteDomainCreateRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    provider, settings, cname_target = _provider()
    try:
        hostname = validate_custom_hostname(payload.hostname, settings)
    except ValueError as error:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(error)) from error
    configuration = _lock_configuration(db, configuration)
    existing = db.scalar(select(SiteDomain).where(SiteDomain.hostname == hostname))
    if existing is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Custom domain already exists")
    domain_count = db.scalar(select(func.count(SiteDomain.id))) or 0
    if domain_count >= settings.custom_domain_max_per_site:
        raise HTTPException(status.HTTP_409_CONFLICT, "Custom domain limit was reached")

    domain = SiteDomain(
        id=uuid.uuid4(),
        site_brand_configuration_id=configuration.id,
        hostname=hostname,
        provider="cloudflare",
        status=SiteDomainStatus.provisioning,
        revision=0,
        dns_records=[],
    )
    db.add(domain)
    configuration.domains_revision += 1
    _audit(
        db,
        request,
        admin,
        "site_domain.created",
        {"domain_id": str(domain.id), "hostname": hostname},
    )
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Custom domain already exists") from error

    configuration = _lock_configuration(db, configuration)
    domain = get_owned_domain(db, domain.id, for_update=True)
    try:
        provider_hostname = provider.create_hostname(hostname)
    except DomainProviderError as error:
        _record_provider_failure(
            db,
            configuration,
            domain,
            error,
            request,
            admin,
            "site_domain.provisioning",
            fail_domain=True,
        )
        raise _provider_failure() from error

    try:
        apply_provider_hostname(domain, provider_hostname, cname_target)
        configuration.domains_revision += 1
        db.commit()
    except Exception:
        db.rollback()
        _compensate_created_hostname(provider, provider_hostname.id)
        raise
    _activate_pending_domain(db, configuration, domain, provider, request, admin)
    return collection_response(db, configuration)


@router.post("/reconcile", response_model=SiteDomainCollectionResponse)
def reconcile_site_domains(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    provider, settings, _ = _provider()
    configuration = _lock_configuration(db, configuration)
    domains = list(db.scalars(select(SiteDomain).order_by(SiteDomain.hostname)))
    try:
        for domain in domains:
            if domain.status != SiteDomainStatus.active:
                provider.delete_domain_allowlist(domain.hostname)
        if settings.captcha_required:
            nonactive_hostnames = {
                domain.hostname
                for domain in domains
                if domain.status != SiteDomainStatus.active
            }
            provider.reconcile_turnstile_domains(
                required=turnstile_required_hostnames(db),
                remove=nonactive_hostnames,
            )
        sync_active_edge_allowlist(db, configuration, provider)
    except DomainProviderError as error:
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {"reason": error.code},
            outcome="failed",
        )
        db.commit()
        raise _provider_failure() from error
    for domain in domains:
        if domain.status != SiteDomainStatus.active:
            domain.failure_reason = None
    _audit(db, request, admin, "site_domain.edge_reconciliation", {"domain_count": len(domains)})
    db.commit()
    return collection_response(db, configuration)


@router.post("/use-platform", response_model=SiteDomainCollectionResponse)
def use_platform_as_primary(
    payload: SiteDomainMutationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _lock_configuration(db, _configuration(db, request, admin))
    if configuration.domains_revision != payload.revision:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Custom domains changed; reload before trying again",
        )
    current_primary = db.scalar(
        select(SiteDomain).where(SiteDomain.is_primary.is_(True)).with_for_update()
    )
    has_active_domain = db.scalar(
        select(SiteDomain.id).where(SiteDomain.status == SiteDomainStatus.active).limit(1)
    )
    if current_primary is None and has_active_domain is None:
        return collection_response(db, configuration)
    if current_primary is not None:
        current_primary.is_primary = False
        current_primary.revision += 1
        configuration.domains_revision += 1
        _audit(
            db,
            request,
            admin,
            "site_domain.platform_primary_selected",
            {"previous_primary_hostname": current_primary.hostname},
        )
        db.commit()
        configuration = _lock_configuration(db, configuration)
    try:
        provider, _, _ = _provider()
    except HTTPException:
        active_domains = list(
            db.scalars(select(SiteDomain).where(SiteDomain.status == SiteDomainStatus.active))
        )
        for active_domain in active_domains:
            active_domain.failure_reason = "edge_reconciliation_required"
            active_domain.revision += 1
        configuration.domains_revision += 1
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {"reason": "provider_unavailable"},
            outcome="failed",
        )
        db.commit()
        return collection_response(db, configuration)
    try:
        sync_active_edge_allowlist(db, configuration, provider)
    except DomainProviderError as error:
        active_domains = list(
            db.scalars(select(SiteDomain).where(SiteDomain.status == SiteDomainStatus.active))
        )
        for active_domain in active_domains:
            active_domain.failure_reason = "edge_reconciliation_required"
            active_domain.revision += 1
        configuration.domains_revision += 1
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {"reason": error.code},
            outcome="failed",
        )
        db.commit()
        return collection_response(db, configuration)
    db.commit()
    return collection_response(db, configuration)


@router.post("/{domain_id}/refresh", response_model=SiteDomainCollectionResponse)
def refresh_site_domain(
    domain_id: uuid.UUID,
    payload: SiteDomainMutationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    provider, settings, cname_target = _provider()
    configuration = _lock_configuration(db, configuration)
    domain = get_owned_domain(db, domain_id, for_update=True)
    _check_revision(domain, payload.revision)
    if domain.status == SiteDomainStatus.removing:
        raise HTTPException(status.HTTP_409_CONFLICT, "Custom domain removal is in progress")
    previous_status = domain.status
    try:
        provider_hostname = (
            provider.get_hostname(domain.provider_hostname_id)
            if domain.provider_hostname_id
            else provider.create_hostname(domain.hostname)
        )
    except DomainProviderNotFound as error:
        domain.status = SiteDomainStatus.failed
        domain.is_primary = False
        domain.provider_hostname_id = None
        domain.edge_published_revision = None
        domain.activated_at = None
        domain.failure_reason = error.code
        domain.last_checked_at = datetime.now(UTC)
        domain.revision += 1
        configuration.domains_revision += 1
        reconciliation_failed = False
        try:
            provider.delete_domain_allowlist(domain.hostname)
        except DomainProviderError:
            reconciliation_failed = True
        if settings.captcha_required:
            try:
                provider.reconcile_turnstile_domains(
                    required=turnstile_required_hostnames(
                        db, exclude={domain.hostname}
                    ),
                    remove={domain.hostname},
                )
            except DomainProviderError:
                reconciliation_failed = True
        try:
            sync_active_edge_allowlist(db, configuration, provider)
        except DomainProviderError:
            reconciliation_failed = True
        if reconciliation_failed:
            domain.failure_reason = "edge_reconciliation_required"
        _audit(
            db,
            request,
            admin,
            "site_domain.authoritative_loss",
            {
                "domain_id": str(domain.id),
                "hostname": domain.hostname,
                "reason": domain.failure_reason,
            },
            outcome="failed",
        )
        db.commit()
        if reconciliation_failed:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Domain admission was revoked locally; edge reconciliation is required",
            ) from error
        return collection_response(db, configuration)
    except DomainProviderError as error:
        _record_provider_failure(
            db,
            configuration,
            domain,
            error,
            request,
            admin,
            "site_domain.refreshed",
            fail_domain=domain.provider_hostname_id is None,
        )
        raise _provider_failure() from error

    apply_provider_hostname(domain, provider_hostname, cname_target)
    configuration.domains_revision += 1
    _audit(
        db,
        request,
        admin,
        "site_domain.refreshed",
        {
            "domain_id": str(domain.id),
            "hostname": domain.hostname,
            "previous_status": previous_status,
            "status": domain.status,
        },
    )
    db.commit()
    _sync_after_refresh(
        db, configuration, domain, provider, previous_status, request, admin
    )
    return collection_response(db, configuration)


@router.post("/{domain_id}/make-primary", response_model=SiteDomainCollectionResponse)
def make_site_domain_primary(
    domain_id: uuid.UUID,
    payload: SiteDomainMutationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    provider, _, _ = _provider()
    configuration = _lock_configuration(db, configuration)
    domain = get_owned_domain(db, domain_id, for_update=True)
    _check_revision(domain, payload.revision)
    if domain.status != SiteDomainStatus.active:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only an active domain can be primary")
    if domain.is_primary:
        return collection_response(db, configuration)

    current_primary = db.scalar(select(SiteDomain).where(SiteDomain.is_primary.is_(True)))
    if current_primary is not None:
        current_primary.is_primary = False
        current_primary.revision += 1
    domain.is_primary = True
    domain.revision += 1
    configuration.domains_revision += 1
    _audit(
        db,
        request,
        admin,
        "site_domain.primary_changed",
        {"domain_id": str(domain.id), "hostname": domain.hostname},
    )
    db.commit()
    try:
        sync_active_edge_allowlist(db, configuration, provider)
    except DomainProviderError as error:
        domain.failure_reason = error.code
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {"domain_id": str(domain.id), "reason": error.code},
            outcome="failed",
        )
        db.commit()
        raise _provider_failure() from error
    db.commit()
    return collection_response(db, configuration)


@router.delete("/{domain_id}", response_model=SiteDomainCollectionResponse)
def delete_site_domain(
    domain_id: uuid.UUID,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
    revision: Annotated[int, Query(ge=0)],
    confirmation: Annotated[str, Query(min_length=1, max_length=253)],
) -> SiteDomainCollectionResponse:
    _no_store(response)
    configuration = _configuration(db, request, admin)
    configuration = _lock_configuration(db, configuration)
    domain = get_owned_domain(db, domain_id, for_update=True)
    _check_revision(domain, revision)
    hostname = domain.hostname
    try:
        normalized_confirmation = normalize_hostname(confirmation)
    except ValueError:
        normalized_confirmation = ""
    if confirmation != normalized_confirmation or normalized_confirmation != hostname:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Custom domain confirmation did not match",
        )
    provider, settings, _ = _provider()
    provider_hostname_id = domain.provider_hostname_id

    # Revoke edge admission first. The canonical platform origin remains available throughout.
    try:
        provider.delete_domain_allowlist(hostname)
    except DomainProviderError as error:
        _record_provider_failure(
            db,
            configuration,
            domain,
            error,
            request,
            admin,
            "site_domain.removed",
        )
        raise _provider_failure() from error

    if settings.captcha_required:
        try:
            provider.reconcile_turnstile_domains(
                required=turnstile_required_hostnames(db, exclude={hostname}),
                remove={hostname},
            )
        except DomainProviderError as error:
            domain.status = SiteDomainStatus.removing
            domain.is_primary = False
            domain.edge_published_revision = None
            _record_provider_failure(
                db,
                configuration,
                domain,
                error,
                request,
                admin,
                "site_domain.turnstile_removal",
            )
            raise _provider_failure() from error

    try:
        if provider_hostname_id is not None:
            provider.delete_hostname(provider_hostname_id)
    except DomainProviderError as error:
        domain.status = SiteDomainStatus.removing
        domain.is_primary = False
        domain.edge_published_revision = None
        _record_provider_failure(
            db,
            configuration,
            domain,
            error,
            request,
            admin,
            "site_domain.removed",
        )
        raise _provider_failure() from error

    db.delete(domain)
    configuration.domains_revision += 1
    _audit(
        db,
        request,
        admin,
        "site_domain.removed",
        {"domain_id": str(domain_id), "hostname": hostname},
    )
    db.commit()
    try:
        sync_active_edge_allowlist(db, configuration, provider)
    except DomainProviderError as error:
        active_domains = list(
            db.scalars(select(SiteDomain).where(SiteDomain.status == SiteDomainStatus.active))
        )
        for active_domain in active_domains:
            active_domain.failure_reason = error.code
        _audit(
            db,
            request,
            admin,
            "site_domain.edge_reconciliation",
            {"reason": error.code},
            outcome="failed",
        )
        db.commit()
        raise _provider_failure() from error
    db.commit()
    return collection_response(db, configuration)
