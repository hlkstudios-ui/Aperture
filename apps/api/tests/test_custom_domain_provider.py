import json

import httpx
import pytest

from app.custom_domain_provider import (
    CloudflareCustomHostnamesClient,
    DomainProviderError,
    DomainProviderNotFound,
)

ZONE_ID = "a" * 32
ACCOUNT_ID = "b" * 32
NAMESPACE_ID = "c" * 32
API_TOKEN = "provider-secret-token-that-must-stay-private"


def _client(transport: httpx.BaseTransport) -> CloudflareCustomHostnamesClient:
    return CloudflareCustomHostnamesClient(
        api_token=API_TOKEN,
        zone_id=ZONE_ID,
        account_id=ACCOUNT_ID,
        kv_namespace_id=NAMESPACE_ID,
        timeout_seconds=4,
        transport=transport,
    )


def test_cloudflare_custom_hostname_and_prefixed_kv_contract() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {API_TOKEN}"
        if request.method == "POST":
            assert json.loads(request.content) == {
                "hostname": "watch.customer.com",
                "ssl": {"method": "txt", "type": "dv"},
            }
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "id": "d" * 32,
                        "hostname": "watch.customer.com",
                        "status": "pending",
                        "ownership_verification": {
                            "type": "txt",
                            "name": "_cf-custom-hostname.watch.customer.com",
                            "value": "ownership-value",
                        },
                        "ssl": {
                            "status": "pending_validation",
                            "validation_records": [
                                {
                                    "txt_name": "_acme-challenge.watch.customer.com",
                                    "txt_value": "tls-value",
                                }
                            ],
                        },
                    },
                },
            )
        return httpx.Response(200, json={"success": True, "result": {}})

    client = _client(httpx.MockTransport(handler))
    created = client.create_hostname("watch.customer.com")
    assert created.id == "d" * 32
    assert [record.purpose for record in created.dns_records] == ["ownership", "tls"]

    client.publish_domain_allowlist(
        "watch.customer.com",
        {
            "status": "active",
            "site_id": "1",
            "hostname": "watch.customer.com",
            "primary_hostname": "watch.customer.com",
            "revision": 4,
        },
    )
    client.delete_domain_allowlist("watch.customer.com")
    kv_requests = requests[1:]
    assert [request.method for request in kv_requests] == ["PUT", "DELETE"]
    assert all(
        request.url.raw_path.endswith(b"/values/hostname%3Awatch.customer.com")
        for request in kv_requests
    )
    assert API_TOKEN not in repr(client)


def test_cloudflare_errors_are_bounded_and_do_not_expose_secrets() -> None:
    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("upstream included a secret", request=request)

    client = _client(httpx.MockTransport(timeout))
    with pytest.raises(DomainProviderError) as captured:
        client.create_hostname("watch.customer.com")
    assert captured.value.code == "provider_timeout"
    assert API_TOKEN not in str(captured.value)
    assert "upstream included" not in str(captured.value)


def test_cloudflare_response_body_is_not_reflected_in_provider_errors() -> None:
    secret_body = "provider diagnostic that must not escape"

    def rejected(_: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text=secret_body)

    with pytest.raises(DomainProviderError) as captured:
        _client(httpx.MockTransport(rejected)).create_hostname("watch.customer.com")
    assert captured.value.code == "provider_rejected"
    assert secret_body not in str(captured.value)


def test_cloudflare_get_hostname_distinguishes_authoritative_not_found() -> None:
    transport = httpx.MockTransport(lambda _request: httpx.Response(404, json={}))
    with pytest.raises(DomainProviderNotFound) as captured:
        _client(transport).get_hostname("d" * 32)
    assert captured.value.code == "provider_hostname_not_found"


def test_turnstile_widget_domains_are_fetched_preserved_and_verified() -> None:
    turnstile_token = "turnstile-runtime-token-that-stays-private"
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        assert request.headers["authorization"] == f"Bearer {turnstile_token}"
        if request.method == "GET":
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "result": {
                        "domains": ["apertures.online", "preserved.example.com"]
                    },
                },
            )
        assert json.loads(request.content) == {
            "domains": [
                "apertures.online",
                "preserved.example.com",
                "watch.customer.com",
            ]
        }
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": json.loads(request.content),
            },
        )

    client = CloudflareCustomHostnamesClient(
        api_token=API_TOKEN,
        zone_id=ZONE_ID,
        account_id=ACCOUNT_ID,
        kv_namespace_id=NAMESPACE_ID,
        timeout_seconds=4,
        turnstile_api_token=turnstile_token,
        turnstile_site_key="0x4AAAA-widget-site-key",
        turnstile_hostname_limit=10,
        transport=httpx.MockTransport(handler),
    )
    updated = client.reconcile_turnstile_domains(
        required={"apertures.online", "watch.customer.com"}
    )
    assert updated == (
        "apertures.online",
        "preserved.example.com",
        "watch.customer.com",
    )
    assert [request.method for request in requests] == ["GET", "PUT"]


def test_turnstile_hostname_quota_fails_before_widget_update() -> None:
    methods: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        return httpx.Response(
            200,
            json={
                "success": True,
                "result": {"domains": ["apertures.online", "existing.customer.com"]},
            },
        )

    client = CloudflareCustomHostnamesClient(
        api_token=API_TOKEN,
        zone_id=ZONE_ID,
        account_id=ACCOUNT_ID,
        kv_namespace_id=NAMESPACE_ID,
        timeout_seconds=4,
        turnstile_api_token="turnstile-runtime-token-that-stays-private",
        turnstile_site_key="0x4AAAA-widget-site-key",
        turnstile_hostname_limit=2,
        transport=httpx.MockTransport(handler),
    )
    with pytest.raises(DomainProviderError) as captured:
        client.reconcile_turnstile_domains(required={"watch.customer.com"})
    assert captured.value.code == "turnstile_hostname_quota"
    assert methods == ["GET"]
