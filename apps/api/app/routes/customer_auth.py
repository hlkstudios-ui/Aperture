from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload

from app.auth import (
    DbSession,
    hash_password,
    new_session_token,
    require_customer,
    require_customer_session,
    require_trusted_origin,
    token_hash,
    verify_password,
)
from app.captcha import verify_captcha
from app.config import get_settings
from app.email_delivery import send_password_reset
from app.models import DeviceSession, PasswordResetToken, Profile, ProfilePreference, User
from app.rate_limit import enforce_rate_limit
from app.remembered_accounts import forget_account, read_remembered, remember_account
from app.schemas import (
    AccountResponse,
    LoginRequest,
    PasswordResetConfirm,
    PasswordResetRequest,
    PasswordResetRequestResponse,
    ProfileResponse,
    RegisterRequest,
)

router = APIRouter(
    prefix="/auth", tags=["customer authentication"], dependencies=[Depends(require_trusted_origin)]
)
settings = get_settings()


def account_response(user: User, active_profile_id=None) -> AccountResponse:
    return AccountResponse(
        id=user.id,
        email=user.email,
        profiles=[ProfileResponse.model_validate(profile) for profile in user.profiles],
        active_profile_id=active_profile_id,
    )


def set_session_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        settings.customer_session_cookie,
        token,
        max_age=settings.customer_session_days * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )


@router.post("/register", response_model=AccountResponse, status_code=status.HTTP_201_CREATED)
async def register(
    payload: RegisterRequest, request: Request, response: Response, db: DbSession
) -> AccountResponse:
    await verify_captcha(payload.captcha_token, request)
    email = str(payload.email).lower()
    await enforce_rate_limit(
        f"register:{request.client.host if request.client else 'unknown'}",
        limit=settings.registration_rate_limit_per_hour,
        window_seconds=3600,
    )
    if db.scalar(select(User.id).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")

    user = User(email=email, password_hash=hash_password(payload.password))
    profile = Profile(name=payload.profile_name.strip())
    profile.preference = ProfilePreference()
    user.profiles.append(profile)
    db.add(user)
    db.flush()

    raw_token, hashed_token = new_session_token()
    session = DeviceSession(
        user=user,
        active_profile_id=profile.id,
        token_hash=hashed_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.customer_session_days),
    )
    db.add(session)
    db.commit()
    set_session_cookie(response, raw_token)
    remember_account(request, response, email, label=profile.name)
    return account_response(user, profile.id)


@router.post("/login", response_model=AccountResponse)
async def login(
    payload: LoginRequest, request: Request, response: Response, db: DbSession
) -> AccountResponse:
    await verify_captcha(payload.captcha_token, request)
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"customer-login:{client_ip}:{email}", limit=8, window_seconds=900)
    user = db.scalar(
        select(User)
        .options(selectinload(User.profiles).selectinload(Profile.preference))
        .where(User.email == email)
    )
    if (
        user is None
        or not user.is_active
        or not verify_password(user.password_hash, payload.password)
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    raw_token, hashed_token = new_session_token()
    active_profile_id = user.profiles[0].id if user.profiles else None
    db.add(
        DeviceSession(
            user=user,
            active_profile_id=active_profile_id,
            token_hash=hashed_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.now(UTC) + timedelta(days=settings.customer_session_days),
        )
    )
    db.commit()
    set_session_cookie(response, raw_token)
    remember_account(
        request, response, email, label=user.profiles[0].name if user.profiles else None
    )
    return account_response(user, active_profile_id)


@router.get("/remembered-accounts")
def remembered_accounts(request: Request) -> dict:
    return {"accounts": read_remembered(request)}


@router.delete("/remembered-accounts/{identity_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_remembered_account(identity_id: str, request: Request, response: Response) -> None:
    forget_account(request, response, identity_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession,
    session: Annotated[DeviceSession, Depends(require_customer_session)],
) -> None:
    session.revoked_at = datetime.now(UTC)
    db.commit()
    response.delete_cookie(
        settings.customer_session_cookie, path="/", domain=settings.session_cookie_domain
    )


@router.get("/me", response_model=AccountResponse)
def me(
    db: DbSession,
    user: Annotated[User, Depends(require_customer)],
    session: Annotated[DeviceSession, Depends(require_customer_session)],
) -> AccountResponse:
    hydrated = db.scalar(
        select(User)
        .options(selectinload(User.profiles).selectinload(Profile.preference))
        .where(User.id == user.id)
    )
    return account_response(hydrated, session.active_profile_id)


@router.post("/logout-all", status_code=status.HTTP_204_NO_CONTENT)
def logout_all(
    response: Response, db: DbSession, user: Annotated[User, Depends(require_customer)]
) -> None:
    now = datetime.now(UTC)
    for session in user.sessions:
        if session.revoked_at is None:
            session.revoked_at = now
    db.commit()
    response.delete_cookie(
        settings.customer_session_cookie, path="/", domain=settings.session_cookie_domain
    )


@router.post("/password-reset/request", response_model=PasswordResetRequestResponse)
async def request_password_reset(
    payload: PasswordResetRequest, request: Request, db: DbSession
) -> PasswordResetRequestResponse:
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"password-reset:{client_ip}:{email}", limit=5, window_seconds=3600)
    user = db.scalar(select(User).where(User.email == email, User.is_active.is_(True)))
    development_token = None
    if user is not None:
        now = datetime.now(UTC)
        db.execute(
            update(PasswordResetToken)
            .where(PasswordResetToken.user_id == user.id, PasswordResetToken.used_at.is_(None))
            .values(used_at=now)
        )
        raw_token, hashed_token = new_session_token()
        db.add(
            PasswordResetToken(
                user_id=user.id,
                token_hash=hashed_token,
                expires_at=now + timedelta(minutes=30),
            )
        )
        if settings.app_env in {"development", "test"}:
            development_token = raw_token
        else:
            try:
                await send_password_reset(user.email, raw_token)
            except RuntimeError as error:
                db.rollback()
                raise HTTPException(
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                    "Password-reset delivery is unavailable",
                ) from error
        db.commit()
    return PasswordResetRequestResponse(
        message=(
            "If an active account matches that email, password-reset instructions have been issued."
        ),
        development_reset_token=development_token,
    )


@router.post("/password-reset/confirm")
async def confirm_password_reset(
    payload: PasswordResetConfirm, request: Request, db: DbSession
) -> dict[str, str]:
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"password-reset-confirm:{client_ip}", limit=10, window_seconds=900)
    reset = db.scalar(
        select(PasswordResetToken).where(
            PasswordResetToken.token_hash == token_hash(payload.token),
            PasswordResetToken.used_at.is_(None),
            PasswordResetToken.expires_at > datetime.now(UTC),
        )
    )
    if reset is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Reset token is invalid or expired")
    now = datetime.now(UTC)
    reset.user.password_hash = hash_password(payload.password)
    reset.used_at = now
    for session in reset.user.sessions:
        if session.revoked_at is None:
            session.revoked_at = now
    db.commit()
    return {"status": "password_updated"}
