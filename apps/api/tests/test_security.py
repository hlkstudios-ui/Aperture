from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import SecretStr
from starlette.requests import Request

import app.auth as auth
import app.site_domain_service as site_domain_service


class ScalarDb:
    def __init__(self, result=None) -> None:
        self.result = result

    def scalar(self, _query):
        return self.result


def request(
    method: str, origin: str | None = None, extra_headers: dict[str, str] | None = None
) -> Request:
    supplied = dict(extra_headers or {})
    if origin is not None:
        supplied["origin"] = origin
    headers = [(name.lower().encode(), value.encode()) for name, value in supplied.items()]
    return Request({"type": "http", "method": method, "headers": headers})


def settings(environment: str = "production") -> SimpleNamespace:
    return SimpleNamespace(
        app_env=environment,
        web_origin="https://aperture.example",
        api_origin="https://api.aperture.example",
        admin_web_origin="https://studio.aperture.example",
        custom_domain_edge_secret=SecretStr("e" * 32),
    )


def test_production_mutations_require_a_trusted_origin(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: settings())

    for origin in (None, "https://attacker.example"):
        with pytest.raises(HTTPException) as error:
            auth.require_trusted_origin(request("POST", origin), ScalarDb())
        assert error.value.status_code == 403

    auth.require_trusted_origin(request("POST", "https://aperture.example/"), ScalarDb())
    auth.require_trusted_origin(request("DELETE", "https://api.aperture.example"), ScalarDb())
    auth.require_trusted_origin(request("PATCH", "https://studio.aperture.example"), ScalarDb())
    auth.require_trusted_origin(request("GET"), ScalarDb())


def test_development_allows_non_browser_mutations_without_an_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth, "get_settings", lambda: settings("development"))
    auth.require_trusted_origin(request("POST"), ScalarDb())


def test_active_custom_origin_requires_valid_matching_edge_assertion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configured = settings()
    monkeypatch.setattr(auth, "get_settings", lambda: configured)
    monkeypatch.setattr(site_domain_service, "get_settings", lambda: configured)
    active = SimpleNamespace(hostname="watch.customer.com", status="active")
    headers = {
        "X-Aperture-Public-Origin": "https://watch.customer.com",
        "X-Aperture-Edge-Secret": "e" * 32,
    }
    auth.require_trusted_origin(
        request("POST", "https://watch.customer.com", headers), ScalarDb(active)
    )

    rejected = (
        (ScalarDb(active), {**headers, "X-Aperture-Edge-Secret": "wrong"}),
        (
            ScalarDb(active),
            {**headers, "X-Aperture-Public-Origin": "https://other.customer.com"},
        ),
        (ScalarDb(None), headers),
    )
    for db, supplied in rejected:
        with pytest.raises(HTTPException) as error:
            auth.require_trusted_origin(
                request("POST", "https://watch.customer.com", supplied), db
            )
        assert error.value.status_code == 403
