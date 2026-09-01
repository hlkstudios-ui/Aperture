import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from app.auth import DbSession, hash_password, new_session_token, token_hash, verify_password
from app.captcha import verify_captcha
from app.config import get_settings
from app.email_delivery import send_platform_email_verification
from app.platform_models import (
    PlatformAccount,
    PlatformAuditEvent,
    PlatformEmailVerificationToken,
    PlatformSession,
    TemplateRental,
)
from app.platform_schemas import (
    PlatformAccountResponse,
    PlatformAuthConfiguration,
    PlatformEmailVerificationClaimRequest,
    PlatformEmailVerificationDeliveryResponse,
    PlatformEmailVerificationRequest,
    PlatformLoginRequest,
    PlatformRegisterRequest,
    PlatformRegistrationResponse,
)
from app.platform_security import (
    CurrentPlatformSession,
    PlatformIdentity,
    platform_rate_limit_identifier,
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


@dataclass(frozen=True)
class _FinalizedVerificationDelivery:
    account: PlatformAccountResponse
    delivery: PlatformEmailVerificationDeliveryResponse
    session_valid: bool


@dataclass(frozen=True)
class _IssuedPlatformSession:
    account: PlatformAccountResponse
    session_id: uuid.UUID


def _no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _database_now(db: DbSession) -> datetime:
    now = db.scalar(select(func.transaction_timestamp()))
    if not isinstance(now, datetime):
        raise RuntimeError("Database clock is unavailable")
    return now


def _constraint_name(error: IntegrityError) -> str | None:
    diagnostics = getattr(error.orig, "diag", None)
    value = getattr(diagnostics, "constraint_name", None)
    return value if isinstance(value, str) else None


def _account_response(account: PlatformAccount) -> PlatformAccountResponse:
    return PlatformAccountResponse(
        id=account.id,
        email=account.email,
        email_verified=account.email_verified_at is not None,
        unverified_account_expires_at=account.email_verification_expires_at,
        created_at=account.created_at,
    )


def _audit(
    db: DbSession,
    request: Request,
    *,
    action: str,
    outcome: str,
    account: PlatformAccount | None,
    detail: dict[str, object] | None = None,
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
            detail={"schema_version": 1, **(detail or {})},
        )
    )


def _commit_audit_best_effort(
    db: DbSession,
    request: Request,
    *,
    action: str,
    outcome: str,
    account: PlatformAccount | None,
    detail: dict[str, object] | None = None,
) -> None:
    try:
        _audit(
            db,
            request,
            action=action,
            outcome=outcome,
            account=account,
            detail=detail,
        )
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
    now: datetime,
) -> _IssuedPlatformSession:
    raw_token, hashed_token = new_session_token()
    session = PlatformSession(
        account=account,
        token_hash=hashed_token,
        user_agent=(request.headers.get("user-agent") or "")[:500] or None,
        ip_address=request.client.host[:64] if request.client else None,
        expires_at=now + timedelta(days=settings.platform_session_days),
    )
    db.add(session)
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
    return _IssuedPlatformSession(
        account=_account_response(account),
        session_id=session.id,
    )


