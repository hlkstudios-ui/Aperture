import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import or_, select
from sqlalchemy.orm import selectinload

from app.account_schemas import (
    AccountDashboardResponse,
    BillingState,
    CheckoutRequest,
    EntitlementResponse,
    PasswordChangeRequest,
    SessionResponse,
)
from app.auth import (
    DbSession,
    hash_password,
    require_customer,
    require_customer_session,
    require_trusted_origin,
    verify_password,
)
from app.billing import BillingUnavailable, get_billing_provider
from app.config import get_settings
from app.models import (
    DeviceSession,
    Entitlement,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)
from app.site_domain_service import resolve_request_public_origin

router = APIRouter(
    prefix="/account",
    tags=["customer account"],
    dependencies=[Depends(require_trusted_origin), Depends(require_customer)],
)
Customer = Annotated[User, Depends(require_customer)]
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]
ACTIVE_SUBSCRIPTION_STATES = (
    SubscriptionStatus.incomplete,
    SubscriptionStatus.trialing,
    SubscriptionStatus.active,
    SubscriptionStatus.past_due,
)


def active_entitlements(db: DbSession, user_id: uuid.UUID) -> list[Entitlement]:
    now = datetime.now(UTC)
    return list(
        db.scalars(
            select(Entitlement)
            .where(
                Entitlement.user_id == user_id,
                or_(Entitlement.starts_at.is_(None), Entitlement.starts_at <= now),
                or_(Entitlement.ends_at.is_(None), Entitlement.ends_at > now),
            )
            .order_by(Entitlement.key)
        )
    )


@router.get("", response_model=AccountDashboardResponse)
def dashboard(db: DbSession, user: Customer, current: CurrentSession) -> AccountDashboardResponse:
    subscription = db.scalar(
        select(Subscription)
        .options(selectinload(Subscription.plan))
        .where(
            Subscription.user_id == user.id,
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATES),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sessions = list(
        db.scalars(
            select(DeviceSession)
            .where(
                DeviceSession.user_id == user.id,
                DeviceSession.revoked_at.is_(None),
                DeviceSession.expires_at > datetime.now(UTC),
            )
            .order_by(DeviceSession.last_seen_at.desc())
        )
    )
    provider = get_billing_provider()
    return AccountDashboardResponse(
        email=user.email,
        subscription=subscription,
        entitlements=[
            EntitlementResponse.model_validate(item) for item in active_entitlements(db, user.id)
        ],
        sessions=[
            SessionResponse(
                id=item.id,
                current=item.id == current.id,
                user_agent=item.user_agent,
                ip_address=item.ip_address,
                created_at=item.created_at,
                last_seen_at=item.last_seen_at,
                expires_at=item.expires_at,
            )
            for item in sessions
        ],
        plans=list(
            db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.price_cents))
        ),
        billing=BillingState(
            provider=provider.name,
            production_ready=provider.production_ready,
            checkout_available=provider.production_ready,
            notice=(
                None if provider.production_ready else (
                    "Payments are intentionally disabled for this launch. "
                    "No payment can be accepted."
                    if provider.name == "disabled"
                    else "Billing is not configured and never simulates completed payment."
                )
            ),
        ),
    )


@router.post("/checkout")
def checkout(
    payload: CheckoutRequest,
    request: Request,
    db: DbSession,
    user: Customer,
) -> dict[str, str]:
    existing = db.scalar(
        select(Subscription).where(
            Subscription.user_id == user.id,
            Subscription.status.in_(ACTIVE_SUBSCRIPTION_STATES),
        )
    )
    if existing is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "An existing subscription must be managed through the billing portal",
        )
    plan = db.scalar(select(Plan).where(Plan.code == payload.plan_code, Plan.is_active.is_(True)))
    if plan is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Subscription plan was not found")
    try:
        result = get_billing_provider().create_checkout(
            user,
            plan,
            return_origin=resolve_request_public_origin(db, request),
        )
    except BillingUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"provider": result.provider, "checkout_url": result.checkout_url}


@router.post("/billing-portal")
def billing_portal(request: Request, db: DbSession, user: Customer) -> dict[str, str]:
    provider = get_billing_provider()
    subscription = db.scalar(
        select(Subscription)
        .where(
            Subscription.user_id == user.id,
            Subscription.provider == provider.name,
            Subscription.provider_customer_ref.is_not(None),
        )
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    if subscription is None or not subscription.provider_customer_ref:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No provider billing account was found")
    try:
        result = provider.create_portal(
            subscription.provider_customer_ref,
            return_origin=resolve_request_public_origin(db, request),
        )
    except BillingUnavailable as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {"provider": result.provider, "portal_url": result.portal_url}


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def revoke_session(
    session_id: uuid.UUID,
    response: Response,
    db: DbSession,
    user: Customer,
    current: CurrentSession,
) -> None:
    session = db.scalar(
        select(DeviceSession).where(
            DeviceSession.id == session_id,
            DeviceSession.user_id == user.id,
            DeviceSession.revoked_at.is_(None),
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Active session was not found")
    session.revoked_at = datetime.now(UTC)
    db.commit()
    if session.id == current.id:
        settings = get_settings()
        response.delete_cookie(
            settings.customer_session_cookie, path="/", domain=settings.session_cookie_domain
        )


@router.post("/sessions/revoke-others", status_code=status.HTTP_204_NO_CONTENT)
def revoke_other_sessions(db: DbSession, user: Customer, current: CurrentSession) -> None:
    now = datetime.now(UTC)
    for session in user.sessions:
        if session.id != current.id and session.revoked_at is None:
            session.revoked_at = now
    db.commit()


@router.post("/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: PasswordChangeRequest,
    db: DbSession,
    user: Customer,
    current: CurrentSession,
) -> None:
    if not verify_password(user.password_hash, payload.current_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Current password is incorrect")
    if verify_password(user.password_hash, payload.new_password):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "New password must be different")
    user.password_hash = hash_password(payload.new_password)
    now = datetime.now(UTC)
    for session in user.sessions:
        if session.id != current.id and session.revoked_at is None:
            session.revoked_at = now
    db.commit()
