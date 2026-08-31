from __future__ import annotations

import ipaddress
import re
import secrets
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlsplit
from uuid import UUID

import idna
from fastapi import HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.custom_domain_provider import (
    CloudflareCustomHostnamesClient,
    DomainDnsRecord,
    DomainProviderError,
    ProviderHostname,
)
from app.models import SiteBrandConfiguration, SiteDomain, SiteDomainStatus
from app.site_domain_schemas import (
    SiteDomainCollectionResponse,
    SiteDomainDnsRecord,
    SiteDomainResponse,
)

PUBLIC_ORIGIN_HEADER = "X-Aperture-Public-Origin"
EDGE_SECRET_HEADER = "X-Aperture-Edge-Secret"
SAFE_REQUEST_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
RESERVED_CUSTOM_TLDS = frozenset(
    {"example", "invalid", "localhost", "local", "internal", "onion", "test"}
)
PROVIDER_FAILURE_STATES = frozenset(
    {
        "blocked",
        "deleted",
        "expired",
        "moved",
        "pending_deletion",
        "validation_timed_out",
    }
)


def normalize_hostname(value: str) -> str:
    """Normalize a user-owned DNS hostname to a unique lower-case ASCII form."""
    if not isinstance(value, str):
        raise ValueError("A hostname is required")
    raw = unicodedata.normalize("NFC", value.strip())
    if not raw or raw.endswith("."):
        raise ValueError("Use a hostname without a trailing dot")
    if any(character.isspace() or ord(character) < 32 for character in raw):
        raise ValueError("Hostname contains unsupported whitespace")
    if any(marker in raw for marker in ("://", "/", "\\", "@", "*", "[", "]", ":")):
        raise ValueError("Enter a hostname, not a URL or wildcard")
    try:
        hostname = idna.encode(
            raw,
            uts46=True,
            transitional=False,
            std3_rules=True,
        ).decode("ascii").lower()
    except idna.IDNAError as error:
        raise ValueError("Hostname cannot be represented in DNS") from error
    if len(hostname) > 253:
        raise ValueError("Hostname is longer than 253 characters")
    labels = hostname.split(".")
    if len(labels) < 2 or any(not HOST_LABEL.fullmatch(label) for label in labels):
        raise ValueError("Hostname must be a valid public DNS name")
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        raise ValueError("IP addresses cannot be used as custom domains")
    if labels[-1].isdigit() or labels[-1] in RESERVED_CUSTOM_TLDS:
        raise ValueError("Hostname must use a public DNS suffix")
    return hostname


def platform_hostname(settings: Settings | None = None) -> str:
    configured = settings or get_settings()
    hostname = urlsplit(str(configured.web_origin)).hostname
    if not hostname:
        raise RuntimeError("WEB_ORIGIN does not contain a hostname")
    return hostname.lower().rstrip(".")


def reserved_domain_hostnames(settings: Settings | None = None) -> frozenset[str]:
    configured = settings or get_settings()
    hostnames: set[str] = set()
    for value in (
        configured.web_origin,
        configured.api_origin,
        configured.admin_web_origin,
        configured.s3_public_endpoint,
        configured.cdn_public_origin,
    ):
        if value is not None and (hostname := urlsplit(str(value)).hostname):
            hostnames.add(hostname.lower().rstrip("."))
    if configured.custom_domain_cname_target:
        hostnames.add(configured.custom_domain_cname_target.strip().lower().rstrip("."))
    return frozenset(hostnames)


def validate_custom_hostname(value: str, settings: Settings | None = None) -> str:
    hostname = normalize_hostname(value)
    for reserved in reserved_domain_hostnames(settings):
        if hostname == reserved or hostname.endswith(f".{reserved}"):
            raise ValueError("This hostname is reserved by the Aperture deployment")
    return hostname


def _canonical_origin(settings: Settings | None = None) -> str:
    return str((settings or get_settings()).web_origin).rstrip("/")


def _normalize_https_origin(value: str) -> tuple[str, str]:
    try:
        parsed = urlsplit(value.strip())
        port = parsed.port
    except (TypeError, ValueError) as error:
        raise ValueError("Public origin is invalid") from error
    if (
        parsed.scheme.lower() != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
        or port not in {None, 443}
    ):
        raise ValueError("Public origin must be an HTTPS origin without a path")
    hostname = normalize_hostname(parsed.hostname)
    return f"https://{hostname}", hostname


