import base64
import hashlib
import json
from typing import TypedDict

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Request, Response

from app.config import get_settings

COOKIE_NAME = "aperture_recognized_accounts"
MAX_ACCOUNTS = 6


class RememberedAccount(TypedDict):
    id: str
    email: str
    provider: str
    label: str


def _fernet() -> Fernet:
    secret = get_settings().session_secret.encode()
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(secret).digest()))


def account_id(email: str, provider: str) -> str:
    return hashlib.sha256(f"{provider}:{email.lower()}".encode()).hexdigest()[:20]


def read_remembered(request: Request) -> list[RememberedAccount]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return []
    try:
        value = json.loads(_fernet().decrypt(token.encode()).decode())
        if not isinstance(value, list):
            return []
        return [item for item in value if isinstance(item, dict)][:MAX_ACCOUNTS]
    except (InvalidToken, json.JSONDecodeError, UnicodeDecodeError):
        return []


def remember_account(
    request: Request,
    response: Response,
    email: str,
    provider: str = "email",
    label: str | None = None,
) -> None:
    normalized = email.lower()
    entry: RememberedAccount = {
        "id": account_id(normalized, provider),
        "email": normalized,
        "provider": provider,
        "label": (label or normalized.split("@", 1)[0])[:50],
    }
    accounts = [item for item in read_remembered(request) if item["id"] != entry["id"]]
    accounts.insert(0, entry)
    encrypted = _fernet().encrypt(json.dumps(accounts[:MAX_ACCOUNTS]).encode()).decode()
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME,
        encrypted,
        max_age=365 * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )


def forget_account(request: Request, response: Response, identity_id: str) -> None:
    accounts = [item for item in read_remembered(request) if item["id"] != identity_id]
    settings = get_settings()
    if not accounts:
        response.delete_cookie(COOKIE_NAME, path="/", domain=settings.session_cookie_domain)
        return
    response.set_cookie(
        COOKIE_NAME,
        _fernet().encrypt(json.dumps(accounts).encode()).decode(),
        max_age=365 * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )
