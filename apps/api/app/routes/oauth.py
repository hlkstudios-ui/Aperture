import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlencode

import httpx
from authlib.jose import JsonWebKey, jwt
from fastapi import APIRouter, HTTPException, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.auth import DbSession, new_session_token, token_hash
from app.config import get_settings
from app.models import DeviceSession, OAuthIdentity, Profile, ProfilePreference, User
from app.oauth_broker import (
    OAuthAttempt,
    OAuthBrokerUnavailable,
    OAuthHandoff,
    consume_attempt,
    consume_handoff_for_origin,
    store_attempt,
    store_handoff,
)
from app.rate_limit import enforce_rate_limit
from app.remembered_accounts import remember_account
from app.site_domain_service import resolve_request_public_origin, validate_public_origin

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


def _signed_state(provider: str, return_origin: str) -> str:
    payload = _b64(
        json.dumps(
            {
                "provider": provider,
                "return_origin": return_origin,
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


def _validate_state(value: str, provider: str) -> dict[str, str | int]:
    try:
        payload, signature = value.split(".", 1)
        expected = _b64(
            hmac.new(settings.session_secret.encode(), payload.encode(), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        parsed = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
        if (
            parsed["provider"] != provider
            or parsed["exp"] < time.time()
            or not isinstance(parsed.get("return_origin"), str)
        ):
            raise ValueError
        return parsed
    except (ValueError, KeyError, json.JSONDecodeError) as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Invalid or expired sign-in request"
        ) from error


def _callback_url(provider: str) -> str:
    return (
        f"{str(settings.web_origin).rstrip('/')}/api/gateway/auth/oauth/"
        f"{provider}/callback"
    )


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
async def start(provider: str, request: Request, db: DbSession) -> RedirectResponse:
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
    return_origin = resolve_request_public_origin(db, request)
    state = _signed_state(provider, return_origin)
    verifier = secrets.token_urlsafe(64)
    challenge = _b64(hashlib.sha256(verifier.encode()).digest())
    try:
        await store_attempt(
            state,
            OAuthAttempt(
                provider=provider,
                verifier=verifier,
                return_origin=return_origin,
            ),
        )
    except OAuthBrokerUnavailable as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Social sign-in is temporarily unavailable",
        ) from error
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
    return RedirectResponse(f"{config.authorize_url}?{urlencode(query)}", status_code=302)


@router.get("/handoff")
async def handoff(
    request: Request,
    db: DbSession,
    code: str = Query(min_length=32, max_length=256),
) -> RedirectResponse:
    """Redeem a one-time broker code on the verified storefront hostname."""
    public_origin = resolve_request_public_origin(db, request)
    try:
        payload = await consume_handoff_for_origin(code, public_origin)
    except OAuthBrokerUnavailable as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Social sign-in is temporarily unavailable",
        ) from error
    if payload is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign-in handoff is invalid or expired")
    try:
        session_id = uuid.UUID(payload.session_id)
    except ValueError as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Sign-in handoff is invalid or expired"
        ) from error
    session = db.scalar(
        select(DeviceSession).where(
            DeviceSession.id == session_id,
            DeviceSession.token_hash == token_hash(payload.session_token),
            DeviceSession.revoked_at.is_(None),
            DeviceSession.expires_at > datetime.now(UTC),
        )
    )
    if session is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Sign-in handoff is invalid or expired")

    response = RedirectResponse(f"{public_origin}/profiles", status_code=303)
    response.set_cookie(
        settings.customer_session_cookie,
        payload.session_token,
        max_age=settings.customer_session_days * 86400,
        httponly=True,
        secure=settings.app_env not in {"development", "test"},
        samesite="lax",
        path="/",
        domain=settings.session_cookie_domain,
    )
    remember_account(
        request,
        response,
        payload.email,
        provider=payload.provider,
        label=payload.label,
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


async def callback(provider: str, request: Request, db: DbSession) -> Response:
    config = providers().get(provider)
    if config is None or not _configured(config):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Identity provider is unavailable")
    params = await _callback_params(request)
    state, code = params.get("state", ""), params.get("code", "")
    state_payload = _validate_state(state, provider)
    try:
        attempt = await consume_attempt(state)
    except OAuthBrokerUnavailable as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Social sign-in is temporarily unavailable",
        ) from error
    if (
        attempt is None
        or attempt.provider != provider
        or not hmac.compare_digest(
            attempt.return_origin, str(state_payload["return_origin"])
        )
    ):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired sign-in request")
    try:
        return_origin = validate_public_origin(db, attempt.return_origin)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "The sign-in storefront is no longer available"
        ) from error
    if params.get("error"):
        return RedirectResponse(
            f"{return_origin}/login?oauth_error=cancelled", status_code=303
        )
    if not code:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Incomplete sign-in response")
    email, subject, display_name = await _identity(
        config, provider, code, attempt.verifier
    )
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
    session = DeviceSession(
        user=user,
        active_profile_id=active_profile_id,
        token_hash=hashed_token,
        user_agent=request.headers.get("user-agent"),
        ip_address=request.client.host if request.client else None,
        expires_at=datetime.now(UTC) + timedelta(days=settings.customer_session_days),
    )
    db.add(session)
    db.commit()
    handoff_code = secrets.token_urlsafe(48)
    try:
        await store_handoff(
            handoff_code,
            OAuthHandoff(
                session_id=str(session.id),
                session_token=raw_token,
                return_origin=return_origin,
                email=email,
                provider=provider,
                label=display_name,
            ),
        )
    except OAuthBrokerUnavailable as error:
        session.revoked_at = datetime.now(UTC)
        db.commit()
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "Social sign-in is temporarily unavailable",
        ) from error
    query = urlencode({"code": handoff_code})
    return RedirectResponse(
        f"{return_origin}/api/gateway/auth/oauth/handoff?{query}", status_code=303
    )


router.add_api_route(
    "/{provider}/callback",
    callback,
    methods=["GET"],
    operation_id="oauth_callback_get",
)
router.add_api_route(
    "/{provider}/callback",
    callback,
    methods=["POST"],
    operation_id="oauth_callback_post",
)
