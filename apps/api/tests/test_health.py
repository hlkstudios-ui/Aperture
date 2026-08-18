import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import app.main as main
from app.config import Settings, get_settings
from app.main import app


def test_health() -> None:
    response = TestClient(app).get("/health", headers={"x-request-id": "health-check-1"})
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "environment": "development"}
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert (
        response.headers["content-security-policy"] == "default-src 'none'; frame-ancestors 'none'"
    )
    assert "strict-transport-security" not in response.headers
    assert response.headers["x-request-id"] == "health-check-1"


def test_metrics_are_authenticated_and_include_api_and_operational_signals() -> None:
    with TestClient(app) as client:
        assert client.get("/metrics").status_code == 401
        response = client.get(
            "/metrics",
            headers={"authorization": f"Bearer {get_settings().metrics_bearer_token}"},
        )
    assert response.status_code == 200
    assert "aperture_api_requests_total" in response.text
    assert 'aperture_queue_backlog{queue="media"}' in response.text
    assert "aperture_storage_available 1" in response.text
    assert "aperture_transcode_duration_seconds_average" in response.text


def test_readiness_fails_closed_with_named_dependency_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unavailable() -> None:
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(main, "check_database", unavailable)
    response = TestClient(app).get("/ready")
    assert response.status_code == 503
    assert response.json()["status"] == "unavailable"
    assert response.json()["checks"]["database"] == "error"


def test_production_rejects_placeholder_credentials_and_insecure_origins() -> None:
    with pytest.raises(ValidationError, match="strong environment-specific secret"):
        Settings(_env_file=None, app_env="staging", session_secret="CHANGE_ME")

    with pytest.raises(ValidationError, match="Database and object-storage credentials"):
        Settings(
            _env_file=None,
            app_env="production",
            session_secret="a" * 64,
            smtp_host="smtp.example.com",
            smtp_username="aperture",
            smtp_password="strong-password",
            smtp_from_email="security@example.com",
            billing_provider="configured_provider",
        )

    with pytest.raises(ValidationError, match="ERROR_TRACKING_DSN"):
        Settings(
            _env_file=None,
            app_env="production",
            api_origin="https://api.example.com",
            web_origin="https://example.com",
            database_url="postgresql+psycopg://service:strong@db.example.com/aperture",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
            session_secret="a" * 64,
            smtp_host="smtp.example.com",
            smtp_username="aperture",
            smtp_password="strong-password",
            smtp_from_email="security@example.com",
            billing_provider="configured_provider",
            metrics_bearer_token="m" * 64,
        )

    with pytest.raises(ValidationError, match="object-storage origin"):
        Settings(
            _env_file=None,
            app_env="production",
            api_origin="https://api.example.com",
            web_origin="https://example.com",
            database_url="postgresql+psycopg://service:strong@db.example.com/aperture",
            s3_public_endpoint="http://storage.example.com",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
            session_secret="a" * 64,
            smtp_host="smtp.example.com",
            smtp_username="aperture",
            smtp_password="strong-password",
            smtp_from_email="security@example.com",
            billing_provider="configured_provider",
            metrics_bearer_token="m" * 64,
            error_tracking_dsn="https://public@example.ingest.sentry.io/1",
        )

    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(
            _env_file=None,
            app_env="production",
            api_origin="http://api.example.com",
            web_origin="https://example.com",
            database_url="postgresql+psycopg://service:strong@db.example.com/aperture",
            s3_access_key="production-access-key",
            s3_secret_key="production-secret-key",
            session_secret="a" * 64,
            smtp_host="smtp.example.com",
            smtp_username="aperture",
            smtp_password="strong-password",
            smtp_from_email="security@example.com",
            billing_provider="configured_provider",
        )


def test_production_requires_private_clamav_scanning() -> None:
    production = {
        "_env_file": None,
        "app_env": "production",
        "api_origin": "https://watch.example.com/api",
        "web_origin": "https://watch.example.com",
        "database_url": "postgresql+psycopg://service:strong@db.example.com/aperture",
        "s3_access_key": "production-access-key",
        "s3_secret_key": "production-secret-key",
        "session_secret": "s" * 64,
        "smtp_host": "smtp.example.com",
        "smtp_username": "aperture",
        "smtp_password": "strong-password",
        "smtp_from_email": "security@example.com",
        "billing_provider": "configured_provider",
        "metrics_bearer_token": "m" * 64,
        "error_tracking_dsn": "https://public@example.ingest.sentry.io/1",
        "media_delivery_mode": "cdn",
        "cdn_public_origin": "https://media.example.com",
        "cdn_signing_secret": "a" * 64,
        "cdn_origin_secret": "b" * 64,
        "geo_assertion_secret": "g" * 64,
        "private_studio_required": True,
        "studio_edge_secret": "p" * 64,
        "admin_web_origin": "https://studio.example-tailnet.ts.net",
    }
    with pytest.raises(ValidationError, match="ClamAV TCP"):
        Settings(**production, malware_scanner_mode="eicar")
    settings = Settings(
        **production,
        malware_scanner_mode="clamav_tcp",
        malware_scanner_host="private-clamd.internal",
    )
    assert settings.malware_scanner_mode == "clamav_tcp"
    without_private_studio = {
        key: value
        for key, value in production.items()
        if key not in {"private_studio_required", "studio_edge_secret", "admin_web_origin"}
    }
    with pytest.raises(ValidationError, match="PRIVATE_STUDIO_REQUIRED"):
        Settings(
            **without_private_studio,
            malware_scanner_mode="clamav_tcp",
            malware_scanner_host="private-clamd.internal",
        )
    with pytest.raises(ValidationError, match="must cover CDN_TOKEN_TTL_SECONDS"):
        Settings(
            **production,
            malware_scanner_mode="clamav_tcp",
            malware_scanner_host="private-clamd.internal",
            cdn_token_ttl_seconds=301,
            playback_lease_seconds=300,
        )


def test_private_studio_boundary_fails_closed(monkeypatch: pytest.MonkeyPatch) -> None:
    private_settings = Settings(
        _env_file=None,
        private_studio_required=True,
        studio_edge_secret="p" * 64,
        admin_web_origin="https://studio.example-tailnet.ts.net",
    )
    monkeypatch.setattr(main, "settings", private_settings)
    assert not main.private_studio_authorized("/admin/auth/login", None)
    assert not main.private_studio_authorized("/admin/auth/login", "wrong")
    assert main.private_studio_authorized("/admin/auth/login", "p" * 64)
    assert main.private_studio_authorized("/catalog/movies", None)

    with TestClient(app) as client:
        assert client.post("/admin/auth/login", json={}).status_code == 404
        accepted = client.post(
            "/admin/auth/login",
            json={},
            headers={"x-aperture-studio-edge": "p" * 64},
        )
        assert accepted.status_code != 404
