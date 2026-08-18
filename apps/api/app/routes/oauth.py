import base64
import hashlib
import hmac
import json
import secrets
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode

import httpx
from authlib.jose import JsonWebKey, jwt
from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import DbSession, new_session_token
from app.config import get_settings
from app.models import DeviceSession, OAuthIdentity, Profile, ProfilePreference, User
from app.rate_limit import enforce_rate_limit
from app.remembered_accounts import remember_account

router = APIRouter(prefix="/auth/oauth", tags=["customer OAuth"])
settings = get_settings()


@dataclass(frozen=True)
class Provider:
    label: str
    authorize_url: str
    token_url: str
    scopes: str
    client_id: str | None
    client_secret: str | None
    user_url: str | None = None
    jwks_url: str | None = None


def providers() -> dict[str, Provider]:
    return {
        "google": Provider(
            "Google",
            "https://accounts.google.com/o/oauth2/v2/auth",
            "https://oauth2.googleapis.com/token",
            "openid email profile",
            settings.oauth_google_client_id,
            settings.oauth_google_client_secret,
            "https://openidconnect.googleapis.com/v1/userinfo",
        ),
        "microsoft": Provider(
            "Microsoft",
            "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
            "https://login.microsoftonline.com/common/oauth2/v2.0/token",
            "openid email profile User.Read",
            settings.oauth_microsoft_client_id,
            settings.oauth_microsoft_client_secret,
            "https://graph.microsoft.com/v1.0/me",
        ),
        "github": Provider(
            "GitHub",
            "https://github.com/login/oauth/authorize",
            "https://github.com/login/oauth/access_token",
            "read:user user:email",
            settings.oauth_github_client_id,
            settings.oauth_github_client_secret,
            "https://api.github.com/user",
        ),
        "apple": Provider(
            "Apple",
            "https://appleid.apple.com/auth/authorize",
            "https://appleid.apple.com/auth/token",
            "openid email name",
            settings.oauth_apple_client_id,
            settings.oauth_apple_client_secret,
            jwks_url="https://appleid.apple.com/auth/keys",
        ),
    }


def _configured(provider: Provider) -> bool:
    return bool(provider.client_id and provider.client_secret)


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def _signed_state(provider: str) -> str:
    payload = _b64(
        json.dumps(
            {
                "provider": provider,
                "exp": int(time.time()) + 600,
                "nonce": secrets.token_urlsafe(18),
            },
            separators=(",", ":"),
        ).encode()
    )
    signature = _b64(
        hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest()
    )
    return f"{payload}.{signature}"


def _validate_state(value: str, provider: str) -> None:
    try:
        payload, signature = value.split(".", 1)
        expected = _b64(
            hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        parsed = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if parsed["provider"] != provider or parsed["exp"] < time.time():
            raise ValueError
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid or expired sign-in request"
        ) from error


def _callback_url(provider: str) -> str:
    return f"{str(settings.api_origin).rstrip('/')}/auth/oauth/{provider}/callback"


@router.get("/providers")
def available_providers() -> dict:
    return {
        "captcha": {
            "required": settings.captcha_required,
            "test_mode": settings.app_env in {"development", "test"} and settings.captcha_test_mode,
        },
        "providers": [
            {"id": key, "label": value.label, "enabled": _configured(value)}
            for key, value in providers().items()
        ],
    }


@router.get("/{provider}/start")
async def start(provider: str, request: Request) -> RedirectResponse:
    available = providers()
    config = available.get(provider)
    if config is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Unknown identity provider")
    if not _configured(config):
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, f"{config.label} sign-in is not configured yet"
        )
    client_ip = request.client.host if request.client else "unknown"
    await enforce_rate_limit(f"oauth-start:{client_ip}", limit=30, window_seconds=900)
    state = _signed_state(provider)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    query = {
        "client_id": config.client_id,
        "redirect_uri": _callback_url(provider),
        "response_type": "code",
        "scope": config.scopes,
        "state": state,
        "code_challenge": challenge,
        "code_challenge_method": "S256",
    }
    if provider in {"google", "microsoft"}:
        query["prompt"] = "select_account"
    if provider == "apple":
        query["response_mode"] = "form_post"
    response = RedirectResponse(f"{config.authorize_url}?{urlencode(query)}", status_code=302)
    response.set_cookie(
        f"aperture_oauth_{provider}",
        verifier,
        max_age=600,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path=f"/auth/oauth/{provider}",
    )
    return response


async def _callback_params(request: Request) -> dict[str, str]:
    if request.method == "GET":
        return dict(request.query_params)
    parsed = parse_qs((await request.body()).decode())
    return {key: values[0] for key, values in parsed.items() if values}