def active_domain_by_hostname(db: Session, hostname: str) -> SiteDomain | None:
    try:
        normalized = normalize_hostname(hostname)
    except ValueError:
        return None
    return db.scalar(
        select(SiteDomain).where(
            SiteDomain.hostname == normalized,
            SiteDomain.status == SiteDomainStatus.active,
        )
    )


def validate_public_origin(db: Session, origin: str) -> str:
    """Return a canonical allowed origin or raise without reflecting the supplied value."""
    canonical = _canonical_origin()
    if isinstance(origin, str) and origin.rstrip("/") == canonical:
        return canonical
    try:
        normalized_origin, hostname = _normalize_https_origin(origin)
    except ValueError as error:
        raise ValueError("Public origin is not allowed") from error
    if active_domain_by_hostname(db, hostname) is None:
        raise ValueError("Public origin is not allowed")
    return normalized_origin


def is_allowed_public_origin(db: Session, origin: str) -> bool:
    try:
        validate_public_origin(db, origin)
    except (TypeError, ValueError):
        return False
    return True


def preferred_public_origin(db: Session) -> str:
    primary = db.scalar(
        select(SiteDomain).where(
            SiteDomain.status == SiteDomainStatus.active,
            SiteDomain.is_primary.is_(True),
        )
    )
    return f"https://{primary.hostname}" if primary is not None else _canonical_origin()


def resolve_request_public_origin(
    db: Session, request: Request, *, require_active: bool = True
) -> str:
    """Resolve an edge-asserted or browser Origin to a safe public return origin."""
    settings = get_settings()
    canonical = _canonical_origin(settings)
    asserted = request.headers.get(PUBLIC_ORIGIN_HEADER)
    browser_origin = request.headers.get("origin")

    if asserted is not None:
        expected = (
            settings.custom_domain_edge_secret.get_secret_value()
            if settings.custom_domain_edge_secret is not None
            else ""
        )
        supplied = request.headers.get(EDGE_SECRET_HEADER, "")
        if not expected or not supplied or not secrets.compare_digest(supplied, expected):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Public origin assertion is invalid")
        asserted_origin = _validate_origin_for_request(db, asserted, require_active=require_active)
        if browser_origin is not None:
            browser = _validate_origin_for_request(
                db, browser_origin, require_active=require_active
            )
            if browser != asserted_origin:
                raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin does not match host")
        return asserted_origin

    if browser_origin is not None:
        return _validate_origin_for_request(db, browser_origin, require_active=require_active)
    if request.method in SAFE_REQUEST_METHODS or settings.app_env != "production":
        return canonical
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin is required")


def _validate_origin_for_request(db: Session, origin: str, *, require_active: bool) -> str:
    if require_active:
        try:
            return validate_public_origin(db, origin)
        except (TypeError, ValueError) as error:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Public origin is not allowed"
            ) from error

    canonical = _canonical_origin()
    if isinstance(origin, str) and origin.rstrip("/") == canonical:
        return canonical
    try:
        normalized_origin, hostname = _normalize_https_origin(origin)
    except ValueError as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public origin is not allowed") from error
    domain = db.scalar(select(SiteDomain).where(SiteDomain.hostname == hostname))
    if domain is None or domain.status in {SiteDomainStatus.failed, SiteDomainStatus.removing}:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Public origin is not allowed")
    return normalized_origin


def domain_response(domain: SiteDomain) -> SiteDomainResponse:
    return SiteDomainResponse(
        id=domain.id,
        hostname=domain.hostname,
        status=domain.status,
        is_primary=domain.is_primary,
        revision=domain.revision,
        dns_records=[SiteDomainDnsRecord.model_validate(record) for record in domain.dns_records],
        verified_at=domain.verified_at,
        activated_at=domain.activated_at,
        last_checked_at=domain.last_checked_at,
        failure_reason=domain.failure_reason,
    )


def collection_response(
    db: Session, configuration: SiteBrandConfiguration
) -> SiteDomainCollectionResponse:
    domains = list(
        db.scalars(select(SiteDomain).order_by(SiteDomain.created_at, SiteDomain.hostname))
    )
    primary = next((domain for domain in domains if domain.is_primary), None)
    return SiteDomainCollectionResponse(
        revision=configuration.domains_revision,
        custom_domains_available=get_settings().custom_domains_available,
        platform_hostname=platform_hostname(),
        primary_domain_id=primary.id if primary is not None else None,
        domains=[domain_response(domain) for domain in domains],
    )


