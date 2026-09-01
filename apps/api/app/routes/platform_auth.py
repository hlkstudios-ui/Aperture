from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import DbSession, hash_password, new_session_token, verify_password
from app.captcha import verify_captcha
from app.config import get_settings
from app.platform_models import PlatformAccount, PlatformAuditEvent, PlatformSession
from app.platform_schemas import (
    PlatformAccountResponse,
    PlatformAuthConfiguration,
    PlatformLoginRequest,
    PlatformRegisterRequest,
)
from app.platform_security import (
    CurrentPlatformSession,
    PlatformIdentity,
    require_platform_origin,
)
from app.rate_limit import enforce_rate_limit

router = APIRouter(
    prefix="/platform/auth",
    tags=["platform authentication"],
    dependencies=[Depends(require_platform_origin)],
)
settings = get_settings()
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Cookie",
}


def _no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _account_response(account: PlatformAccount) -> PlatformAccountResponse:
    return PlatformAccountResponse(
        id=account.id, email=account.email, created_at=account.created_at
    )


def _audit(
    db: DbSession,
    request: Request,
    *,
    action: str,
    outcome: str,
    account: PlatformAccount | None,
) -> None:
    db.add(
        PlatformAuditEvent(
            actor_type="platform_account" if account is not None else "system",
            actor_account_id=account.id if account is not None else None,
            action=action,
            outcome=outcome,
            resource_type="platform_account" if account is not None else None,
            resource_id=account.id if account is not None else None,
            ip_address=request.client.host[:64] if request.client else None,
            detail={"schema_version": 1},
        )
    )


def _commit_audit_best_effort(
    db: DbSession,
    request: Request,
    *,
    action: str,
    outcome: str,
    account: PlatformAccount | None,
) -> None:
    try:
        _audit(db, request, action=action, outcome=outcome, account=account)
        db.commit()
    except SQLAlchemyError:
        db.rollback()


def _issue_session(
    db: DbSession,
    request: Request,
    response: Response,
    account: PlatformAccount,
    *,
    action: str,
) -> PlatformAccountResponse:
    raw_token, hashed_token = new_session_token()
    db.add(
        PlatformSession(
            account=account,
            token_hash=hashed_token,
            user_agent=(request.headers.get("user-agent") or "")[:500] or None,
            ip_address=request.client.host[:64] if request.client else None,
            expires_at=datetime.now(UTC) + timedelta(days=settings.platform_session_days),
        )
    )
    _audit(
        db,
        request,
        action=action,
        outcome="succeeded",
        account=account,
    )
    db.commit()
    response.set_cookie(
        settings.platform_session_cookie,
        raw_token,
        max_age=settings.platform_session_days * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
    )
    _no_store(response)
    return _account_response(account)


@router.get("/config", response_model=PlatformAuthConfiguration)
def auth_configuration() -> PlatformAuthConfiguration:
    return PlatformAuthConfiguration(
        captcha={
            "required": settings.captcha_required,
            "test_mode": settings.app_env in {"development", "test"} and settings.captcha_test_mode,
        }
    )


@router.post(
    "/register",
    response_model=PlatformAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: PlatformRegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> PlatformAccountResponse:
    await verify_captcha(payload.captcha_token, request)
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        f"platform-register:{client_ip}",
        limit=settings.registration_rate_limit_per_hour,
        window_seconds=3600,
    )
    email = str(payload.email).lower()
    if db.scalar(select(PlatformAccount.id).where(PlatformAccount.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "A platform account with this email exists")
    account = PlatformAccount(email=email, password_hash=hash_password(payload.password))
    db.add(account)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A platform account with this email exists",
        ) from None
    return _issue_session(
        db,
        request,
        response,
        account,
        action="platform_account.registered",
    )


@router.post("/login", response_model=PlatformAccountResponse)
async def login(
    payload: PlatformLoginRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> PlatformAccountResponse:
    await verify_captcha(payload.captcha_token, request)
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"platform-login:{client_ip}:{email}", limit=8, window_seconds=900)
    account = db.scalar(select(PlatformAccount).where(PlatformAccount.email == email))
    if (
        account is None
        or not account.is_active
        or not verify_password(account.password_hash, payload.password)
    ):
        _commit_audit_best_effort(
            db,
            request,
            action="platform_account.login",
            outcome="denied",
            account=account,
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    return _issue_session(
        db,
        request,
        response,
        account,
        action="platform_account.login",
    )


@router.get("/me", response_model=PlatformAccountResponse)
def me(response: Response, account: PlatformIdentity) -> PlatformAccountResponse:
    _no_store(response)
    return _account_response(account)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    account: PlatformIdentity,
    session: CurrentPlatformSession,
) -> None:
    session.revoked_at = datetime.now(UTC)
    _audit(
        db,
        request,
        action="platform_account.logout",
        outcome="succeeded",
        account=account,
    )
    db.commit()
    response.delete_cookie(settings.platform_session_cookie, path="/")
    _no_store(response)