async def _identity(
    config: Provider, provider: str, code: str, verifier: str
) -> tuple[str, str, str]:
    async with httpx.AsyncClient(
        timeout=12, headers={"Accept": "application/json", "User-Agent": "Aperture/1.0"}
    ) as client:
        token_response = await client.post(
            config.token_url,
            data={
                "client_id": config.client_id,
                "client_secret": config.client_secret,
                "code": code,
                "redirect_uri": _callback_url(provider),
                "grant_type": "authorization_code",
                "code_verifier": verifier,
            },
        )
        if token_response.is_error:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "The identity provider rejected this sign-in"
            )
        token = token_response.json()
        access_token = token.get("access_token")
        if provider == "apple":
            id_token = token.get("id_token")
            if not id_token or not config.jwks_url:
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Apple did not return an identity")
            keys = (await client.get(config.jwks_url)).json()
            claims = jwt.decode(
                id_token,
                JsonWebKey.import_key_set(keys),
                claims_options={
                    "iss": {"essential": True, "value": "https://appleid.apple.com"},
                    "aud": {"essential": True, "value": config.client_id},
                },
            )
            claims.validate()
            email = claims.get("email")
            subject = claims.get("sub")
            name = email.split("@", 1)[0] if email else "Apple Viewer"
        elif provider == "github":
            user = (
                await client.get(
                    config.user_url, headers={"Authorization": f"Bearer {access_token}"}
                )
            ).json()
            emails = (
                await client.get(
                    "https://api.github.com/user/emails",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            ).json()
            verified = next(
                (
                    entry["email"]
                    for entry in emails
                    if entry.get("primary") and entry.get("verified")
                ),
                None,
            ) or next((entry["email"] for entry in emails if entry.get("verified")), None)
            email, subject, name = (
                verified,
                str(user.get("id", "")),
                user.get("name") or user.get("login") or "GitHub Viewer",
            )
        else:
            user = (
                await client.get(
                    config.user_url, headers={"Authorization": f"Bearer {access_token}"}
                )
            ).json()
            if provider == "google" and not user.get("email_verified"):
                raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google email is not verified")
            email = user.get("email") or user.get("mail") or user.get("userPrincipalName")
            subject = str(user.get("sub") or user.get("id") or "")
            name = user.get("name") or (email.split("@", 1)[0] if email else "Viewer")
    if not email or not subject:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The provider did not share a verified email identity"
        )
    return email.lower(), subject, str(name)[:50]


@router.api_route("/{provider}/callback", methods=["GET", "POST"])
async def callback(provider: str, request: Request, db: DbSession) -> Response:
    config = providers().get(provider)
    if config is None or not _configured(config):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Identity provider is unavailable")
    params = await _callback_params(request)
    if params.get("error"):
        return RedirectResponse(
            f"{str(settings.web_origin).rstrip('/')}/login?oauth_error=cancelled", status_code=303
        )
    state, code = params.get("state", ""), params.get("code", "")
    _validate_state(state, provider)
    verifier = request.cookies.get(f"aperture_oauth_{provider}")
    if not code or not verifier:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incomplete sign-in response")
    email, subject, display_name = await _identity(config, provider, code, verifier)
    identity = db.scalar(
        select(OAuthIdentity)
        .options(
            selectinload(OAuthIdentity.user)
            .selectinload(User.profiles)
            .selectinload(Profile.preference)
        )
        .where(OAuthIdentity.provider == provider, OAuthIdentity.subject == subject)
    )
    if identity:
        user = identity.user
        identity.last_login_at = datetime.now(UTC)
    else:
        user = db.scalar(
            select(User)
            .options(selectinload(User.profiles).selectinload(Profile.preference))
            .where(User.email == email)
        )
        if user is None:
            user = User(email=email, password_hash=None)
            profile = Profile(name=display_name)
            profile.preference = ProfilePreference()
            user.profiles.append(profile)
            db.add(user)
            db.flush()
        identity = OAuthIdentity(user=user, provider=provider, subject=subject, email_at_link=email)
        db.add(identity)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This account is disabled")
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
    response = RedirectResponse(f"{str(settings.web_origin).rstrip('/')}/profiles", status_code=303)
    response.set_cookie(
        settings.customer_session_cookie,
        raw_token,
        max_age=settings.customer_session_days * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )
    remember_account(request, response, email, provider=provider, label=display_name)
    response.delete_cookie(f"aperture_oauth_{provider}", path=f"/auth/oauth/{provider}")
    return response
