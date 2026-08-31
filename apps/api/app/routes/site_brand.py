import time
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.auth import DbSession, require_admin, require_trusted_origin
from app.brand_copy_assistant import (
    BrandAiProviderError,
    BrandAiUnavailableError,
    generate_brand_copy,
    owner_safety_identifier,
)
from app.config import get_settings
from app.models import Admin, AuditLog, SiteBrandAsset, SiteBrandConfiguration
from app.rate_limit import enforce_rate_limit
from app.site_brand_schemas import (
    BrandCopyAssistRequest,
    BrandCopyAssistResponse,
    SiteBrandAdminResponse,
    SiteBrandPatchRequest,
    SiteBrandPublicResponse,
    SiteBrandPublishRequest,
)
from app.site_brand_service import (
    MAX_LOGO_BYTES,
    admin_response,
    delete_logo,
    get_or_claim_configuration,
    patch_configuration,
    public_response,
    publish_configuration,
    put_logo,
    response_etag,
    validate_logo,
)

public_router = APIRouter(prefix="/site/brand", tags=["site brand"])
admin_router = APIRouter(
    prefix="/admin/site/brand",
    tags=["administrator site brand"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Cookie",
}


def _audit(
    db: DbSession,
    request: Request,
    admin: Admin | uuid.UUID,
    action: str,
    detail: dict[str, Any] | None = None,
    *,
    outcome: str = "succeeded",
) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id if isinstance(admin, Admin) else admin,
            action=action,
            outcome=outcome,
            ip_address=request.client.host if request.client else None,
            detail=detail or {},
        )
    )


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


def _published_logo_kind(configuration: SiteBrandConfiguration) -> str:
    if configuration.published_snapshot.get("logo_mark") is not None:
        return "generated"
    if configuration.published_logo_asset_id is not None:
        return "uploaded"
    return "none"


def _private_no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _assistant_error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"detail": message, "code": code},
        headers=PRIVATE_NO_STORE_HEADERS,
    )


def _etag_matches(request: Request, etag: str) -> bool:
    supplied = request.headers.get("if-none-match", "")
    return any(value.strip() in {etag, "*"} for value in supplied.split(","))


