import hashlib
import hmac
import secrets
from typing import Annotated

from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.auth import DbSession, token_hash
from app.config import get_settings
from app.platform_models import PlatformAccount, PlatformSession
from app.site_domain_service import EDGE_SECRET_HEADER, PUBLIC_ORIGIN_HEADER, SAFE_REQUEST_METHODS


def require_platform_origin(request: Request) -> None:
    """Keep control-plane mutations on Aperture-owned origins, never tenant aliases."""
    if request.method in SAFE_REQUEST_METHODS:
        return
    settings = get_settings()
    allowed = {
        str(settings.web_origin).rstrip("/"),
        str(settings.api_origin).rstrip("/"),
    }
    supplied_origin = request.headers.get("origin")
    asserted_origin = request.headers.get(PUBLIC_ORIGIN_HEADER)

    if asserted_origin is not None:
        expected = (
            settings.custom_domain_edge_secret.get_secret_value()
            if settings.custom_domain_edge_secret is not None
            else ""
        )
        supplied_secret = request.headers.get(EDGE_SECRET_HEADER, "")
        if (
            not expected
            or not supplied_secret
            or not secrets.compare_digest(expected, supplied_secret)
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform origin assertion is invalid")
        if asserted_origin.rstrip("/") not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform origin is required")
        if supplied_origin is not None and supplied_origin.rstrip("/") != asserted_origin.rstrip(
            "/"
        ):
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin does not match host")
        return

    if supplied_origin is not None and supplied_origin.rstrip("/") in allowed:
        return
    if supplied_origin is None and settings.app_env != "production":
        return
    raise HTTPException(status.HTTP_403_FORBIDDEN, "Platform origin is required")


def require_platform_session(
    db: DbSession,
    token: Annotated[
        str | None,
        Cookie(alias=get_settings().platform_session_cookie),
    ] = None,
) -> PlatformSession:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform authentication required")
    session = db.scalar(
        select(PlatformSession).where(
            PlatformSession.token_hash == token_hash(token),
            PlatformSession.revoked_at.is_(None),
            PlatformSession.expires_at > func.transaction_timestamp(),
        )
    )
    if session is None or not session.account.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Platform session is invalid or expired",
        )
    return session


def require_platform_account(
    session: Annotated[PlatformSession, Depends(require_platform_session)],
) -> PlatformAccount:
    return session.account


def require_verified_platform_account(
    account: Annotated[PlatformAccount, Depends(require_platform_account)],
) -> PlatformAccount:
    if account.email_verified_at is None:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "platform_email_verification_required",
                "message": "Verify the platform account email before reserving a template.",
            },
        )
    return account


def platform_rate_limit_identifier(namespace: str, value: object) -> str:
    """Pseudonymize identifiers before they enter Redis rate-limit keys."""
    settings = get_settings()
    return hmac.new(
        settings.session_secret.encode("utf-8"),
        f"platform-rate-limit:{namespace}:{value}".encode(),
        hashlib.sha256,
    ).hexdigest()


PlatformIdentity = Annotated[PlatformAccount, Depends(require_platform_account)]
VerifiedPlatformIdentity = Annotated[
    PlatformAccount, Depends(require_verified_platform_account)
]
CurrentPlatformSession = Annotated[PlatformSession, Depends(require_platform_session)]
