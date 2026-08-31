from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import quote

import httpx

from app.config import Settings

CLOUDFLARE_API_BASE = "https://api.cloudflare.com/client/v4"
CLOUDFLARE_IDENTIFIER = re.compile(r"^[0-9a-fA-F]{32}$")


class DomainProviderError(RuntimeError):
    """A deliberately opaque provider failure safe to retain or return to an owner."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Custom domain provider request failed")


class DomainProviderNotFound(DomainProviderError):
    pass


@dataclass(frozen=True, slots=True)
class DomainDnsRecord:
    type: Literal["CNAME", "TXT", "HTTP"]
    name: str
    value: str
    purpose: Literal["routing", "ownership", "tls"]

    def as_dict(self) -> dict[str, str]:
        return {
            "type": self.type,
            "name": self.name,
            "value": self.value,
            "purpose": self.purpose,
        }


@dataclass(frozen=True, slots=True)
class ProviderHostname:
    id: str
    hostname: str
    hostname_status: str
    ssl_status: str
    dns_records: tuple[DomainDnsRecord, ...]


class CloudflareCustomHostnamesClient:
    """Small registrar-neutral boundary around Cloudflare for SaaS and Workers KV."""

    def __init__(
        self,
        *,
        api_token: str,
        zone_id: str,
        account_id: str,
        kv_namespace_id: str,
        timeout_seconds: float,
        turnstile_api_token: str | None = None,
        turnstile_site_key: str | None = None,
        turnstile_hostname_limit: int = 10,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        identifiers = (zone_id, account_id, kv_namespace_id)
        if not api_token or not all(
            CLOUDFLARE_IDENTIFIER.fullmatch(value) for value in identifiers
        ):
            raise ValueError("Cloudflare custom-domain configuration is incomplete")
        if not 2 <= timeout_seconds <= 15:
            raise ValueError("Cloudflare request timeout is outside the safe range")
        if not 1 <= turnstile_hostname_limit <= 200:
            raise ValueError("Turnstile hostname limit is outside the safe range")
        if turnstile_site_key is not None and not re.fullmatch(
            r"[A-Za-z0-9_-]{10,32}", turnstile_site_key
        ):
            raise ValueError("Turnstile site key is invalid")
        self._api_token = api_token
        self._zone_id = zone_id
        self._account_id = account_id
        self._kv_namespace_id = kv_namespace_id
        self._timeout_seconds = timeout_seconds
        self._turnstile_api_token = turnstile_api_token
        self._turnstile_site_key = turnstile_site_key
        self._turnstile_hostname_limit = turnstile_hostname_limit
        self._transport = transport

    def __repr__(self) -> str:
        return "CloudflareCustomHostnamesClient(api_token=<redacted>)"

    @classmethod
    def from_settings(cls, settings: Settings) -> CloudflareCustomHostnamesClient:
        if (
            not settings.custom_domains_available
            or settings.cloudflare_custom_hostnames_api_token is None
        ):
            raise ValueError("Custom domains are not configured")
        return cls(
            api_token=settings.cloudflare_custom_hostnames_api_token.get_secret_value(),
            zone_id=settings.cloudflare_zone_id or "",
            account_id=settings.cloudflare_account_id or "",
            kv_namespace_id=settings.cloudflare_site_domains_kv_namespace_id or "",
            timeout_seconds=settings.cloudflare_api_timeout_seconds,
            turnstile_api_token=(
                settings.cloudflare_turnstile_api_token.get_secret_value()
                if settings.cloudflare_turnstile_api_token is not None
                else None
            ),
            turnstile_site_key=settings.turnstile_site_key,
            turnstile_hostname_limit=settings.turnstile_hostname_limit,
        )

    def create_hostname(self, hostname: str) -> ProviderHostname:
        result = self._request_json(
            "POST",
            f"/zones/{self._zone_id}/custom_hostnames",
            json_body={
                "hostname": hostname,
                "ssl": {"method": "txt", "type": "dv"},
            },
        )
        return self._parse_hostname(result)

    def get_hostname(self, provider_hostname_id: str) -> ProviderHostname:
        self._validate_provider_hostname_id(provider_hostname_id)
        result = self._request_json(
            "GET",
            f"/zones/{self._zone_id}/custom_hostnames/{provider_hostname_id}",
            raise_not_found=True,
        )
        return self._parse_hostname(result)

    def delete_hostname(self, provider_hostname_id: str) -> None:
        self._validate_provider_hostname_id(provider_hostname_id)
        self._request_json(
            "DELETE",
            f"/zones/{self._zone_id}/custom_hostnames/{provider_hostname_id}",
            allow_not_found=True,
        )

    def publish_domain_allowlist(self, hostname: str, payload: dict[str, Any]) -> None:
        key = quote(f"hostname:{hostname}", safe="")
        self._request_json(
            "PUT",
            f"/accounts/{self._account_id}/storage/kv/namespaces/"
            f"{self._kv_namespace_id}/values/{key}",
            content=json.dumps(payload, sort_keys=True, separators=(",", ":")).encode(),
            content_type="application/json",
        )

    def delete_domain_allowlist(self, hostname: str) -> None:
        key = quote(f"hostname:{hostname}", safe="")
        self._request_json(
            "DELETE",
            f"/accounts/{self._account_id}/storage/kv/namespaces/"
            f"{self._kv_namespace_id}/values/{key}",
            allow_not_found=True,
        )

    def reconcile_turnstile_domains(
        self,
        *,
        required: set[str],
        remove: set[str] | None = None,
    ) -> tuple[str, ...]:
        if not self._turnstile_api_token or not self._turnstile_site_key:
            raise DomainProviderError("turnstile_unavailable")
        current = self._turnstile_domains(
            self._request_json(
                "GET",
                f"/accounts/{self._account_id}/challenges/widgets/"
                f"{self._turnstile_site_key}",
                api_token=self._turnstile_api_token,
            )
        )
        desired = set(current)
        desired.difference_update(remove or set())
        desired.update(required)
        if len(desired) > self._turnstile_hostname_limit:
            raise DomainProviderError("turnstile_hostname_quota")
        ordered = tuple(sorted(desired))
        if ordered == current:
            return current
        updated = self._turnstile_domains(
            self._request_json(
                "PUT",
                f"/accounts/{self._account_id}/challenges/widgets/"
                f"{self._turnstile_site_key}",
                json_body={"domains": list(ordered)},
                api_token=self._turnstile_api_token,
            )
        )
        if set(updated) != set(ordered):
            raise DomainProviderError("provider_malformed_response")
        return updated

    @staticmethod
    def _validate_provider_hostname_id(value: str) -> None:
        if not re.fullmatch(r"^[A-Za-z0-9_-]{1,64}$", value):
            raise DomainProviderError("provider_identifier_invalid")

    def _client(self, api_token: str | None = None) -> httpx.Client:
        timeout = httpx.Timeout(
            self._timeout_seconds,
            connect=min(self._timeout_seconds, 5.0),
            read=self._timeout_seconds,
            write=self._timeout_seconds,
            pool=min(self._timeout_seconds, 5.0),
        )
        return httpx.Client(
            base_url=CLOUDFLARE_API_BASE,
            headers={
                "Authorization": f"Bearer {api_token or self._api_token}",
                "Accept": "application/json",
                "User-Agent": "Aperture-Custom-Domains/1.0",
            },
            timeout=timeout,
            follow_redirects=False,
            transport=self._transport,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        content: bytes | None = None,
        content_type: str | None = None,
        allow_not_found: bool = False,
        raise_not_found: bool = False,
        api_token: str | None = None,
    ) -> Any:
        headers = {"Content-Type": content_type} if content_type else None
        try:
            with self._client(api_token) as client:
                response = client.request(
                    method,
                    path,
                    json=json_body,
                    content=content,
                    headers=headers,
                )
        except httpx.TimeoutException as error:
            raise DomainProviderError("provider_timeout") from error
        except httpx.HTTPError as error:
            raise DomainProviderError("provider_unavailable") from error

        if response.status_code == 404:
            if allow_not_found:
                return None
            if raise_not_found:
                raise DomainProviderNotFound("provider_hostname_not_found")
        if response.status_code == 401 or response.status_code == 403:
            raise DomainProviderError("provider_unauthorized")
        if response.status_code == 429:
            raise DomainProviderError("provider_rate_limited")
        if response.status_code < 200 or response.status_code >= 300:
            code = "provider_rejected" if response.status_code < 500 else "provider_unavailable"
            raise DomainProviderError(code)
        try:
            envelope = response.json()
        except (ValueError, UnicodeError) as error:
            raise DomainProviderError("provider_malformed_response") from error
        if not isinstance(envelope, dict) or envelope.get("success") is not True:
            raise DomainProviderError("provider_rejected")
        return envelope.get("result")

    @staticmethod
    def _turnstile_domains(value: Any) -> tuple[str, ...]:
        if not isinstance(value, dict) or not isinstance(value.get("domains"), list):
            raise DomainProviderError("provider_malformed_response")
        domains: set[str] = set()
        for raw_domain in value["domains"]:
            if not isinstance(raw_domain, str):
                raise DomainProviderError("provider_malformed_response")
            domain = raw_domain.strip().lower().rstrip(".")
            if (
                not domain
                or len(domain) > 253
                or not re.fullmatch(r"[a-z0-9.-]+", domain)
            ):
                raise DomainProviderError("provider_malformed_response")
            domains.add(domain)
        return tuple(sorted(domains))

    @classmethod
    def _parse_hostname(cls, value: Any) -> ProviderHostname:
        if not isinstance(value, dict):
            raise DomainProviderError("provider_malformed_response")
        provider_id = value.get("id")
        hostname = value.get("hostname")
        hostname_status = value.get("status")
        ssl = value.get("ssl")
        if not all(isinstance(item, str) and item for item in (provider_id, hostname)):
            raise DomainProviderError("provider_malformed_response")
        if not isinstance(hostname_status, str) or not isinstance(ssl, dict):
            raise DomainProviderError("provider_malformed_response")
        ssl_status = ssl.get("status")
        if not isinstance(ssl_status, str):
            ssl_status = "initializing"

        records: list[DomainDnsRecord] = []
        ownership = value.get("ownership_verification")
        record = cls._parse_dns_record(ownership, "ownership")
        if record is not None:
            records.append(record)
        validation_records = ssl.get("validation_records")
        if isinstance(validation_records, list):
            for raw_record in validation_records:
                record = cls._parse_dns_record(raw_record, "tls")
                if record is not None and record not in records:
                    records.append(record)
        return ProviderHostname(
            id=provider_id,
            hostname=hostname.lower().rstrip("."),
            hostname_status=hostname_status.lower(),
            ssl_status=ssl_status.lower(),
            dns_records=tuple(records),
        )

    @staticmethod
    def _parse_dns_record(
        value: Any, purpose: Literal["ownership", "tls"]
    ) -> DomainDnsRecord | None:
        if not isinstance(value, dict):
            return None
        record_type = str(value.get("type", "")).upper()
        name = value.get("name")
        record_value = value.get("value")
        if isinstance(value.get("txt_name"), str) and isinstance(value.get("txt_value"), str):
            record_type, name, record_value = "TXT", value["txt_name"], value["txt_value"]
        elif isinstance(value.get("cname_name"), str) and isinstance(
            value.get("cname_target"), str
        ):
            record_type, name, record_value = (
                "CNAME",
                value["cname_name"],
                value["cname_target"],
            )
        elif isinstance(value.get("http_url"), str) and isinstance(
            value.get("http_body"), str
        ):
            record_type, name, record_value = "HTTP", value["http_url"], value["http_body"]
        if record_type not in {"CNAME", "TXT", "HTTP"}:
            return None
        if not isinstance(name, str) or not isinstance(record_value, str):
            return None
        if not name or not record_value or len(name) > 2048 or len(record_value) > 4096:
            return None
        return DomainDnsRecord(
            type=record_type,
            name=name,
            value=record_value,
            purpose=purpose,
        )
