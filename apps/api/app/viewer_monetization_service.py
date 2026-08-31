from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit

import stripe
from fastapi import HTTPException, status
from pydantic import SecretStr
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.models import Admin, Plan, SiteBrandConfiguration, ViewerPaymentConnection
from app.viewer_monetization_schemas import ViewerMonetizationStatus

CONNECTED_ACCOUNT_ID = re.compile(r"^acct_[A-Za-z0-9]{8,64}$")
MAX_REQUIREMENTS = 100
MAX_REQUIREMENT_LENGTH = 160


class ViewerMonetizationUnavailable(RuntimeError):
    pass


class ViewerMonetizationProviderError(RuntimeError):
    pass


@dataclass(frozen=True)
class StripeAccountState:
    account_id: str
    livemode: bool
    details_submitted: bool
    charges_enabled: bool
    payouts_enabled: bool
    requirements_due: list[str]


@dataclass(frozen=True)
class StripeOnboardingLink:
    url: str
    expires_at: int | None


def _secret_value(value: SecretStr | None) -> str:
    return value.get_secret_value() if value is not None else ""


def stripe_connect_settings() -> tuple[Settings, str]:
    settings = get_settings()
    secret_key = _secret_value(settings.stripe_connect_platform_secret_key)
    webhook_secret = _secret_value(settings.stripe_connect_webhook_secret)
    if not settings.stripe_connect_enabled or not secret_key or not webhook_secret:
        raise ViewerMonetizationUnavailable("Stripe Connect onboarding is disabled")
    return settings, secret_key


def _field(value: Any, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _account_id(value: Any) -> str:
    account_id = _field(value, "id")
    if not isinstance(account_id, str) or not CONNECTED_ACCOUNT_ID.fullmatch(account_id):
        raise ViewerMonetizationProviderError("Stripe returned an invalid connected account")
    return account_id


def _requirements(value: Any) -> list[str]:
    requirements = _field(value, "requirements", {}) or {}
    due = _field(requirements, "currently_due", []) or []
    if not isinstance(due, (list, tuple)):
        raise ViewerMonetizationProviderError("Stripe returned invalid account requirements")
    cleaned: set[str] = set()
    for item in due:
        if not isinstance(item, str) or not item or len(item) > MAX_REQUIREMENT_LENGTH:
            raise ViewerMonetizationProviderError("Stripe returned invalid account requirements")
        cleaned.add(item)
        if len(cleaned) > MAX_REQUIREMENTS:
            raise ViewerMonetizationProviderError("Stripe returned too many account requirements")
    return sorted(cleaned)


def parse_account_state(value: Any, *, secret_key: str) -> StripeAccountState:
    supplied_livemode = _field(value, "livemode")
    return StripeAccountState(
        account_id=_account_id(value),
        livemode=(
            supplied_livemode
            if isinstance(supplied_livemode, bool)
            else secret_key.startswith("sk_live_")
        ),
        details_submitted=bool(_field(value, "details_submitted", False)),
        charges_enabled=bool(_field(value, "charges_enabled", False)),
        payouts_enabled=bool(_field(value, "payouts_enabled", False)),
        requirements_due=_requirements(value),
    )


def _owned_connection(
    db: Session, admin: Admin, *, for_update: bool = False
) -> ViewerPaymentConnection | None:
    query = select(ViewerPaymentConnection).where(ViewerPaymentConnection.id == 1)
    if for_update:
        query = query.with_for_update()
    connection = db.scalar(query)
    if connection is not None and connection.owner_admin_id != admin.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the site owner can manage viewer monetization",
        )
    return connection


def _lock_owner_configuration(db: Session, admin: Admin) -> None:
    configuration = db.scalar(
        select(SiteBrandConfiguration).where(SiteBrandConfiguration.id == 1).with_for_update()
    )
    if configuration is None or configuration.owner_admin_id != admin.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the site owner can manage viewer monetization",
        )


def ensure_connected_account(db: Session, admin: Admin) -> tuple[ViewerPaymentConnection, bool]:
    _, secret_key = stripe_connect_settings()
    _lock_owner_configuration(db, admin)
    connection = _owned_connection(db, admin, for_update=True)
    if connection is not None and connection.stripe_connected_account_id:
        return connection, False
    try:
        account = stripe.Account.create(
            type="standard",
            metadata={"aperture_cell_owner_id": str(admin.id)},
            api_key=secret_key,
            idempotency_key=f"viewer-monetization-account:{admin.id}",
        )
    except stripe.StripeError as error:
        raise ViewerMonetizationProviderError(
            "Stripe connected-account creation is temporarily unavailable"
        ) from error
    account_id = _account_id(account)
    if connection is None:
        connection = ViewerPaymentConnection(
            id=1,
            owner_admin_id=admin.id,
            provider="stripe_connect",
            access_mode="free",
            stripe_connected_account_id=account_id,
            livemode=None,
            details_submitted=False,
            charges_enabled=False,
            payouts_enabled=False,
            requirements_due=[],
            revision=1,
        )
        db.add(connection)
    else:
        connection.provider = "stripe_connect"
        connection.access_mode = "free"
        connection.stripe_connected_account_id = account_id
        connection.livemode = None
        connection.details_submitted = False
        connection.charges_enabled = False
        connection.payouts_enabled = False
        connection.requirements_due = []
        connection.revision += 1
    db.flush()
    return connection, True


def _studio_origin(settings: Settings) -> str:
    origin = settings.admin_web_origin or settings.web_origin
    parsed = urlsplit(str(origin).rstrip("/"))
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ViewerMonetizationUnavailable("The private Studio return address is unavailable")
    return f"{parsed.scheme}://{parsed.netloc}"


