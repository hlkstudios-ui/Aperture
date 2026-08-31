import asyncio
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.oauth_broker import OAuthHandoff
from app.routes import oauth


def test_oauth_provider_callback_stays_on_the_stable_storefront_gateway(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        oauth,
        "settings",
        SimpleNamespace(web_origin="https://cinema.example", app_env="development"),
    )

    assert oauth._callback_url("google") == (
        "https://cinema.example/api/gateway/auth/oauth/google/callback"
    )


def test_apple_form_post_start_stores_pkce_server_side_for_custom_domain_handoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider = oauth.Provider(
        label="Apple",
        authorize_url="https://appleid.apple.com/auth/authorize",
        token_url="https://appleid.apple.com/auth/token",
        scopes="openid email name",
        client_id="apple-client",
        client_secret="apple-secret",
    )

    async def allow_rate_limit(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(
        oauth,
        "settings",
        SimpleNamespace(web_origin="https://cinema.example", app_env="production"),
    )
    monkeypatch.setattr(oauth, "providers", lambda: {"apple": provider})
    captured = {}

    async def store(state, attempt) -> None:
        captured["state"] = state
        captured["attempt"] = attempt

    monkeypatch.setattr(
        oauth, "_signed_state", lambda _provider, _origin: "signed-state"
    )
    monkeypatch.setattr(oauth, "enforce_rate_limit", allow_rate_limit)
    monkeypatch.setattr(oauth, "store_attempt", store)
    monkeypatch.setattr(
        oauth,
        "resolve_request_public_origin",
        lambda _db, _request: "https://watch.customer.example",
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/gateway/auth/oauth/apple/start",
            "headers": [],
            "client": ("203.0.113.10", 443),
        }
    )

    response = asyncio.run(oauth.start("apple", request, SimpleNamespace()))

    query = parse_qs(urlsplit(response.headers["location"]).query)
    assert query["response_mode"] == ["form_post"]
    assert query["redirect_uri"] == [
        "https://cinema.example/api/gateway/auth/oauth/apple/callback"
    ]
    assert response.headers.get("set-cookie") is None
    assert captured["state"] == "signed-state"
    assert captured["attempt"].provider == "apple"
    assert captured["attempt"].return_origin == "https://watch.customer.example"
    assert len(captured["attempt"].verifier) >= 64


def test_handoff_sets_a_host_only_cookie_only_on_its_bound_custom_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = OAuthHandoff(
        session_id="11111111-1111-1111-1111-111111111111",
        session_token="one-time-session-token",
        return_origin="https://watch.customer.example",
        email="viewer@example.test",
        provider="google",
        label="Viewer",
    )

    async def consume(_code: str, origin: str) -> OAuthHandoff | None:
        return payload if origin == payload.return_origin else None

    remembered = {}
    monkeypatch.setattr(oauth, "consume_handoff_for_origin", consume)
    monkeypatch.setattr(
        oauth,
        "resolve_request_public_origin",
        lambda _db, _request: "https://watch.customer.example",
    )
    monkeypatch.setattr(
        oauth,
        "remember_account",
        lambda _request, _response, email, **kwargs: remembered.update(
            email=email, **kwargs
        ),
    )
    monkeypatch.setattr(
        oauth,
        "settings",
        SimpleNamespace(
            customer_session_cookie="aperture_session",
            customer_session_days=30,
            app_env="production",
            session_cookie_domain=None,
        ),
    )
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/api/gateway/auth/oauth/handoff",
            "headers": [],
        }
    )
    db = SimpleNamespace(scalar=lambda _statement: SimpleNamespace())

    response = asyncio.run(oauth.handoff(request, db, code="c" * 48))

    assert response.headers["location"] == "https://watch.customer.example/profiles"
    cookie = response.headers["set-cookie"]
    assert "aperture_session=one-time-session-token" in cookie
    assert "Domain=" not in cookie
    assert remembered == {
        "email": "viewer@example.test",
        "provider": "google",
        "label": "Viewer",
    }

    monkeypatch.setattr(
        oauth,
        "resolve_request_public_origin",
        lambda _db, _request: "https://other.customer.example",
    )
    with pytest.raises(HTTPException) as error:
        asyncio.run(oauth.handoff(request, db, code="d" * 48))
    assert error.value.status_code == 400
