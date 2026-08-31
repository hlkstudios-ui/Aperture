"""Credential-free smoke checks for a deployed HTTPS customer edge."""

import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit


@dataclass(frozen=True)
class Response:
    status: int
    headers: dict[str, str]
    body: bytes


def origin(label: str, value: str) -> str:
    parsed = urlsplit(value)
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.query
        or parsed.fragment
        or parsed.path not in {"", "/"}
    ):
        raise ValueError(f"{label} must be a valid HTTPS edge base")
    return value.rstrip("/") + "/"


def fetch(url: str, context: ssl.SSLContext) -> Response:
    request = urllib.request.Request(
        url,
        headers={"Accept": "application/json, text/html", "X-Request-ID": "production-smoke"},
    )
    try:
        response = urllib.request.urlopen(request, context=context, timeout=15)
    except urllib.error.HTTPError as error:
        with error:
            return Response(
                error.status,
                {key.lower(): value for key, value in error.headers.items()},
                error.read(256 * 1024),
            )
    with response:
        return Response(
            response.status,
            {key.lower(): value for key, value in response.headers.items()},
            response.read(256 * 1024),
        )


def security_headers(response: Response, *, production: bool) -> None:
    expected = {
        "content-security-policy",
        "x-content-type-options",
        "x-frame-options",
        "referrer-policy",
        "permissions-policy",
    }
    if production:
        expected.add("strict-transport-security")
    missing = sorted(expected - response.headers.keys())
    if missing:
        raise RuntimeError("response is missing required security headers: " + ", ".join(missing))
    if response.headers["x-content-type-options"].lower() != "nosniff":
        raise RuntimeError("response does not enforce nosniff")
    if response.headers["x-frame-options"].upper() != "DENY":
        raise RuntimeError("response does not deny framing")


def private_gateway_headers(response: Response) -> None:
    cache_control = response.headers.get("cache-control", "").lower()
    if "private" not in cache_control or "no-store" not in cache_control:
        raise RuntimeError("same-origin gateway response is not private and non-cacheable")
    vary = {value.strip().lower() for value in response.headers.get("vary", "").split(",")}
    if "cookie" not in vary:
        raise RuntimeError("same-origin gateway response does not vary on Cookie")


def verify(web_origin: str, *, production: bool, context) -> dict[str, object]:
    web = fetch(urljoin(web_origin, "/"), context)
    if web.status != 200 or "text/html" not in web.headers.get("content-type", ""):
        raise RuntimeError("customer edge did not return HTML")
    security_headers(web, production=production)

    hidden_studio = {
        "studio": fetch(urljoin(web_origin, "/studio"), context).status,
        "studio_login": fetch(urljoin(web_origin, "/studio/login"), context).status,
    }
    if production and any(code != 404 for code in hidden_studio.values()):
        raise RuntimeError("Studio is exposed on the public web edge")

    gateway = fetch(urljoin(web_origin, "/api/gateway/auth/oauth/providers"), context)
    if gateway.status != 200 or "application/json" not in gateway.headers.get("content-type", ""):
        raise RuntimeError("same-origin API gateway failed")
    security_headers(gateway, production=production)
    private_gateway_headers(gateway)

    ready = fetch(urljoin(web_origin, "/api/ready"), context)
    if ready.status != 200 or "application/json" not in ready.headers.get("content-type", ""):
        raise RuntimeError("API readiness failed")
    security_headers(ready, production=production)
    if ready.headers.get("x-request-id") != "production-smoke":
        raise RuntimeError("edge did not preserve the smoke request ID")
    ready_value = json.loads(ready.body)
    if ready_value.get("status") != "ready":
        raise RuntimeError("API dependencies are not ready")

    denied = {
        "customer_account": fetch(urljoin(web_origin, "/api/account"), context).status,
        "oauth": fetch(urljoin(web_origin, "/api/auth/oauth/providers"), context).status,
        "studio_users": fetch(urljoin(web_origin, "/api/admin/support/users"), context).status,
        "metrics": fetch(urljoin(web_origin, "/api/metrics"), context).status,
    }
    allowed_denial_statuses = {404} if production else {401, 403, 404}
    if any(code not in allowed_denial_statuses for code in denied.values()):
        raise RuntimeError("a direct API surface remains publicly routed")
    forbidden_gateway = {
        path: fetch(urljoin(web_origin, f"/api/gateway/{path}"), context).status
        for path in ("billing", "edge-media", "metrics", "ready")
    }
    if any(code != 404 for code in forbidden_gateway.values()):
        raise RuntimeError("a non-browser API surface is reachable through the gateway")
    if production:
        for path in ("/api/docs", "/api/openapi.json", "/api/redoc"):
            if fetch(urljoin(web_origin, path), context).status != 404:
                raise RuntimeError("production API documentation is publicly exposed")
    return {
        "event": "public_edge.verified",
        "status": "pass",
        "checks": 20 if production else 14,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--environment", choices=("staging", "production"), required=True)
    args = parser.parse_args()
    try:
        web = origin("SMOKE_WEB_ORIGIN", os.environ.get("SMOKE_WEB_ORIGIN", ""))
        ca_file = os.environ.get("SMOKE_CA_FILE")
        context = ssl.create_default_context(cafile=ca_file)
        result = verify(web, production=args.environment == "production", context=context)
    except Exception:
        print(json.dumps({"event": "public_edge.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