def create_onboarding_link(account_id: str) -> StripeOnboardingLink:
    settings, secret_key = stripe_connect_settings()
    if not CONNECTED_ACCOUNT_ID.fullmatch(account_id):
        raise ViewerMonetizationProviderError("The connected account is unavailable")
    studio_origin = _studio_origin(settings)
    try:
        link = stripe.AccountLink.create(
            account=account_id,
            refresh_url=f"{studio_origin}/studio/monetization?stripe_connect=refresh",
            return_url=f"{studio_origin}/studio/monetization?stripe_connect=return",
            type="account_onboarding",
            api_key=secret_key,
        )
    except stripe.StripeError as error:
        raise ViewerMonetizationProviderError(
            "Stripe hosted onboarding is temporarily unavailable"
        ) from error
    link_url = _field(link, "url")
    parsed = urlsplit(link_url) if isinstance(link_url, str) else None
    if (
        parsed is None
        or parsed.scheme != "https"
        or parsed.hostname is None
        or not (parsed.hostname == "connect.stripe.com" or parsed.hostname.endswith(".stripe.com"))
    ):
        raise ViewerMonetizationProviderError("Stripe returned an invalid onboarding link")
    expires_at = _field(link, "expires_at")
    if expires_at is not None and (not isinstance(expires_at, int) or expires_at < 0):
        raise ViewerMonetizationProviderError("Stripe returned an invalid onboarding expiry")
    return StripeOnboardingLink(url=link_url, expires_at=expires_at)


def retrieve_account_state(account_id: str) -> StripeAccountState:
    _, secret_key = stripe_connect_settings()
    if not CONNECTED_ACCOUNT_ID.fullmatch(account_id):
        raise ViewerMonetizationProviderError("The connected account is unavailable")
    try:
        account = stripe.Account.retrieve(account_id, api_key=secret_key)
    except stripe.StripeError as error:
        raise ViewerMonetizationProviderError(
            "Stripe account verification is temporarily unavailable"
        ) from error
    state = parse_account_state(account, secret_key=secret_key)
    if state.account_id != account_id:
        raise ViewerMonetizationProviderError("Stripe returned a different connected account")
    return state


def apply_account_state(
    db: Session,
    admin: Admin,
    expected_account_id: str,
    state: StripeAccountState,
) -> ViewerPaymentConnection:
    connection = _owned_connection(db, admin, for_update=True)
    if (
        connection is None
        or connection.stripe_connected_account_id != expected_account_id
        or state.account_id != expected_account_id
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "The connected account changed; reload before refreshing",
        )
    connection.provider = "stripe_connect"
    connection.livemode = state.livemode
    connection.details_submitted = state.details_submitted
    connection.charges_enabled = state.charges_enabled
    connection.payouts_enabled = state.payouts_enabled
    connection.requirements_due = state.requirements_due
    if connection.access_mode == "subscription_required" and not state.charges_enabled:
        connection.access_mode = "free"
    connection.revision += 1
    connection.updated_at = datetime.now(UTC)
    db.flush()
    return connection


def status_response(
    db: Session,
    connection: ViewerPaymentConnection | None,
) -> ViewerMonetizationStatus:
    settings = get_settings()
    active_plan_count = int(
        db.scalar(select(func.count(Plan.id)).where(Plan.is_active.is_(True))) or 0
    )
    runtime_enabled = settings.stripe_connect_enabled
    connected = bool(connection and connection.stripe_connected_account_id)
    requirements_due = list(connection.requirements_due if connection else [])
    details_submitted = bool(connection and connection.details_submitted)
    charges_enabled = bool(connection and connection.charges_enabled)
    payouts_enabled = bool(connection and connection.payouts_enabled)
    ready = bool(
        runtime_enabled
        and connected
        and details_submitted
        and charges_enabled
        and payouts_enabled
        and not requirements_due
    )
    eligible = bool(runtime_enabled and connected and charges_enabled and active_plan_count > 0)
    if not runtime_enabled:
        connection_state = "disabled"
        notice = "Viewer monetization is disabled. The storefront remains free."
    elif not connected:
        connection_state = "not_connected"
        notice = "Connect a Stripe account to begin hosted onboarding."
    elif ready:
        connection_state = "ready"
        notice = (
            "Stripe reports that charges and payouts are ready. Access remains free until "
            "subscription checkout and playback enforcement are separately enabled."
        )
    elif not details_submitted or requirements_due:
        connection_state = "onboarding_required"
        notice = "Stripe requires more hosted onboarding information before payments are ready."
    else:
        connection_state = "restricted"
        notice = "Stripe has not enabled both charges and payouts for this account."
    effective_access_mode = connection.access_mode if connection is not None else "free"
    if effective_access_mode == "subscription_required" and not eligible:
        effective_access_mode = "free"
    return ViewerMonetizationStatus(
        revision=connection.revision if connection else 0,
        access_mode=effective_access_mode,
        access_mode_change_available=False,
        provider=(
            "stripe_connect"
            if runtime_enabled or (connection and connection.provider == "stripe_connect")
            else "disabled"
        ),
        connection=connection_state,
        connected_account_id=(connection.stripe_connected_account_id if connection else None),
        livemode=connection.livemode if connection else None,
        details_submitted=details_submitted,
        charges_enabled=charges_enabled,
        payouts_enabled=payouts_enabled,
        requirements_due=requirements_due,
        active_plan_count=active_plan_count,
        subscription_mode_eligible=eligible,
        updated_at=connection.updated_at if connection else None,
        notice=notice,
    )


def get_owned_connection(db: Session, admin: Admin) -> ViewerPaymentConnection | None:
    return _owned_connection(db, admin)