def _require_locked_current_session(
    db: DbSession,
    account: PlatformAccount,
    current_session: PlatformSession,
    now: datetime,
) -> PlatformSession:
    locked_session = db.scalar(
        select(PlatformSession)
        .where(
            PlatformSession.id == current_session.id,
            PlatformSession.account_id == account.id,
            PlatformSession.revoked_at.is_(None),
            PlatformSession.expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked_session is None:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Platform session is invalid or expired",
        )
    return locked_session


def _terminalize_live_verification_tokens(
    db: DbSession,
    account: PlatformAccount,
    now: datetime,
) -> None:
    db.execute(
        update(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == account.id,
            PlatformEmailVerificationToken.state == "active",
        )
        .values(state="superseded", used_at=now)
    )
    db.execute(
        update(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == account.id,
            PlatformEmailVerificationToken.state == "pending_delivery",
        )
        .values(state="delivery_failed", used_at=now)
    )


def _create_verification_token(
    db: DbSession,
    account: PlatformAccount,
    now: datetime,
    *,
    state: str,
) -> tuple[PlatformEmailVerificationToken, str]:
    account_expires_at = account.email_verification_expires_at
    if account_expires_at is None or account_expires_at <= now:
        raise RuntimeError("A verification token requires a live unverified account")
    expires_at = min(
        now + timedelta(minutes=settings.platform_email_verification_minutes),
        account_expires_at,
    )
    raw_token, hashed_token = new_session_token()
    verification = PlatformEmailVerificationToken(
        account=account,
        token_hash=hashed_token,
        expires_at=expires_at,
        state=state,
        created_at=now,
    )
    db.add(verification)
    db.flush()
    return verification, raw_token


async def _deliver_verification(
    email: str,
    raw_token: str,
    expires_at: datetime,
) -> PlatformEmailVerificationDeliveryResponse:
    if settings.app_env in {"development", "test"}:
        return PlatformEmailVerificationDeliveryResponse(
            status="development",
            verification_token_expires_at=expires_at,
            development_verification_token=raw_token,
        )
    try:
        await send_platform_email_verification(email, raw_token, expires_at)
    except RuntimeError:
        return PlatformEmailVerificationDeliveryResponse(
            status="unavailable",
            verification_token_expires_at=expires_at,
        )
    return PlatformEmailVerificationDeliveryResponse(
        status="sent",
        verification_token_expires_at=expires_at,
    )


def _finalize_verification_delivery(
    db: DbSession,
    request: Request,
    *,
    account_id: uuid.UUID,
    session_id: uuid.UUID,
    verification_id: uuid.UUID,
    verification_expires_at: datetime,
    delivery: PlatformEmailVerificationDeliveryResponse,
) -> _FinalizedVerificationDelivery:
    locked = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform account is unavailable")
    finalized_at = _database_now(db)
    valid_session = db.scalar(
        select(PlatformSession)
        .where(
            PlatformSession.id == session_id,
            PlatformSession.account_id == account_id,
            PlatformSession.revoked_at.is_(None),
            PlatformSession.expires_at > finalized_at,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    pending = db.scalar(
        select(PlatformEmailVerificationToken)
        .where(PlatformEmailVerificationToken.id == verification_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    promoted = False
    activation = pending.state if pending is not None else "missing"
    session_is_valid = valid_session is not None and locked.is_active
    delivery_is_usable = (
        delivery.status in {"development", "sent"}
        and verification_expires_at > finalized_at
        and locked.is_active
        and locked.email_verified_at is None
        and locked.email_verification_expires_at is not None
        and locked.email_verification_expires_at > finalized_at
        and (delivery.status == "sent" or session_is_valid)
    )
    if pending is not None and pending.state == "pending_delivery":
        if delivery_is_usable:
            db.execute(
                update(PlatformEmailVerificationToken)
                .where(
                    PlatformEmailVerificationToken.account_id == account_id,
                    PlatformEmailVerificationToken.state == "active",
                )
                .values(state="superseded", used_at=finalized_at)
            )
            db.flush()
            pending.state = "active"
            db.flush()
            promoted = True
            activation = "promoted"
        else:
            pending.state = "delivery_failed"
            pending.used_at = finalized_at
            db.flush()
            activation = "delivery_failed"

    _audit(
        db,
        request,
        action="platform_account.email_verification_delivery",
        outcome="failed" if delivery.status == "unavailable" else "succeeded",
        account=locked,
        detail={
            "delivery_result": delivery.status,
            "token_activation": activation,
        },
    )
    active_expiry = db.scalar(
        select(PlatformEmailVerificationToken.expires_at).where(
            PlatformEmailVerificationToken.account_id == account_id,
            PlatformEmailVerificationToken.state == "active",
            PlatformEmailVerificationToken.expires_at > finalized_at,
        )
    )
    account_response = _account_response(locked)
    if locked.email_verified_at is not None:
        response_delivery = PlatformEmailVerificationDeliveryResponse(
            status="already_verified",
            verification_token_expires_at=None,
        )
    elif promoted:
        response_delivery = delivery
    else:
        response_delivery = PlatformEmailVerificationDeliveryResponse(
            status="unavailable",
            verification_token_expires_at=active_expiry,
        )
    db.commit()
    return _FinalizedVerificationDelivery(
        account=account_response,
        delivery=response_delivery,
        session_valid=session_is_valid,
    )


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
    response_model=PlatformRegistrationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: PlatformRegisterRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> PlatformRegistrationResponse:
    await verify_captcha(payload.captcha_token, request)
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(
        f"platform-register:{client_ip}",
        limit=settings.registration_rate_limit_per_hour,
        window_seconds=3600,
    )
    email = str(payload.email).lower()
    password_hash = hash_password(payload.password)
    account = db.scalar(
        select(PlatformAccount).where(PlatformAccount.email == email).with_for_update()
    )
    now = _database_now(db)
    action = "platform_account.registered"
    if account is None:
        account = PlatformAccount(
            email=email,
            password_hash=password_hash,
            email_verification_expires_at=now
            + timedelta(hours=settings.platform_unverified_account_hours),
        )
        db.add(account)
        try:
            db.flush()
        except IntegrityError as error:
            db.rollback()
            if _constraint_name(error) != "ix_platform_accounts_email":
                raise
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A platform account with this email exists",
            ) from None
    else:
        has_rental = db.scalar(
            select(TemplateRental.id).where(TemplateRental.account_id == account.id).limit(1)
        )
        if (
            account.email_verified_at is not None
            or account.email_verification_expires_at is None
            or account.email_verification_expires_at > now
            or has_rental is not None
        ):
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                "A platform account with this email exists",
            )
        account.password_hash = password_hash
        account.is_active = True
        account.email_verification_expires_at = now + timedelta(
            hours=settings.platform_unverified_account_hours
        )
        db.execute(
            update(PlatformSession)
            .where(
                PlatformSession.account_id == account.id,
                PlatformSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        action = "platform_account.registration_reclaimed"
    _terminalize_live_verification_tokens(db, account, now)
    verification, raw_verification_token = _create_verification_token(
        db,
        account,
        now,
        state="pending_delivery",
    )
    account_id = account.id
    verification_id = verification.id
    verification_expires_at = verification.expires_at
    email = account.email
    issued = _issue_session(
        db,
        request,
        response,
        account,
        action=action,
        now=now,
    )
    delivery = await _deliver_verification(
        email,
        raw_verification_token,
        verification_expires_at,
    )
    finalized = _finalize_verification_delivery(
        db,
        request,
        account_id=account_id,
        session_id=issued.session_id,
        verification_id=verification_id,
        verification_expires_at=verification_expires_at,
        delivery=delivery,
    )
    if not finalized.session_valid or finalized.account.email_verified:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "platform_registration_superseded",
                "message": "This registration was superseded. Sign in or register again.",
            },
        )
    return PlatformRegistrationResponse(
        **finalized.account.model_dump(),
        verification_delivery=finalized.delivery.status,
        verification_token_expires_at=finalized.delivery.verification_token_expires_at,
        development_verification_token=finalized.delivery.development_verification_token,
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
    identity = platform_rate_limit_identifier("login-email", email)
    await enforce_rate_limit(f"platform-login:{client_ip}:{identity}", limit=8, window_seconds=900)
    account = db.scalar(
        select(PlatformAccount).where(PlatformAccount.email == email).with_for_update()
    )
    now = _database_now(db)
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
    if (
        account.email_verified_at is None
        and account.email_verification_expires_at is not None
        and account.email_verification_expires_at <= now
    ):
        _commit_audit_best_effort(
            db,
            request,
            action="platform_account.login",
            outcome="denied",
            account=account,
        )
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            detail={
                "code": "platform_email_verification_expired",
                "message": "Email verification expired. Register again to restart verification.",
            },
        )
    return _issue_session(
        db,
        request,
        response,
        account,
        action="platform_account.login",
        now=now,
    ).account


@router.get("/me", response_model=PlatformAccountResponse)
def me(response: Response, account: PlatformIdentity) -> PlatformAccountResponse:
    _no_store(response)
    return _account_response(account)


@router.post(
    "/email-verification/resend",
    response_model=PlatformEmailVerificationDeliveryResponse,
)
async def resend_email_verification(
    request: Request,
    response: Response,
    db: DbSession,
    account: PlatformIdentity,
    session: CurrentPlatformSession,
) -> PlatformEmailVerificationDeliveryResponse:
    _no_store(response)
    client_ip = request.client.host if request.client else "unknown"
    account_key = platform_rate_limit_identifier("verification-account", account.id)
    await enforce_rate_limit(
        f"platform-email-verification-resend:account:{account_key}",
        limit=5,
        window_seconds=3600,
    )
    await enforce_rate_limit(
        f"platform-email-verification-resend:ip:{client_ip}",
        limit=20,
        window_seconds=3600,
    )
    locked = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or not locked.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform account is unavailable")
    now = _database_now(db)
    _require_locked_current_session(db, locked, session, now)
    if locked.email_verified_at is not None:
        return PlatformEmailVerificationDeliveryResponse(
            status="already_verified",
            verification_token_expires_at=None,
        )
    if (
        locked.email_verification_expires_at is None
        or locked.email_verification_expires_at <= now
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            detail={
                "code": "platform_email_verification_expired",
                "message": "Email verification expired. Register again to restart verification.",
            },
        )
    existing_pending = db.scalar(
        select(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == locked.id,
            PlatformEmailVerificationToken.state == "pending_delivery",
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if existing_pending is not None:
        delivery_lease_expires_at = existing_pending.created_at + timedelta(
            seconds=settings.platform_email_delivery_lease_seconds
        )
        if delivery_lease_expires_at > now:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "code": "platform_email_verification_delivery_in_progress",
                    "message": "A verification email delivery is already in progress.",
                },
            )
        existing_pending.state = "delivery_failed"
        existing_pending.used_at = now
        db.flush()
        _audit(
            db,
            request,
            action="platform_account.email_verification_delivery",
            outcome="failed",
            account=locked,
            detail={"reason": "delivery_lease_expired"},
        )

    if locked.email_verification_expires_at <= now + timedelta(
        seconds=settings.platform_email_delivery_lease_seconds
    ):
        active_expiry = db.scalar(
            select(PlatformEmailVerificationToken.expires_at).where(
                PlatformEmailVerificationToken.account_id == locked.id,
                PlatformEmailVerificationToken.state == "active",
                PlatformEmailVerificationToken.expires_at > now,
            )
        )
        _audit(
            db,
            request,
            action="platform_account.email_verification_requested",
            outcome="denied",
            account=locked,
            detail={"reason": "account_verification_window_closing"},
        )
        db.commit()
        return PlatformEmailVerificationDeliveryResponse(
            status="unavailable",
            verification_token_expires_at=active_expiry,
        )

    verification, raw_token = _create_verification_token(
        db,
        locked,
        now,
        state="pending_delivery",
    )
    account_id = locked.id
    session_id = session.id
    verification_id = verification.id
    verification_expires_at = verification.expires_at
    email = locked.email
    _audit(
        db,
        request,
        action="platform_account.email_verification_requested",
        outcome="succeeded",
        account=locked,
    )
    db.commit()
    delivery = await _deliver_verification(
        email,
        raw_token,
        verification_expires_at,
    )
    finalized = _finalize_verification_delivery(
        db,
        request,
        account_id=account_id,
        session_id=session_id,
        verification_id=verification_id,
        verification_expires_at=verification_expires_at,
        delivery=delivery,
    )
    if not finalized.session_valid:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Platform session is invalid or expired",
        )
    return finalized.delivery


@router.post("/email-verification/confirm", response_model=PlatformAccountResponse)
async def confirm_email_verification(
    payload: PlatformEmailVerificationRequest,
    request: Request,
    response: Response,
    db: DbSession,
    account: PlatformIdentity,
    session: CurrentPlatformSession,
) -> PlatformAccountResponse:
    _no_store(response)
    client_ip = request.client.host if request.client else "unknown"
    account_key = platform_rate_limit_identifier("verification-account", account.id)
    await enforce_rate_limit(
        f"platform-email-verification-confirm:account:{account_key}",
        limit=10,
        window_seconds=900,
    )
    await enforce_rate_limit(
        f"platform-email-verification-confirm:ip:{client_ip}",
        limit=50,
        window_seconds=900,
    )
    locked = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or not locked.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform account is unavailable")
    now = _database_now(db)
    _require_locked_current_session(db, locked, session, now)
    if locked.email_verified_at is not None:
        return _account_response(locked)
    verification = db.scalar(
        select(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == locked.id,
            PlatformEmailVerificationToken.token_hash == token_hash(payload.token),
            PlatformEmailVerificationToken.state == "active",
            PlatformEmailVerificationToken.expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked.email_verification_expires_at is None
        or locked.email_verification_expires_at <= now
        or verification is None
    ):
        _commit_audit_best_effort(
            db,
            request,
            action="platform_account.email_verification_confirmed",
            outcome="denied",
            account=locked,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "platform_email_verification_invalid",
                "message": "Email verification token is invalid or expired.",
            },
    )
    locked.email_verified_at = now
    locked.email_verification_expires_at = None
    db.flush()
    verification.state = "used"
    verification.used_at = now
    db.flush()
    db.execute(
        update(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == locked.id,
            PlatformEmailVerificationToken.state == "pending_delivery",
        )
        .values(state="delivery_failed", used_at=now)
    )
    _audit(
        db,
        request,
        action="platform_account.email_verification_confirmed",
        outcome="succeeded",
        account=locked,
    )
    db.commit()
    return _account_response(locked)


@router.post("/email-verification/claim", response_model=PlatformAccountResponse)
async def claim_email_verification(
    payload: PlatformEmailVerificationClaimRequest,
    request: Request,
    response: Response,
    db: DbSession,
) -> PlatformAccountResponse:
    """Let the mailbox owner verify, set their password, and revoke preclaim sessions."""
    _no_store(response)
    await verify_captcha(payload.captcha_token, request)
    client_ip = request.client.host if request.client else "unknown"
    supplied_token_hash = token_hash(payload.token)
    token_key = platform_rate_limit_identifier(
        "verification-claim-token",
        supplied_token_hash,
    )
    await enforce_rate_limit(
        f"platform-email-verification-claim:token:{token_key}",
        limit=10,
        window_seconds=900,
    )
    await enforce_rate_limit(
        f"platform-email-verification-claim:ip:{client_ip}",
        limit=30,
        window_seconds=900,
    )

    lookup_now = _database_now(db)
    account_id = db.scalar(
        select(PlatformEmailVerificationToken.account_id).where(
            PlatformEmailVerificationToken.token_hash == supplied_token_hash,
            PlatformEmailVerificationToken.state == "active",
            PlatformEmailVerificationToken.expires_at > lookup_now,
        )
    )
    if account_id is None:
        _commit_audit_best_effort(
            db,
            request,
            action="platform_account.email_verification_claimed",
            outcome="denied",
            account=None,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "platform_email_verification_invalid",
                "message": "Email verification token is invalid or expired.",
            },
        )

    account_key = platform_rate_limit_identifier("verification-account", account_id)
    await enforce_rate_limit(
        f"platform-email-verification-claim:account:{account_key}",
        limit=10,
        window_seconds=900,
    )
    replacement_password_hash = hash_password(payload.password)
    locked = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account_id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    now = _database_now(db)
    verification = db.scalar(
        select(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == account_id,
            PlatformEmailVerificationToken.token_hash == supplied_token_hash,
            PlatformEmailVerificationToken.state == "active",
            PlatformEmailVerificationToken.expires_at > now,
        )
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if (
        locked is None
        or not locked.is_active
        or locked.email_verified_at is not None
        or locked.email_verification_expires_at is None
        or locked.email_verification_expires_at <= now
        or verification is None
    ):
        _commit_audit_best_effort(
            db,
            request,
            action="platform_account.email_verification_claimed",
            outcome="denied",
            account=locked,
        )
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "platform_email_verification_invalid",
                "message": "Email verification token is invalid or expired.",
            },
        )

    locked.password_hash = replacement_password_hash
    locked.email_verified_at = now
    locked.email_verification_expires_at = None
    db.flush()
    verification.state = "used"
    verification.used_at = now
    db.flush()
    db.execute(
        update(PlatformEmailVerificationToken)
        .where(
            PlatformEmailVerificationToken.account_id == locked.id,
            PlatformEmailVerificationToken.state == "pending_delivery",
        )
        .values(state="delivery_failed", used_at=now)
    )
    db.execute(
        update(PlatformSession)
        .where(
            PlatformSession.account_id == locked.id,
            PlatformSession.revoked_at.is_(None),
        )
        .values(revoked_at=now)
    )
    return _issue_session(
        db,
        request,
        response,
        locked,
        action="platform_account.email_verification_claimed",
        now=now,
    ).account


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    account: PlatformIdentity,
    session: CurrentPlatformSession,
) -> None:
    locked = db.scalar(
        select(PlatformAccount)
        .where(PlatformAccount.id == account.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    if locked is None or not locked.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Platform account is unavailable")
    now = _database_now(db)
    locked_session = _require_locked_current_session(db, locked, session, now)
    locked_session.revoked_at = now
    _audit(
        db,
        request,
        action="platform_account.logout",
        outcome="succeeded",
        account=locked,
    )
    db.commit()
    response.delete_cookie(
        settings.platform_session_cookie,
        path="/",
        secure=settings.app_env not in {"development", "test"},
        httponly=True,
        samesite="lax",
    )
    _no_store(response)
