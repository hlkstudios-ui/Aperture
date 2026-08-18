from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select

from app.auth import (
    DbSession,
    new_session_token,
    require_admin,
    require_trusted_origin,
    token_hash,
    verify_password,
)
from app.config import get_settings
from app.mfa import (
    decrypt_secret,
    encrypt_secret,
    generate_recovery_codes,
    generate_totp_secret,
    hash_recovery_code,
    provisioning_uri,
    verify_totp,
)
from app.models import Admin, AdminMfaRecoveryCode, AdminSession, AuditLog
from app.rate_limit import enforce_rate_limit
from app.schemas import (
    AdminLoginRequest,
    AdminResponse,
    MfaCodeRequest,
    MfaConfirmationResponse,
    MfaEnrollmentResponse,
)

router = APIRouter(
    prefix="/admin/auth",
    tags=["administrator authentication"],
    dependencies=[Depends(require_trusted_origin)],
)
settings = get_settings()


def audit(db: DbSession, request: Request, action: str, outcome: str, admin_id=None) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin_id,
            action=action,
            outcome=outcome,
            ip_address=request.client.host if request.client else None,
        )
    )


@router.post("/login", response_model=AdminResponse)
async def login(
    payload: AdminLoginRequest, request: Request, response: Response, db: DbSession
) -> AdminResponse:
    email = str(payload.email).lower()
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"admin-login:{client_ip}:{email}", limit=10, window_seconds=900)
    admin = db.scalar(select(Admin).where(Admin.email == email))
    if (
        admin is None
        or not admin.is_active
        or not verify_password(admin.password_hash, payload.password)
    ):
        audit(db, request, "admin.login", "denied", admin.id if admin else None)
        db.commit()
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid administrator credentials")
    if admin.mfa_enabled:
        if not payload.mfa_code:
            audit(db, request, "admin.login.mfa", "denied", admin.id)
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code is required")
        totp_valid = bool(
            admin.mfa_secret_encrypted
            and verify_totp(decrypt_secret(admin.mfa_secret_encrypted), payload.mfa_code)
        )
        recovery = None
        if not totp_valid:
            recovery = db.scalar(
                select(AdminMfaRecoveryCode).where(
                    AdminMfaRecoveryCode.admin_id == admin.id,
                    AdminMfaRecoveryCode.code_hash == hash_recovery_code(payload.mfa_code),
                    AdminMfaRecoveryCode.used_at.is_(None),
                )
            )
        if not totp_valid and recovery is None:
            audit(db, request, "admin.login.mfa", "denied", admin.id)
            db.commit()
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "MFA code is invalid")
        if recovery is not None:
            recovery.used_at = datetime.now(UTC)
            audit(db, request, "admin.mfa.recovery_used", "succeeded", admin.id)

    raw_token, hashed_token = new_session_token()
    db.add(
        AdminSession(
            admin=admin,
            token_hash=hashed_token,
            user_agent=request.headers.get("user-agent"),
            ip_address=request.client.host if request.client else None,
            expires_at=datetime.now(UTC) + timedelta(hours=settings.admin_session_hours),
        )
    )
    audit(db, request, "admin.login", "succeeded", admin.id)
    db.commit()
    response.set_cookie(
        settings.admin_session_cookie,
        raw_token,
        max_age=settings.admin_session_hours * 3600,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="strict",
        path="/",
        domain=settings.admin_session_cookie_domain,
    )
    return AdminResponse(id=admin.id, email=admin.email, mfa_enabled=admin.mfa_enabled)


@router.get("/me", response_model=AdminResponse)
def me(admin: Annotated[Admin, Depends(require_admin)]) -> AdminResponse:
    return AdminResponse(id=admin.id, email=admin.email, mfa_enabled=admin.mfa_enabled)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    db: DbSession,
    admin: Annotated[Admin, Depends(require_admin)],
) -> None:
    cookie = request.cookies.get(settings.admin_session_cookie)
    session = (
        db.scalar(select(AdminSession).where(AdminSession.token_hash == token_hash(cookie)))
        if cookie
        else None
    )
    if session:
        session.revoked_at = datetime.now(UTC)
    audit(db, request, "admin.logout", "succeeded", admin.id)
    db.commit()
    response.delete_cookie(
        settings.admin_session_cookie, path="/", domain=settings.admin_session_cookie_domain
    )


@router.get("/authorization-check")
def authorization_check(admin: Annotated[Admin, Depends(require_admin)]) -> dict[str, str]:
    return {"status": "authorized", "admin_id": str(admin.id)}


@router.post("/mfa/enroll", response_model=MfaEnrollmentResponse)
def enroll_mfa(
    request: Request,
    db: DbSession,
    admin: Annotated[Admin, Depends(require_admin)],
) -> MfaEnrollmentResponse:
    secret = generate_totp_secret()
    admin.mfa_secret_encrypted = encrypt_secret(secret)
    admin.mfa_enabled = False
    db.execute(delete(AdminMfaRecoveryCode).where(AdminMfaRecoveryCode.admin_id == admin.id))
    audit(db, request, "admin.mfa.enrollment_started", "succeeded", admin.id)
    db.commit()
    return MfaEnrollmentResponse(
        secret=secret, provisioning_uri=provisioning_uri(secret, admin.email)
    )


@router.post("/mfa/confirm", response_model=MfaConfirmationResponse)
def confirm_mfa(
    payload: MfaCodeRequest,
    request: Request,
    db: DbSession,
    admin: Annotated[Admin, Depends(require_admin)],
) -> MfaConfirmationResponse:
    if not admin.mfa_secret_encrypted:
        raise HTTPException(status.HTTP_409_CONFLICT, "MFA enrollment has not been started")
    if not verify_totp(decrypt_secret(admin.mfa_secret_encrypted), payload.code):
        audit(db, request, "admin.mfa.enrollment_confirm", "denied", admin.id)
        db.commit()
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "MFA code is invalid")
    recovery_codes = generate_recovery_codes()
    db.execute(delete(AdminMfaRecoveryCode).where(AdminMfaRecoveryCode.admin_id == admin.id))
    db.add_all(
        [
            AdminMfaRecoveryCode(admin_id=admin.id, code_hash=hash_recovery_code(code))
            for code in recovery_codes
        ]
    )
    admin.mfa_enabled = True
    audit(db, request, "admin.mfa.enabled", "succeeded", admin.id)
    db.commit()
    return MfaConfirmationResponse(enabled=True, recovery_codes=recovery_codes)
