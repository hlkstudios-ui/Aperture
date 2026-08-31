import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from app.auth import DbSession, require_admin, require_trusted_origin
from app.models import Admin, AuditLog
from app.site_brand_service import get_or_claim_configuration
from app.viewer_monetization_schemas import (
    StripeConnectOnboardingResponse,
    ViewerMonetizationStatus,
)
from app.viewer_monetization_service import (
    ViewerMonetizationProviderError,
    ViewerMonetizationUnavailable,
    apply_account_state,
    create_onboarding_link,
    ensure_connected_account,
    get_owned_connection,
    retrieve_account_state,
    status_response,
)

router = APIRouter(
    prefix="/admin/viewer-monetization",
    tags=["administrator viewer monetization"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Cookie",
}


def _private_no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _audit(
    db: DbSession,
    request: Request,
    admin: Admin | uuid.UUID,
    action: str,
    detail: dict[str, Any] | None = None,
) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id if isinstance(admin, Admin) else admin,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail=detail or {},
        )
    )


def _require_owner(db: DbSession, request: Request, admin: Admin) -> None:
    _, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(db, request, admin, "site_brand.owner.claimed", {"schema_version": 1})
        db.commit()


def _provider_error(error: Exception) -> HTTPException:
    if isinstance(error, ViewerMonetizationUnavailable):
        return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(error))
    return HTTPException(
        status.HTTP_502_BAD_GATEWAY,
        "Stripe Connect is temporarily unavailable",
    )


@router.get("", response_model=ViewerMonetizationStatus)
def get_viewer_monetization(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> ViewerMonetizationStatus:
    _private_no_store(response)
    _require_owner(db, request, admin)
    return status_response(db, get_owned_connection(db, admin))


@router.post(
    "/providers/stripe/connect",
    response_model=StripeConnectOnboardingResponse,
)
def connect_stripe(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> StripeConnectOnboardingResponse:
    _private_no_store(response)
    _require_owner(db, request, admin)
    try:
        connection, created = ensure_connected_account(db, admin)
    except (ViewerMonetizationUnavailable, ViewerMonetizationProviderError) as error:
        db.rollback()
        raise _provider_error(error) from error
    if created:
        _audit(
            db,
            request,
            admin,
            "viewer_monetization.stripe_account.created",
            {
                "schema_version": 1,
                "provider": "stripe_connect",
                "connected_account_id": connection.stripe_connected_account_id,
                "revision": connection.revision,
            },
        )
        db.commit()
        db.refresh(connection)
    else:
        # Release the owner/account row locks before waiting on Stripe.
        db.rollback()
    try:
        link = create_onboarding_link(connection.stripe_connected_account_id or "")
    except (ViewerMonetizationUnavailable, ViewerMonetizationProviderError) as error:
        db.rollback()
        raise _provider_error(error) from error
    _audit(
        db,
        request,
        admin,
        "viewer_monetization.onboarding_link.created",
        {
            "schema_version": 1,
            "provider": "stripe_connect",
            "connected_account_id": connection.stripe_connected_account_id,
            "revision": connection.revision,
        },
    )
    db.commit()
    return StripeConnectOnboardingResponse(
        onboarding_url=link.url,
        expires_at=link.expires_at,
    )


@router.post("/refresh", response_model=ViewerMonetizationStatus)
def refresh_stripe(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> ViewerMonetizationStatus:
    _private_no_store(response)
    _require_owner(db, request, admin)
    connection = get_owned_connection(db, admin)
    if connection is None or not connection.stripe_connected_account_id:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Connect a Stripe account before refreshing its status",
        )
    account_id = connection.stripe_connected_account_id
    db.rollback()
    try:
        account_state = retrieve_account_state(account_id)
    except (ViewerMonetizationUnavailable, ViewerMonetizationProviderError) as error:
        raise _provider_error(error) from error
    connection = apply_account_state(db, admin, account_id, account_state)
    _audit(
        db,
        request,
        admin,
        "viewer_monetization.connection.refreshed",
        {
            "schema_version": 1,
            "provider": "stripe_connect",
            "connected_account_id": account_id,
            "revision": connection.revision,
            "livemode": connection.livemode,
            "details_submitted": connection.details_submitted,
            "charges_enabled": connection.charges_enabled,
            "payouts_enabled": connection.payouts_enabled,
            "requirements_due_count": len(connection.requirements_due),
        },
    )
    db.commit()
    db.refresh(connection)
    return status_response(db, connection)
