import importlib.util
import json
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[3] / "deploy" / "production" / "public_edge_smoke.py"
)
SPEC = importlib.util.spec_from_file_location("public_edge_smoke", MODULE_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(smoke)

SECURITY = {
    "content-security-policy": "default-src 'none'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "DENY",
    "referrer-policy": "no-referrer",
    "permissions-policy": "camera=()",
    "strict-transport-security": "max-age=31536000",
}


def response(status, content_type="application/json", body=b"{}"):
    return smoke.Response(status, {**SECURITY, "content-type": content_type}, body)


def test_production_edge_checks_routing_readiness_denial_and_hidden_docs(monkeypatch) -> None:
    seen = []

    def fake_fetch(url, context):
        seen.append(url)
        if url == "https://watch.example.com/":
            return response(200, "text/html", b"<html></html>")
        if url == "https://watch.example.com/api/gateway/auth/oauth/providers":
            value = response(200)
            return smoke.Response(
                value.status,
                {**value.headers, "cache-control": "private, no-store", "vary": "Cookie"},
                value.body,
            )
        if url == "https://watch.example.com/api/ready":
            value = response(200, body=json.dumps({"status": "ready"}).encode())
            return smoke.Response(
                value.status,
                {**value.headers, "x-request-id": "production-smoke"},
                value.body,
            )
        return response(404)

    monkeypatch.setattr(smoke, "fetch", fake_fetch)
    result = smoke.verify(
        "https://watch.example.com/",
        production=True,
        context=object(),
    )
    assert result == {"event": "public_edge.verified", "status": "pass", "checks": 20}
    assert "https://watch.example.com/api/admin/support/users" in seen
    assert "https://watch.example.com/api/openapi.json" in seen
    assert "https://watch.example.com/studio" in seen
    assert "https://watch.example.com/studio/login" in seen


def test_production_requires_hsts() -> None:
    value = response(200)
    without_hsts = smoke.Response(
        value.status,
        {key: item for key, item in value.headers.items() if key != "strict-transport-security"},
        value.body,
    )
    try:
        smoke.security_headers(without_hsts, production=True)
    except RuntimeError as error:
        assert "strict-transport-security" in str(error)
    else:
        raise AssertionError("production response passed without HSTS")


def test_origin_requires_https_and_rejects_paths() -> None:
    assert smoke.origin("web", "https://watch.example.com").endswith("/")
    for value in (
        "http://watch.example.com",
        "https://watch.example.com/api",
        "https://watch.example.com/customer",
    ):
        try:
            smoke.origin("web", value)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe edge origin was accepted")
