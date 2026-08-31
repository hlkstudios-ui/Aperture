from types import SimpleNamespace

import pytest
from pydantic import SecretStr, ValidationError
from starlette.requests import Request

from app.config import Settings
from app.models import SiteDomainStatus
from app.site_domain_service import (
    is_allowed_public_origin,
    normalize_hostname,
    preferred_public_origin,
    resolve_request_public_origin,
    validate_custom_hostname,
)


def _settings(**overrides) -> Settings:
    values = {
        "_env_file": None,
        "app_env": "development",
        "web_origin": "https://apertures.online",
        "api_origin": "https://api.apertures.online",
        "movie_metadata_mode": "legacy",
        "brand_ai_provider": "disabled",
        "media_delivery_mode": "api_proxy",
        "private_studio_required": False,
    }
    values.update(overrides)
    return Settings(**values)


class _ScalarDb:
    def __init__(self, result=None) -> None:
        self.result = result

    def scalar(self, _query):
        return self.result


def _request(method: str, headers: dict[str, str]) -> Request:
    return Request(
        {
            "type": "http",
            "method": method,
            "path": "/account",
            "headers": [(name.lower().encode(), value.encode()) for name, value in headers.items()],
        }
    )


def test_hostname_normalization_is_strict_and_idna_stable() -> None:
    assert normalize_hostname(" Café.Customer.COM ") == "xn--caf-dma.customer.com"
    assert normalize_hostname("faß.de") == "xn--fa-hia.de"
    for value in (
        "https://customer.com",
        "*.customer.com",
        "customer.com.",
        "127.0.0.1",
        "customer.test",
        "single-label",
    ):
        with pytest.raises(ValueError):
            normalize_hostname(value)


def test_platform_and_service_hostnames_cannot_be_claimed() -> None:
    settings = _settings(custom_domain_cname_target="customers.apertures.online")
    for value in (
        "apertures.online",
        "tenant.apertures.online",
        "api.apertures.online",
        "customers.apertures.online",
    ):
        with pytest.raises(ValueError):
            validate_custom_hostname(value, settings)
    assert validate_custom_hostname("watch.customer.com", settings) == "watch.customer.com"


def test_custom_domain_feature_gate_fails_closed_until_every_edge_setting_exists() -> None:
    incomplete = _settings(custom_domains_enabled=True, custom_domain_provider="cloudflare")
    assert not incomplete.custom_domains_available
    configured = _settings(
        custom_domains_enabled=True,
        custom_domain_infrastructure_ready=True,
        custom_domain_provider="cloudflare",
        custom_domain_cname_target="customers.apertures.online",
        custom_domain_edge_secret=SecretStr("e" * 32),
        cloudflare_custom_hostnames_api_token=SecretStr("t" * 40),
        cloudflare_zone_id="a" * 32,
        cloudflare_account_id="b" * 32,
        cloudflare_site_domains_kv_namespace_id="c" * 32,
    )
    assert configured.custom_domains_available
    configured.custom_domain_infrastructure_ready = False
    assert not configured.custom_domains_available
    configured.custom_domain_infrastructure_ready = True
    configured.captcha_required = True
    assert not configured.custom_domains_available
    configured.cloudflare_turnstile_api_token = SecretStr("u" * 40)
    configured.turnstile_site_key = "0x4AAAA-widget-site-key"
    assert configured.custom_domains_available


def test_custom_domains_reject_shared_customer_cookie_scope() -> None:
    with pytest.raises(ValidationError, match="host-only"):
        _settings(
            custom_domains_enabled=True,
            session_cookie_domain=".apertures.online",
        )


def test_custom_domains_reserve_turnstile_capacity_for_the_platform_hostname() -> None:
    with pytest.raises(ValidationError, match="reserve one Turnstile hostname slot"):
        _settings(
            custom_domains_enabled=True,
            captcha_required=True,
            custom_domain_max_per_site=10,
            turnstile_hostname_limit=10,
        )

    configured = _settings(
        custom_domains_enabled=True,
        captcha_required=True,
        custom_domain_max_per_site=9,
        turnstile_hostname_limit=10,
    )
    assert configured.custom_domain_max_per_site == 9


def test_public_origin_helpers_keep_platform_fallback_and_require_active_custom_domain(
    monkeypatch,
) -> None:
    settings = _settings(custom_domain_edge_secret=SecretStr("e" * 32))
    monkeypatch.setattr("app.site_domain_service.get_settings", lambda: settings)
    active = SimpleNamespace(
        hostname="watch.customer.com",
        status=SiteDomainStatus.active,
        is_primary=True,
    )
    db = _ScalarDb(active)
    assert is_allowed_public_origin(db, "https://apertures.online")
    assert is_allowed_public_origin(db, "https://watch.customer.com")
    assert preferred_public_origin(db) == "https://watch.customer.com"
    assert (
        resolve_request_public_origin(
            db,
            _request(
                "POST",
                {
                    "Origin": "https://watch.customer.com",
                    "X-Aperture-Public-Origin": "https://watch.customer.com",
                    "X-Aperture-Edge-Secret": "e" * 32,
                },
            ),
        )
        == "https://watch.customer.com"
    )

    no_domain = _ScalarDb(None)
    assert preferred_public_origin(no_domain) == "https://apertures.online"
    assert not is_allowed_public_origin(no_domain, "https://watch.customer.com")
    assert is_allowed_public_origin(no_domain, "https://apertures.online")
