import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete, select

import app.routes.admin_auth as admin_auth
from app.auth import hash_password
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog


def development_settings(
    email: str | None = None,
    *,
    enabled: bool = True,
) -> Settings:
    return Settings(
        _env_file=None,
        app_env="development",
        web_origin=get_settings().web_origin,
        studio_dev_auto_login=enabled,
        studio_dev_admin_email=email,
    )


def configured_origin() -> str:
    return str(get_settings().web_origin).rstrip("/")


def test_development_session_issues_a_normal_usable_admin_cookie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"studio-owner-{uuid.uuid4().hex}@example.com"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password("UnusedDevelopmentPassword123"))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    monkeypatch.setattr(admin_auth, "settings", development_settings(email))
    try:
        with TestClient(app) as client:
            response = client.post(
                "/admin/auth/development-session",
                headers={"origin": configured_origin()},
            )
            assert response.status_code == 200
            assert response.json() == {
                "id": str(admin_id),
                "email": email,
                "mfa_enabled": False,
            }
            assert response.headers["set-cookie"].startswith("aperture_admin_session=")
            assert "HttpOnly" in response.headers["set-cookie"]
            assert "SameSite=strict" in response.headers["set-cookie"]

            current_admin = client.get("/admin/auth/me")
            assert current_admin.status_code == 200
            assert current_admin.json()["id"] == str(admin_id)

        with SessionLocal() as db:
            action = db.scalar(select(AuditLog.action).where(AuditLog.actor_id == admin_id))
            assert action == "admin.development_session"
    finally:
        with SessionLocal() as db:
            db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_development_session_is_not_discoverable_when_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin_auth, "settings", development_settings(enabled=False))
    response = TestClient(app).post(
        "/admin/auth/development-session",
        headers={"origin": configured_origin()},
    )
    assert response.status_code == 404


def test_development_session_fails_closed_for_an_unknown_or_inactive_admin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unknown_email = f"missing-studio-owner-{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(admin_auth, "settings", development_settings(unknown_email))
    unknown = TestClient(app).post(
        "/admin/auth/development-session",
        headers={"origin": configured_origin()},
    )
    assert unknown.status_code == 404

    inactive_email = f"inactive-studio-owner-{uuid.uuid4().hex}@example.com"
    with SessionLocal() as db:
        admin = Admin(
            email=inactive_email,
            password_hash=hash_password("UnusedDevelopmentPassword123"),
            is_active=False,
        )
        db.add(admin)
        db.commit()
        admin_id = admin.id

    monkeypatch.setattr(admin_auth, "settings", development_settings(inactive_email))
    try:
        inactive = TestClient(app).post(
            "/admin/auth/development-session",
            headers={"origin": configured_origin()},
        )
        assert inactive.status_code == 404
    finally:
        with SessionLocal() as db:
            db.execute(delete(Admin).where(Admin.id == admin_id))
            db.commit()


def test_development_session_rejects_missing_origin_and_remote_callers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"local-only-studio-owner-{uuid.uuid4().hex}@example.com"
    monkeypatch.setattr(admin_auth, "settings", development_settings(email))

    assert TestClient(app).post("/admin/auth/development-session").status_code == 403
    assert (
        TestClient(app)
        .post(
            "/admin/auth/development-session",
            headers={"origin": "https://untrusted.example"},
        )
        .status_code
        == 403
    )
    with TestClient(app, client=("203.0.113.10", 50000)) as remote_client:
        remote = remote_client.post(
            "/admin/auth/development-session",
            headers={"origin": configured_origin()},
        )
    assert remote.status_code == 403


def test_public_local_studio_uses_web_origin_even_when_admin_origin_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    email = f"origin-selection-studio-owner-{uuid.uuid4().hex}@example.com"
    local_settings = development_settings(email)
    local_settings.admin_web_origin = "https://private-studio.example"
    local_settings.private_studio_required = False
    monkeypatch.setattr(admin_auth, "settings", local_settings)

    response = TestClient(app).post(
        "/admin/auth/development-session",
        headers={"origin": configured_origin()},
    )
    assert response.status_code == 404


@pytest.mark.parametrize("app_env", ["test", "staging", "production"])
def test_development_auto_login_configuration_is_development_only(app_env: str) -> None:
    email = "studio-owner@example.com"
    with pytest.raises(ValidationError, match="allowed only in development"):
        Settings(
            _env_file=None,
            app_env=app_env,
            studio_dev_auto_login=True,
            studio_dev_admin_email=email,
        )
    with pytest.raises(ValidationError, match="STUDIO_DEV_ADMIN_EMAIL is required"):
        Settings(_env_file=None, app_env="development", studio_dev_auto_login=True)
