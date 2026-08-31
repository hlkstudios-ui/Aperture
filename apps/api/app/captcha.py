from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException, Request, status

from app.config import get_settings

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


async def verify_captcha(token: str | None, request: Request) -> None:
    """Fail closed when CAPTCHA is enabled; only development may use the explicit bypass."""
    settings = get_settings()
    if not settings.captcha_required:
        return
    if (
        settings.app_env in {"development", "test"}
        and request.client
        and request.client.host == "testclient"
    ):
        return
    if settings.app_env in {"development", "test"} and settings.captcha_test_mode:
        if token == "local-captcha-pass":
            return
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete the security check")
    if not token or not settings.turnstile_secret_key:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Complete the security check")
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            response = await client.post(
                VERIFY_URL,
                data={
                    "secret": settings.turnstile_secret_key,
                    "response": token,
                    "remoteip": request.client.host if request.client else "",
                },
            )
            response.raise_for_status()
            result = response.json()
    except (httpx.HTTPError, ValueError) as error:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Security verification is temporarily unavailable"
        ) from error
    if not result.get("success"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Security verification failed; try again")
    expected_origin = request.headers.get("x-aperture-public-origin") or request.headers.get(
        "origin"
    )
    expected_hostname = urlsplit(expected_origin).hostname if expected_origin else None
    verified_hostname = str(result.get("hostname") or "").rstrip(".").lower()
    if not expected_hostname or verified_hostname != expected_hostname.rstrip(".").lower():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Security verification was issued for a different storefront",
        )