def apply_provider_hostname(
    domain: SiteDomain, provider: ProviderHostname, cname_target: str
) -> None:
    if provider.hostname != domain.hostname:
        raise DomainProviderError("provider_malformed_response")
    routing = DomainDnsRecord(
        type="CNAME",
        name=domain.hostname,
        value=cname_target,
        purpose="routing",
    )
    records = [routing, *provider.dns_records]
    deduplicated: list[dict[str, str]] = []
    for record in records:
        serialized = record.as_dict()
        if serialized not in deduplicated:
            deduplicated.append(serialized)

    now = datetime.now(UTC)
    domain.provider_hostname_id = provider.id
    domain.dns_records = deduplicated
    domain.last_checked_at = now
    domain.failure_reason = None
    if provider.hostname_status in PROVIDER_FAILURE_STATES or provider.ssl_status in (
        PROVIDER_FAILURE_STATES
    ):
        domain.status = SiteDomainStatus.failed
    elif provider.hostname_status == "active" and provider.ssl_status == "active":
        if domain.status != SiteDomainStatus.active:
            domain.status = SiteDomainStatus.pending_edge
        domain.verified_at = domain.verified_at or now
    elif provider.hostname_status == "active":
        domain.status = SiteDomainStatus.pending_tls
        domain.verified_at = domain.verified_at or now
    else:
        domain.status = SiteDomainStatus.pending_dns
    if domain.status != SiteDomainStatus.active:
        domain.is_primary = False
    domain.revision += 1


def edge_allowlist_payload(
    domain: SiteDomain, *, primary_hostname: str, collection_revision: int
) -> dict[str, str | int]:
    return {
        "status": "active",
        "site_id": "1",
        "hostname": domain.hostname,
        "primary_hostname": primary_hostname,
        "revision": collection_revision,
    }


def turnstile_required_hostnames(
    db: Session,
    *,
    include: set[str] | None = None,
    exclude: set[str] | None = None,
) -> set[str]:
    excluded = exclude or set()
    active_hostnames = set(
        db.scalars(
            select(SiteDomain.hostname).where(
                SiteDomain.status == SiteDomainStatus.active,
                SiteDomain.hostname.not_in(excluded),
            )
        )
    )
    return {platform_hostname(), *active_hostnames, *(include or set())}


def sync_active_edge_allowlist(
    db: Session,
    configuration: SiteBrandConfiguration,
    provider: CloudflareCustomHostnamesClient,
) -> None:
    active_domains = list(
        db.scalars(
            select(SiteDomain)
            .where(SiteDomain.status == SiteDomainStatus.active)
            .order_by(SiteDomain.hostname)
        )
    )
    primary = next((domain for domain in active_domains if domain.is_primary), None)
    primary_hostname = primary.hostname if primary is not None else platform_hostname()
    for domain in active_domains:
        provider.publish_domain_allowlist(
            domain.hostname,
            edge_allowlist_payload(
                domain,
                primary_hostname=primary_hostname,
                collection_revision=configuration.domains_revision,
            ),
        )
    for domain in active_domains:
        domain.edge_published_revision = configuration.domains_revision
        domain.failure_reason = None


def sync_activation_edge_allowlist(
    db: Session,
    configuration: SiteBrandConfiguration,
    candidate: SiteDomain,
    provider: CloudflareCustomHostnamesClient,
) -> None:
    """Publish existing aliases first and the newly verified candidate last."""
    existing_domains = list(
        db.scalars(
            select(SiteDomain)
            .where(
                SiteDomain.status == SiteDomainStatus.active,
                SiteDomain.id != candidate.id,
            )
            .order_by(SiteDomain.hostname)
        )
    )
    primary = next((domain for domain in existing_domains if domain.is_primary), None)
    primary_hostname = primary.hostname if primary is not None else platform_hostname()
    for domain in existing_domains:
        provider.publish_domain_allowlist(
            domain.hostname,
            edge_allowlist_payload(
                domain,
                primary_hostname=primary_hostname,
                collection_revision=configuration.domains_revision,
            ),
        )
    provider.publish_domain_allowlist(
        candidate.hostname,
        edge_allowlist_payload(
            candidate,
            primary_hostname=primary_hostname,
            collection_revision=configuration.domains_revision,
        ),
    )
    for domain in [*existing_domains, candidate]:
        domain.edge_published_revision = configuration.domains_revision
        domain.failure_reason = None


def get_owned_domain(db: Session, domain_id: UUID, *, for_update: bool = False) -> SiteDomain:
    query = select(SiteDomain).where(
        SiteDomain.id == domain_id,
        SiteDomain.site_brand_configuration_id == 1,
    )
    if for_update:
        query = query.execution_options(populate_existing=True).with_for_update()
    domain = db.scalar(query)
    if domain is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Custom domain was not found")
    return domain
