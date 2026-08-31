import hashlib
import secrets
from datetime import UTC, datetime
from typing import Annotated

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError
from fastapi import Cookie, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Admin, AdminSession, DeviceSession, User
from app.site_domain_service import PUBLIC_ORIGIN_HEADER, resolve_request_public_origin

password_hasher = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=4)
DbSession = Annotated[Session, Depends(get_db)]


def hash_password(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(password_hash: str | None, password: str) -> bool:
    if not password_hash:
        return False
    try:
        return password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def new_session_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(48)
    return token, hashlib.sha256(token.encode()).hexdigest()


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def require_customer(
    db: DbSession,
    token: Annotated[str | None, Cookie(alias=get_settings().customer_session_cookie)] = None,
) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.scalar(
        select(DeviceSession).where(
            DeviceSession.token_hash == token_hash(token),
            DeviceSession.revoked_at.is_(None),
            DeviceSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None or not session.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired")
    return session.user


def require_customer_session(
    db: DbSession,
    token: Annotated[str | None, Cookie(alias=get_settings().customer_session_cookie)] = None,
) -> DeviceSession:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    session = db.scalar(
        select(DeviceSession).where(
            DeviceSession.token_hash == token_hash(token),
            DeviceSession.revoked_at.is_(None),
            DeviceSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None or not session.user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session is invalid or expired")
    return session


def require_admin(
    db: DbSession,
    token: Annotated[str | None, Cookie(alias=get_settings().admin_session_cookie)] = None,
) -> Admin:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Administrator authentication required")
    session = db.scalar(
        select(AdminSession).where(
            AdminSession.token_hash == token_hash(token),
            AdminSession.revoked_at.is_(None),
            AdminSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None or not session.admin.is_active:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED, "Administrator session is invalid or expired"
        )
    return session.admin


def require_trusted_origin(request: Request, db: DbSession) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    settings = get_settings()
    allowed = {
        str(settings.web_origin).rstrip("/"),
        str(settings.api_origin).rstrip("/"),
    }
    if getattr(settings, "admin_web_origin", None) is not None:
        allowed.add(str(settings.admin_web_origin).rstrip("/"))
    if request.headers.get(PUBLIC_ORIGIN_HEADER) is not None:
        resolve_request_public_origin(db, request, require_active=True)
        return
    if origin is not None and origin.rstrip("/") in allowed:
        return
    if settings.app_env == "production" and origin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Request origin is required")
    if origin is None:
        return
    try:
        resolve_request_public_origin(db, request, require_active=True)
    except HTTPException as error:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Untrusted request origin") from error
