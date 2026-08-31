import uuid

import pyotp
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog, User


def test_customer_login_profile_switch_and_admin_isolation() -> None:
    suffix = uuid.uuid4().hex
    email = f"viewer-{suffix}@example.com"
    password = "StrongPassword123"

    with TestClient(app) as client:
        registration = client.post(
            "/auth/register",
            json={
                "email": email,
                "password": password,
                "profile_name": "Primary",
                "captcha_token": "local-captcha-pass",
            },
        )
        assert registration.status_code == 201
        assert "Domain=" not in registration.headers["set-cookie"]
        primary_id = registration.json()["active_profile_id"]
        invalid_timezone = client.patch(
            f"/profiles/{primary_id}",
            json={"preference": {"timezone": "Mars/Olympus_Mons"}},
        )
        assert invalid_timezone.status_code == 422
        localized = client.patch(
            f"/profiles/{primary_id}",
            json={
                "language": "fr",
                "preference": {
                    "timezone": "America/Toronto",
                    "preferred_audio_language": "fr",
                    "preferred_subtitle_language": "en",
                    "subtitles_enabled": True,
                },
            },
        )
        assert localized.status_code == 200
        assert localized.json()["language"] == "fr"
        assert localized.json()["preference"]["timezone"] == "America/Toronto"

        second = client.post("/profiles", json={"name": "Cinephile"})
        assert second.status_code == 201
        second_id = second.json()["id"]
        switched = client.post(f"/profiles/{second_id}/switch")
        assert switched.status_code == 200
        assert client.get("/auth/me").json()["active_profile_id"] == second_id
        assert primary_id != second_id

        assert client.get("/admin/auth/authorization-check").status_code == 401
        assert client.post("/auth/logout").status_code == 204
        assert client.get("/auth/me").status_code == 401
        recognized = client.get("/auth/remembered-accounts")
        assert recognized.status_code == 200
        assert recognized.json()["accounts"][0]["email"] == email

        login = client.post(
            "/auth/login",
            json={"email": email, "password": password, "captcha_token": "local-captcha-pass"},
        )
        assert login.status_code == 200
        assert login.headers["set-cookie"].startswith("aperture_session=")
        assert "Domain=" not in login.headers["set-cookie"]

        reset_request = client.post("/auth/password-reset/request", json={"email": email})
        assert reset_request.status_code == 200
        reset_token = reset_request.json()["development_reset_token"]
        assert reset_token
        new_password = "NewStrongPassword456"
        reset = client.post(
            "/auth/password-reset/confirm",
            json={"token": reset_token, "password": new_password},
        )
        assert reset.status_code == 200
        assert reset.json() == {"status": "password_updated"}
        assert client.get("/auth/me").status_code == 401
        assert (
            client.post(
                "/auth/login",
                json={"email": email, "password": password, "captcha_token": "local-captcha-pass"},
            ).status_code
            == 401
        )
        assert (
            client.post(
                "/auth/login",
                json={
                    "email": email,
                    "password": new_password,
                    "captcha_token": "local-captcha-pass",
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                "/auth/password-reset/confirm",
                json={"token": reset_token, "password": "AnotherStrongPassword789"},
            ).status_code
            == 400
        )
        identity_id = client.get("/auth/remembered-accounts").json()["accounts"][0]["id"]
        assert client.delete(f"/auth/remembered-accounts/{identity_id}").status_code == 204
        assert client.get("/auth/remembered-accounts").json() == {"accounts": []}

    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.commit()


def test_admin_login_and_customer_cannot_supply_admin_authority() -> None:
    suffix = uuid.uuid4().hex
    admin_email = f"admin-{suffix}@example.com"
    customer_email = f"viewer-{suffix}@example.com"
    admin_password = "AdministratorPass123"

    with SessionLocal() as db:
        admin = Admin(email=admin_email, password_hash=hash_password(admin_password))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    with TestClient(app) as customer_client:
        customer_client.post(
            "/auth/register",
            json={
                "email": customer_email,
                "password": "CustomerPassword123",
                "profile_name": "Viewer",
                "captcha_token": "local-captcha-pass",
            },
        )
        assert customer_client.get("/admin/auth/authorization-check").status_code == 401

    with TestClient(app) as admin_client:
        denied = admin_client.post(
            "/admin/auth/login",
            json={"email": admin_email, "password": "wrong-password"},
        )
        assert denied.status_code == 401
        login = admin_client.post(
            "/admin/auth/login",
            json={"email": admin_email, "password": admin_password},
        )
        assert login.status_code == 200
        assert "HttpOnly" in login.headers["set-cookie"]
        assert "SameSite=strict" in login.headers["set-cookie"]
        assert admin_client.get("/admin/auth/authorization-check").status_code == 200

        enrollment = admin_client.post("/admin/auth/mfa/enroll")
        assert enrollment.status_code == 200
        totp = pyotp.TOTP(enrollment.json()["secret"])
        confirmation = admin_client.post("/admin/auth/mfa/confirm", json={"code": totp.now()})
        assert confirmation.status_code == 200
        recovery_codes = confirmation.json()["recovery_codes"]
        assert len(recovery_codes) == 8
        assert admin_client.post("/admin/auth/logout").status_code == 204
        assert admin_client.get("/admin/auth/authorization-check").status_code == 401
        assert (
            admin_client.post(
                "/admin/auth/login",
                json={"email": admin_email, "password": admin_password},
            ).status_code
            == 401
        )
        mfa_login = admin_client.post(
            "/admin/auth/login",
            json={"email": admin_email, "password": admin_password, "mfa_code": totp.now()},
        )
        assert mfa_login.status_code == 200
        admin_client.post("/admin/auth/logout")
        recovery_login = admin_client.post(
            "/admin/auth/login",
            json={
                "email": admin_email,
                "password": admin_password,
                "mfa_code": recovery_codes[0],
            },
        )
        assert recovery_login.status_code == 200
        admin_client.post("/admin/auth/logout")
        assert (
            admin_client.post(
                "/admin/auth/login",
                json={
                    "email": admin_email,
                    "password": admin_password,
                    "mfa_code": recovery_codes[0],
                },
            ).status_code
            == 401
        )

    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == customer_email))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
