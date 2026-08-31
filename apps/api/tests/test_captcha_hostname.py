import asyncio
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app import captcha


class VerificationResponse:
    def __init__(self, hostname: str) -> None:
        self.hostname = hostname

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return {"success": True, "hostname": self.hostname}


class VerificationClient:
    def __init__(self, hostname: str) -> None:
        self.hostname = hostname

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args) -> None:
        return None

    async def post(self, *_args, **_kwargs) -> VerificationResponse:
        return VerificationResponse(self.hostname)


def request_for(origin: str) -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/auth/login",
            "headers": [(b"x-aperture-public-origin", origin.encode())],
            "client": ("203.0.113.20", 443),
        }
    )


def test_turnstile_hostname_must_match_the_verified_storefront(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        captcha,
        "get_settings",
        lambda: SimpleNamespace(
            captcha_required=True,
            app_env="production",
            captcha_test_mode=False,
            turnstile_secret_key="turnstile-secret",
        ),
    )
    monkeypatch.setattr(
        captcha.httpx,
        "AsyncClient",
        lambda **_kwargs: VerificationClient("watch.customer.example"),
    )
    asyncio.run(captcha.verify_captcha("valid-token", request_for("https://watch.customer.example")))

    monkeypatch.setattr(
        captcha.httpx,
        "AsyncClient",
        lambda **_kwargs: VerificationClient("different.customer.example"),
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(
            captcha.verify_captcha(
                "valid-token", request_for("https://watch.customer.example")
            )
        )
    assert error.value.status_code == 400
    assert "different storefront" in error.value.detail
