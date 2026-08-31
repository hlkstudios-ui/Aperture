"""Read-only, secret-free Cloudflare-for-SaaS infrastructure preflight."""

from __future__ import annotations

import argparse
import json
import re
import socket
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from validate_config import DEFAULT_INPUT, load


API_BASE = "https://api.cloudflare.com/client/v4"
MAX_RESPONSE_BYTES = 1024 * 1024
CHECK_NAMES = (
    "cdn_custom_domain_mapping",
    "cdn_custom_domains_enabled",
    "cdn_route_excluded",
    "cdn_site_domains_binding",
    "cname_target_proxied",
    "fallback_origin_active",
    "geo_custom_domains_enabled",
    "geo_required_secrets",
    "geo_site_domains_binding",
    "origin_route_excluded",
    "runtime_custom_hostnames_readable",
    "runtime_site_domains_kv_readable",
    "storage_route_excluded",
    "turnstile_hostname_capacity",
    "turnstile_widget_canonical_host",
    "wildcard_geo_route",
)
REQUIRED_GEO_SECRETS = frozenset(
    {
        "CUSTOM_DOMAIN_EDGE_SECRET",
        "GEO_ASSERTION_SECRET",
        "ORIGIN_EDGE_SECRET",
    }
)
IDENTIFIER = re.compile(r"^[0-9a-fA-F]{32}$")
SCRIPT_NAME = re.compile(r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$")


class ConfigurationError(ValueError):
    """The local preflight inputs are incomplete or unsafe."""


class CloudflareApiError(RuntimeError):
    """A stable Cloudflare read failure that never carries provider response text."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__("Cloudflare read failed")


def normalize_hostname(value: str) -> str:
    if not isinstance(value, str):
        raise ConfigurationError("hostname_invalid")
    raw = value.strip().rstrip(".")
    try:
        hostname = raw.encode("idna").decode("ascii").lower()
    except UnicodeError as error:
        raise ConfigurationError("hostname_invalid") from error
    labels = hostname.split(".")
    if (
        not hostname
        or len(hostname) > 253
        or len(labels) < 2
        or any(
            not re.fullmatch(
                r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label
            )
            for label in labels
        )
    ):
        raise ConfigurationError("hostname_invalid")
    return hostname


def validate_preflight_values(values: dict[str, str]) -> dict[str, Any]:
    required = (
        "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
        "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN",
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
        "CUSTOM_DOMAIN_CNAME_TARGET",
        "CUSTOM_DOMAIN_FALLBACK_ORIGIN",
        "CUSTOM_DOMAIN_MAX_PER_SITE",
        "ORIGIN_HOSTNAME",
        "STORAGE_HOSTNAME",
        "CDN_HOSTNAME",
        "WEB_HOSTNAME",
        "CAPTCHA_REQUIRED",
        "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME",
        "CLOUDFLARE_CDN_SCRIPT_NAME",
        "CLOUDFLARE_API_TIMEOUT_SECONDS",
    )
    if any(not values.get(label, "").strip() for label in required):
        raise ConfigurationError("configuration_incomplete")

    topology_token = values["CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN"].strip()
    runtime_token = values["CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN"].strip()
    for token in (topology_token, runtime_token):
        if (
            len(token) < 20
            or any(character.isspace() for character in token)
            or "DUMMY" in token.upper()
        ):
            raise ConfigurationError("control_token_invalid")
    dns_token = values.get("CLOUDFLARE_API_TOKEN", "").strip()
    if (
        topology_token == runtime_token
        or (dns_token and dns_token in {topology_token, runtime_token})
    ):
        raise ConfigurationError("credential_separation_invalid")

    if values["CAPTCHA_REQUIRED"] not in {"true", "false"}:
        raise ConfigurationError("captcha_configuration_invalid")
    captcha_required = values["CAPTCHA_REQUIRED"] == "true"
    turnstile_token = ""
    turnstile_site_key = ""
    turnstile_hostname_limit = 0
    if captcha_required:
        turnstile_required = (
            "CLOUDFLARE_TURNSTILE_API_TOKEN",
            "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
            "TURNSTILE_HOSTNAME_LIMIT",
        )
        if any(not values.get(label, "").strip() for label in turnstile_required):
            raise ConfigurationError("turnstile_configuration_incomplete")
        turnstile_token = values["CLOUDFLARE_TURNSTILE_API_TOKEN"].strip()
        turnstile_site_key = values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"].strip()
        if (
            len(turnstile_token) < 20
            or any(character.isspace() for character in turnstile_token)
            or "DUMMY" in turnstile_token.upper()
            or not 1 <= len(turnstile_site_key) <= 32
            or any(character.isspace() for character in turnstile_site_key)
            or "DUMMY" in turnstile_site_key.upper()
        ):
            raise ConfigurationError("turnstile_credential_invalid")
        if turnstile_token in {topology_token, runtime_token, dns_token}:
            raise ConfigurationError("credential_separation_invalid")
        try:
            turnstile_hostname_limit = int(values["TURNSTILE_HOSTNAME_LIMIT"])
            custom_domain_limit = int(values["CUSTOM_DOMAIN_MAX_PER_SITE"])
        except ValueError as error:
            raise ConfigurationError("turnstile_hostname_limit_invalid") from error
        if (
            not 2 <= turnstile_hostname_limit <= 10
            or not 1 <= custom_domain_limit <= turnstile_hostname_limit - 1
        ):
            raise ConfigurationError("turnstile_hostname_limit_invalid")

    for label in (
        "CLOUDFLARE_ZONE_ID",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
    ):
        if not IDENTIFIER.fullmatch(values[label]):
            raise ConfigurationError("cloudflare_identifier_invalid")

    cname_target = normalize_hostname(values["CUSTOM_DOMAIN_CNAME_TARGET"])
    fallback_origin = normalize_hostname(values["CUSTOM_DOMAIN_FALLBACK_ORIGIN"])
    origin_hostname = normalize_hostname(values["ORIGIN_HOSTNAME"])
    storage_hostname = normalize_hostname(values["STORAGE_HOSTNAME"])
    cdn_hostname = normalize_hostname(values["CDN_HOSTNAME"])
    web_hostname = normalize_hostname(values["WEB_HOSTNAME"])
    if (
        fallback_origin != origin_hostname
        or len(
            {
                cname_target,
                origin_hostname,
                storage_hostname,
                cdn_hostname,
                web_hostname,
            }
        )
        != 5
    ):
        raise ConfigurationError("fallback_origin_invalid")

    geo_script = values["CLOUDFLARE_GEO_EDGE_SCRIPT_NAME"]
    cdn_script = values["CLOUDFLARE_CDN_SCRIPT_NAME"]
    if (
        not SCRIPT_NAME.fullmatch(geo_script)
        or not SCRIPT_NAME.fullmatch(cdn_script)
        or geo_script == cdn_script
    ):
        raise ConfigurationError("worker_script_name_invalid")

    try:
        timeout = float(values["CLOUDFLARE_API_TIMEOUT_SECONDS"])
    except ValueError as error:
        raise ConfigurationError("timeout_invalid") from error
    if not 2 <= timeout <= 15:
        raise ConfigurationError("timeout_invalid")

    return {
        "topology_token": topology_token,
        "runtime_token": runtime_token,
        "turnstile_token": turnstile_token,
        "turnstile_site_key": turnstile_site_key,
        "turnstile_hostname_limit": turnstile_hostname_limit,
        "captcha_required": captcha_required,
        "zone_id": values["CLOUDFLARE_ZONE_ID"],
        "account_id": values["CLOUDFLARE_ACCOUNT_ID"],
        "namespace_id": values["CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID"],
        "cname_target": cname_target,
        "fallback_origin": fallback_origin,
        "origin_hostname": origin_hostname,
        "storage_hostname": storage_hostname,
        "cdn_hostname": cdn_hostname,
        "web_hostname": web_hostname,
        "geo_script": geo_script,
        "cdn_script": cdn_script,
        "timeout": timeout,
    }


class CloudflareReadClient:
    """Minimal GET-only client for the official Cloudflare v4 API."""

    def __init__(
        self,
        token: str,
        timeout: float,
        *,
        opener: Callable[..., Any] = urlopen,
    ) -> None:
        self._token = token
        self._timeout = timeout
        self._opener = opener

    def get(self, path: str, query: dict[str, str] | None = None) -> Any:
        url = f"{API_BASE}{path}"
        if query:
            url = f"{url}?{urlencode(query)}"
        request = Request(
            url,
            method="GET",
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "User-Agent": "Aperture-Cloudflare-SaaS-Preflight/1.0",
            },
        )
        try:
            with self._opener(request, timeout=self._timeout) as response:
                body = response.read(MAX_RESPONSE_BYTES + 1)
        except HTTPError as error:
            code = "cloudflare_api_unauthorized" if error.code in {401, 403} else "cloudflare_api_rejected"
            raise CloudflareApiError(code) from error
        except (URLError, TimeoutError, socket.timeout, OSError) as error:
            raise CloudflareApiError("cloudflare_api_unavailable") from error
        if len(body) > MAX_RESPONSE_BYTES:
            raise CloudflareApiError("cloudflare_api_malformed")
        try:
            envelope = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise CloudflareApiError("cloudflare_api_malformed") from error
        if (
            not isinstance(envelope, dict)
            or envelope.get("success") is not True
            or "result" not in envelope
        ):
            raise CloudflareApiError("cloudflare_api_rejected")
        return envelope["result"]


def _binding_matches(
    settings: Any, *, name: str, binding_type: str, field: str, value: str
) -> bool:
    if not isinstance(settings, dict) or not isinstance(settings.get("bindings"), list):
        return False
    matches = [
        binding
        for binding in settings["bindings"]
        if isinstance(binding, dict)
        and binding.get("name") == name
        and binding.get("type") == binding_type
    ]
    return len(matches) == 1 and matches[0].get(field) == value


def _geo_secrets_present(settings: Any) -> bool:
    if not isinstance(settings, dict) or not isinstance(settings.get("bindings"), list):
        return False
    secrets = {
        binding.get("name")
        for binding in settings["bindings"]
        if isinstance(binding, dict) and binding.get("type") == "secret_text"
    }
    return REQUIRED_GEO_SECRETS <= secrets


def _worker_route_matches(routes: Any, *, pattern: str, script: str | None) -> bool:
    if not isinstance(routes, list):
        return False
    matches = [
        route
        for route in routes
        if isinstance(route, dict) and route.get("pattern") == pattern
    ]
    return len(matches) == 1 and matches[0].get("script") == script


def _turnstile_widget_checks(
    widget: Any, configuration: dict[str, Any]
) -> tuple[bool, bool]:
    if not isinstance(widget, dict) or not isinstance(widget.get("domains"), list):
        return False, False
    domains = widget["domains"]
    normalized_values = [
        value.strip().rstrip(".").lower()
        for value in domains
        if isinstance(value, str) and value.strip()
    ]
    capacity_valid = (
        len(normalized_values) == len(domains)
        and len(set(normalized_values)) == len(normalized_values)
        and 1
        <= len(normalized_values)
        <= int(configuration["turnstile_hostname_limit"])
    )
    canonical_present = False
    for domain in domains:
        try:
            if normalize_hostname(domain) == configuration["web_hostname"]:
                canonical_present = True
                break
        except ConfigurationError:
            continue
    widget_matches = widget.get("sitekey") == configuration["turnstile_site_key"]
    return capacity_valid, widget_matches and canonical_present


def run_preflight(
    configuration: dict[str, Any],
    topology_client: CloudflareReadClient,
    runtime_client: CloudflareReadClient,
    turnstile_client: CloudflareReadClient | None = None,
) -> dict[str, Any]:
    zone_id = quote(str(configuration["zone_id"]), safe="")
    account_id = quote(str(configuration["account_id"]), safe="")
    geo_script = quote(str(configuration["geo_script"]), safe="")
    cdn_script = quote(str(configuration["cdn_script"]), safe="")

    fallback = topology_client.get(
        f"/zones/{zone_id}/custom_hostnames/fallback_origin"
    )
    dns_records = topology_client.get(
        f"/zones/{zone_id}/dns_records",
        {
            "match": "all",
            "name": str(configuration["cname_target"]),
            "per_page": "100",
            "type": "CNAME",
        },
    )
    routes = topology_client.get(f"/zones/{zone_id}/workers/routes")
    geo_settings = topology_client.get(
        f"/accounts/{account_id}/workers/scripts/{geo_script}/settings"
    )
    cdn_settings = topology_client.get(
        f"/accounts/{account_id}/workers/scripts/{cdn_script}/settings"
    )
    cdn_domains = topology_client.get(
        f"/accounts/{account_id}/workers/domains",
        {
            "hostname": str(configuration["cdn_hostname"]),
            "service": str(configuration["cdn_script"]),
            "zone_id": str(configuration["zone_id"]),
        },
    )
    runtime_custom_hostnames = runtime_client.get(
        f"/zones/{zone_id}/custom_hostnames",
        {"page": "1", "per_page": "5"},
    )
    runtime_kv_keys = runtime_client.get(
        f"/accounts/{account_id}/storage/kv/namespaces/"
        f"{quote(str(configuration['namespace_id']), safe='')}/keys",
        {"limit": "10"},
    )
    turnstile_hostname_capacity = True
    turnstile_widget_canonical_host = True
    if configuration["captcha_required"]:
        if turnstile_client is None:
            turnstile_hostname_capacity = False
            turnstile_widget_canonical_host = False
        else:
            turnstile_widget = turnstile_client.get(
                f"/accounts/{account_id}/challenges/widgets/"
                f"{quote(str(configuration['turnstile_site_key']), safe='')}"
            )
            (
                turnstile_hostname_capacity,
                turnstile_widget_canonical_host,
            ) = _turnstile_widget_checks(turnstile_widget, configuration)

    fallback_active = False
    if isinstance(fallback, dict) and fallback.get("status") == "active":
        try:
            fallback_active = (
                normalize_hostname(fallback.get("origin", ""))
                == configuration["fallback_origin"]
            )
        except ConfigurationError:
            fallback_active = False

    matching_dns: list[dict[str, Any]] = []
    if isinstance(dns_records, list):
        for record in dns_records:
            if not isinstance(record, dict):
                continue
            try:
                name_matches = (
                    normalize_hostname(record.get("name", ""))
                    == configuration["cname_target"]
                )
                content_matches = (
                    normalize_hostname(record.get("content", ""))
                    == configuration["fallback_origin"]
                )
            except ConfigurationError:
                continue
            if (
                record.get("type") == "CNAME"
                and record.get("proxied") is True
                and name_matches
                and content_matches
            ):
                matching_dns.append(record)

    matching_cdn_domains: list[dict[str, Any]] = []
    if isinstance(cdn_domains, list):
        for domain in cdn_domains:
            if not isinstance(domain, dict):
                continue
            try:
                hostname_matches = (
                    normalize_hostname(domain.get("hostname", ""))
                    == configuration["cdn_hostname"]
                )
            except ConfigurationError:
                continue
            if (
                hostname_matches
                and domain.get("service") == configuration["cdn_script"]
                and domain.get("zone_id") == configuration["zone_id"]
            ):
                matching_cdn_domains.append(domain)

    namespace_id = str(configuration["namespace_id"])
    checks = {
        "cdn_custom_domain_mapping": len(matching_cdn_domains) == 1,
        "cdn_custom_domains_enabled": _binding_matches(
            cdn_settings,
            name="CUSTOM_DOMAINS_ENABLED",
            binding_type="plain_text",
            field="text",
            value="true",
        ),
        "cdn_route_excluded": _worker_route_matches(
            routes,
            pattern=f"{configuration['cdn_hostname']}/*",
            script=None,
        ),
        "cdn_site_domains_binding": _binding_matches(
            cdn_settings,
            name="SITE_DOMAINS",
            binding_type="kv_namespace",
            field="namespace_id",
            value=namespace_id,
        ),
        "cname_target_proxied": len(matching_dns) == 1,
        "fallback_origin_active": fallback_active,
        "geo_custom_domains_enabled": _binding_matches(
            geo_settings,
            name="CUSTOM_DOMAINS_ENABLED",
            binding_type="plain_text",
            field="text",
            value="true",
        ),
        "geo_required_secrets": _geo_secrets_present(geo_settings),
        "geo_site_domains_binding": _binding_matches(
            geo_settings,
            name="SITE_DOMAINS",
            binding_type="kv_namespace",
            field="namespace_id",
            value=namespace_id,
        ),
        "origin_route_excluded": _worker_route_matches(
            routes,
            pattern=f"{configuration['origin_hostname']}/*",
            script=None,
        ),
        "runtime_custom_hostnames_readable": isinstance(
            runtime_custom_hostnames, list
        ),
        "runtime_site_domains_kv_readable": isinstance(runtime_kv_keys, list),
        "storage_route_excluded": _worker_route_matches(
            routes,
            pattern=f"{configuration['storage_hostname']}/*",
            script=None,
        ),
        "turnstile_hostname_capacity": turnstile_hostname_capacity,
        "turnstile_widget_canonical_host": turnstile_widget_canonical_host,
        "wildcard_geo_route": _worker_route_matches(
            routes, pattern="*/*", script=str(configuration["geo_script"])
        ),
    }
    ready = all(checks.values())
    payload: dict[str, Any] = {
        "checks": checks,
        "event": "cloudflare_saas.infrastructure_preflight",
        "ready": ready,
        "schema_version": 1,
    }
    if not ready:
        payload["error"] = "infrastructure_not_ready"
    return payload


def failure_payload(error: str) -> dict[str, Any]:
    return {
        "checks": {name: False for name in CHECK_NAMES},
        "error": error,
        "event": "cloudflare_saas.infrastructure_preflight",
        "ready": False,
        "schema_version": 1,
    }


def execute(
    values: dict[str, str],
    *,
    client_factory: Callable[[str, float], CloudflareReadClient] = CloudflareReadClient,
) -> tuple[int, dict[str, Any]]:
    try:
        configuration = validate_preflight_values(values)
        topology_client = client_factory(
            str(configuration["topology_token"]), float(configuration["timeout"])
        )
        runtime_client = client_factory(
            str(configuration["runtime_token"]), float(configuration["timeout"])
        )
        turnstile_client = None
        if configuration["captcha_required"]:
            turnstile_client = client_factory(
                str(configuration["turnstile_token"]),
                float(configuration["timeout"]),
            )
        result = run_preflight(
            configuration, topology_client, runtime_client, turnstile_client
        )
        return (0 if result["ready"] else 1), result
    except ConfigurationError as error:
        return 1, failure_payload(str(error))
    except CloudflareApiError as error:
        return 1, failure_payload(error.code)
    except Exception:
        return 1, failure_payload("internal_error")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args(argv)
    try:
        values = load(args.input)
    except (OSError, ValueError):
        status_code, payload = 1, failure_payload("configuration_invalid")
    else:
        status_code, payload = execute(values)
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return status_code


if __name__ == "__main__":
    raise SystemExit(main())