@public_router.get("", response_model=SiteBrandPublicResponse)
def get_public_brand(request: Request, response: Response, db: DbSession) -> Any:
    payload = public_response(db)
    etag = response_etag(payload)
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=60, stale-while-revalidate=300",
        "Vary": "Accept-Encoding",
    }
    if _etag_matches(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    for name, value in headers.items():
        response.headers[name] = value
    return payload


@public_router.get("/logo")
def get_public_logo(
    request: Request,
    db: DbSession,
    revision: Annotated[int | None, Query(ge=0)] = None,
) -> Response:
    configuration = db.get(SiteBrandConfiguration, 1)
    if (
        configuration is None
        or configuration.published_snapshot is None
        or configuration.published_logo_asset_id is None
    ):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand logo was not found")
    asset = db.get(SiteBrandAsset, configuration.published_logo_asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand logo was not found")
    if revision is not None and revision != asset.revision:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand logo revision was not found")
    etag = f'"{asset.sha256}"'
    headers = {
        "ETag": etag,
        "Cache-Control": "public, max-age=300, stale-while-revalidate=86400",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
    }
    if _etag_matches(request, etag):
        return Response(status_code=status.HTTP_304_NOT_MODIFIED, headers=headers)
    return Response(content=asset.content, media_type=asset.content_type, headers=headers)


@admin_router.get("", response_model=SiteBrandAdminResponse)
def get_admin_brand(
    request: Request, response: Response, db: DbSession, admin: AdminIdentity
) -> SiteBrandAdminResponse:
    _no_store(response)
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
        db.commit()
        db.refresh(configuration)
    return admin_response(db, configuration)


@admin_router.patch("", response_model=SiteBrandAdminResponse)
def patch_admin_brand(
    payload: SiteBrandPatchRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteBrandAdminResponse:
    _no_store(response)
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
    configuration, changed_fields = patch_configuration(db, configuration, payload)
    if changed_fields:
        _audit(
            db,
            request,
            admin,
            "site_brand.draft.updated",
            {
                "revision": configuration.revision,
                "changed_fields": changed_fields,
                "current_step": configuration.current_step,
                "completed_steps": configuration.completed_steps,
            },
        )
    db.commit()
    db.refresh(configuration)
    return admin_response(db, configuration)


@admin_router.post("/publish", response_model=SiteBrandAdminResponse)
def publish_admin_brand(
    payload: SiteBrandPublishRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> SiteBrandAdminResponse:
    _no_store(response)
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
    configuration = publish_configuration(db, configuration, payload.revision)
    logo_kind = _published_logo_kind(configuration)
    _audit(
        db,
        request,
        admin,
        "site_brand.published",
        {
            "revision": configuration.revision,
            "business_name": configuration.published_snapshot["business_name"],
            "has_logo": logo_kind != "none",
            "logo_kind": logo_kind,
        },
    )
    db.commit()
    db.refresh(configuration)
    return admin_response(db, configuration)


@admin_router.post("/assist-copy", response_model=BrandCopyAssistResponse)
async def assist_brand_copy(
    payload: BrandCopyAssistRequest,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> BrandCopyAssistResponse | JSONResponse:
    _private_no_store(response)
    settings = get_settings()
    admin_id = admin.id
    configuration, claimed = get_or_claim_configuration(db, admin)
    if configuration.owner_admin_id != admin_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the site owner can use copy assistance",
        )
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
        db.commit()
    else:
        # Do not retain a database connection or transaction while waiting on a model provider.
        db.rollback()

    safety_identifier = owner_safety_identifier(admin_id, settings.session_secret)
    started = time.perf_counter()
    try:
        await enforce_rate_limit(
            f"brand-copy-assist:{safety_identifier}",
            limit=settings.brand_ai_rate_limit_per_hour,
            window_seconds=3600,
        )
    except HTTPException as error:
        if error.status_code != status.HTTP_429_TOO_MANY_REQUESTS:
            raise
        return _assistant_error(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "brand_ai_rate_limited",
            "The copy assistant has reached its request limit. Try again later.",
        )
    except Exception:
        latency_ms = round((time.perf_counter() - started) * 1000)
        _audit(
            db,
            request,
            admin_id,
            "site_brand.copy_assistance",
            {"model": settings.brand_ai_model, "latency_ms": latency_ms},
            outcome="failed",
        )
        db.commit()
        return _assistant_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "brand_ai_unavailable",
            "The copy assistant is temporarily unavailable. Please try again.",
        )

    try:
        result = await generate_brand_copy(
            payload,
            safety_identifier=safety_identifier,
            settings=settings,
        )
    except BrandAiUnavailableError:
        latency_ms = round((time.perf_counter() - started) * 1000)
        _audit(
            db,
            request,
            admin_id,
            "site_brand.copy_assistance",
            {"model": settings.brand_ai_model, "latency_ms": latency_ms},
            outcome="failed",
        )
        db.commit()
        return _assistant_error(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "brand_ai_unavailable",
            "The private copy assistant is not configured yet.",
        )
    except BrandAiProviderError:
        latency_ms = round((time.perf_counter() - started) * 1000)
        _audit(
            db,
            request,
            admin_id,
            "site_brand.copy_assistance",
            {"model": settings.brand_ai_model, "latency_ms": latency_ms},
            outcome="failed",
        )
        db.commit()
        return _assistant_error(
            status.HTTP_502_BAD_GATEWAY,
            "brand_ai_failed",
            "The copy assistant could not create safe suggestions. Please try again.",
        )

    latency_ms = round((time.perf_counter() - started) * 1000)
    _audit(
        db,
        request,
        admin_id,
        "site_brand.copy_assistance",
        {
            "model": settings.brand_ai_model,
            "latency_ms": latency_ms,
            "suggestion_count": len(result.suggestions),
        },
    )
    db.commit()
    return result


@admin_router.get("/logo")
def get_admin_logo(request: Request, db: DbSession, admin: AdminIdentity) -> Response:
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
        db.commit()
    if configuration.draft_logo_asset_id is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand logo was not found")
    asset = db.get(SiteBrandAsset, configuration.draft_logo_asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Brand logo was not found")
    return Response(
        content=asset.content,
        media_type=asset.content_type,
        headers={
            "Cache-Control": "no-store",
            "ETag": f'"{asset.sha256}"',
            "Content-Disposition": "inline",
            "X-Content-Type-Options": "nosniff",
        },
    )


async def _read_logo_body(request: Request) -> bytes:
    supplied_length = request.headers.get("content-length")
    if supplied_length:
        try:
            content_length = int(supplied_length)
        except ValueError as error:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Content-Length is invalid") from error
        if content_length > MAX_LOGO_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Logo image exceeds 2 MiB")
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > MAX_LOGO_BYTES:
            raise HTTPException(status.HTTP_413_CONTENT_TOO_LARGE, "Logo image exceeds 2 MiB")
    return bytes(content)


@admin_router.put("/logo", response_model=SiteBrandAdminResponse)
async def put_admin_logo(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
    expected_revision: int = Query(ge=0),
) -> SiteBrandAdminResponse:
    _no_store(response)
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
    content = await _read_logo_body(request)
    image = validate_logo(content, request.headers.get("content-type", ""))
    configuration, changed = put_logo(db, configuration, expected_revision, image)
    if changed:
        _audit(
            db,
            request,
            admin,
            "site_brand.logo.updated",
            {
                "revision": configuration.revision,
                "sha256": image.sha256,
                "byte_size": len(image.content),
                "width": image.width,
                "height": image.height,
                "content_type": image.content_type,
            },
        )
    db.commit()
    db.refresh(configuration)
    return admin_response(db, configuration)


@admin_router.delete("/logo", response_model=SiteBrandAdminResponse)
def delete_admin_logo(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
    expected_revision: int = Query(ge=0),
) -> SiteBrandAdminResponse:
    _no_store(response)
    configuration, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
    configuration, changed = delete_logo(db, configuration, expected_revision)
    if changed:
        _audit(
            db,
            request,
            admin,
            "site_brand.logo.deleted",
            {"revision": configuration.revision},
        )
    db.commit()
    db.refresh(configuration)
    return admin_response(db, configuration)
