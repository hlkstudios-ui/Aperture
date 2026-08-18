from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

import app.auth as auth


def request(method: str, origin: str | None = None) -> Request:
    headers = [] if origin is None else [(b"origin", origin.encode())]
    return Request({"type": "http", "method": method, "headers": headers})


def settings(environment: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        app_env=environment,
        web_origin="https://aperture.example",
        api_origin="https://api.aperture.example",
    )


def test_production_mutations_require_a_trusted_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: settings())

    for origin in (None, "https://attacker.example"):
        with pytest.raises(HTTPException) as error:
            auth.require_trusted_origin(request("POST", origin))
        assert error.value.status_code == 403

    auth.require_trusted_origin(request("POST", "https://aperture.example/"))
    auth.require_trusted_origin(request("DELETE", "https://api.aperture.example"))
    auth.require_trusted_origin(request("GET"))


def test_development_allows_non_browser_mutations_without_an_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: settings("development"))
    auth.require_trusted_origin(request("POST"))
