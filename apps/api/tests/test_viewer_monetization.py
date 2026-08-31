import json
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import delete, select

from app.auth import hash_password
from app.config import Settings, get_settings
from app.db import SessionLocal
from app.main import app
from app.models import (
    Admin,
    AuditLog,
    SiteBrandConfiguration,
    ViewerPaymentConnection,
)
from app.site_brand_service import default_config


def _brand_snapshot() -> dict[str, object]:
    return {
        "schema_version": 1,
        **default_config().model_dump(mode="json"),
    }


def _connect_settings():
    return get_settings().model_copy(
        update={
            "stripe_connect_enabled": True,
            "stripe_connect_platform_secret_key": SecretStr(
                "sk_test_viewer_connect_private_fixture"
            ),
            "stripe_connect_webhook_secret": SecretStr("whsec_viewer_connect_private_fixture"),
        }
    )


def test_stripe_connect_configuration_is_separate_and_fail_closed() -> None:
    with pytest.raises(ValueError, match="requires BILLING_PROVIDER=disabled"):
        Settings(
            _env_file=None,
            billing_provider="development_stub",
            stripe_connect_enabled=True,
            stripe_connect_platform_secret_key="sk_test_private_fixture",
            stripe_connect_webhook_secret="whsec_private_fixture",
        )
    with pytest.raises(ValueError, match="requires BILLING_PROVIDER=disabled"):
        Settings(
            _env_file=None,
            billing_provider="stripe",
            stripe_secret_key="sk_test_legacy_private_fixture",
            stripe_webhook_secret="whsec_legacy_private_fixture",
            stripe_connect_enabled=True,
            stripe_connect_platform_secret_key="sk_test_private_fixture",
            stripe_connect_webhook_secret="whsec_private_fixture",
        )
    with pytest.raises(ValueError, match="are required"):
        Settings(_env_file=None, stripe_connect_enabled=True)
    with pytest.raises(ValueError, match="platform secret key"):
        Settings(
            _env_file=None,
            stripe_connect_enabled=True,
            stripe_connect_platform_secret_key="not-a-stripe-key",
            stripe_connect_webhook_secret="whsec_fixture",
        )
    with pytest.raises(ValueError, match="webhook signing secret"):
        Settings(
            _env_file=None,
            stripe_connect_enabled=True,
            stripe_connect_platform_secret_key="sk_test_private_fixture",
            stripe_connect_webhook_secret="not-a-webhook-secret",
        )
    configured = Settings(
        _env_file=None,
        stripe_connect_enabled=True,
        stripe_connect_platform_secret_key="sk_test_private_fixture",
        stripe_connect_webhook_secret="whsec_private_fixture",
    )
    assert configured.stripe_connect_enabled is True
    assert configured.billing_provider == "disabled"
    assert configured.stripe_connect_platform_secret_key.get_secret_value() == (
        "sk_test_private_fixture"
    )


def test_owner_only_hosted_onboarding_stays_free_until_verified_refresh(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:10]
    password = "ViewerMonetizationPassword123"
    owner_email = f"viewer-money-owner-{suffix}@example.com"
    other_email = f"viewer-money-other-{suffix}@example.com"
    with SessionLocal() as db:
        owner = Admin(email=owner_email, password_hash=hash_password(password))
        other = Admin(email=other_email, password_hash=hash_password(password))
        db.add_all([owner, other])
        db.flush()
        owner_id = owner.id
        other_id = other.id
        db.add(
            SiteBrandConfiguration(
                id=1,
                owner_admin_id=owner.id,
                draft_config=_brand_snapshot(),
                revision=0,
                current_step=1,
                completed_steps=[],
            )
        )
        db.commit()

    account_create_calls: list[dict] = []
    account_link_calls: list[dict] = []
    private_key = "sk_test_viewer_connect_private_fixture"
    webhook_secret = "whsec_viewer_connect_private_fixture"

    def fail_if_disabled(**_):
        raise AssertionError("disabled Stripe Connect must not call Stripe")

    monkeypatch.setattr(
        "app.viewer_monetization_service.stripe.Account.create",
        fail_if_disabled,
    )
    monkeypatch.setattr(
        "app.viewer_monetization_service.stripe.AccountLink.create",
        fail_if_disabled,
    )

    try:
        with TestClient(app) as anonymous:
            assert anonymous.get("/admin/viewer-monetization").status_code == 401

        with TestClient(app) as owner_client:
            assert (
                owner_client.post(
                    "/admin/auth/login",
                    json={"email": owner_email, "password": password},
                ).status_code
                == 200
            )
            disabled = owner_client.get("/admin/viewer-monetization")
            assert disabled.status_code == 200, disabled.text
            assert disabled.headers["cache-control"] == (
                "private, no-store, max-age=0, must-revalidate"
            )
            assert disabled.headers["pragma"] == "no-cache"
            assert disabled.headers["vary"] == "Cookie"
            assert disabled.json()["provider"] == "disabled"
            assert disabled.json()["connection"] == "disabled"
            assert disabled.json()["access_mode"] == "free"
            assert disabled.json()["access_mode_change_available"] is False
            refused = owner_client.post("/admin/viewer-monetization/providers/stripe/connect")
            assert refused.status_code == 503
            assert "disabled" in refused.json()["detail"].lower()

        with TestClient(app) as other_client:
            assert (
                other_client.post(
                    "/admin/auth/login",
                    json={"email": other_email, "password": password},
                ).status_code
                == 200
            )
            assert other_client.get("/admin/viewer-monetization").status_code == 403
            assert (
                other_client.post("/admin/viewer-monetization/providers/stripe/connect").status_code
                == 403
            )
            assert other_client.post("/admin/viewer-monetization/refresh").status_code == 403

        monkeypatch.setattr(
            "app.viewer_monetization_service.get_settings",
            lambda: _connect_settings(),
        )

        def create_account(**kwargs):
            account_create_calls.append(kwargs)
            return {"id": "acct_ViewerConnect123"}

        def create_link(**kwargs):
            account_link_calls.append(kwargs)
            return {
                "url": "https://connect.stripe.com/setup/c/test_fixture",
                "expires_at": 1_800_000_000,
            }

        monkeypatch.setattr(
            "app.viewer_monetization_service.stripe.Account.create",
            create_account,
        )
        monkeypatch.setattr(
            "app.viewer_monetization_service.stripe.AccountLink.create",
            create_link,
        )

        with TestClient(app) as owner_client:
            assert (
                owner_client.post(
                    "/admin/auth/login",
                    json={"email": owner_email, "password": password},
                ).status_code
                == 200
            )
            connected = owner_client.post("/admin/viewer-monetization/providers/stripe/connect")
            assert connected.status_code == 200, connected.text
            assert connected.json() == {
                "onboarding_url": "https://connect.stripe.com/setup/c/test_fixture",
                "expires_at": 1_800_000_000,
            }
            assert connected.headers["cache-control"] == (
                "private, no-store, max-age=0, must-revalidate"
            )
            assert account_create_calls[0]["type"] == "standard"
            assert account_create_calls[0]["api_key"] == private_key
            assert account_link_calls[0]["api_key"] == private_key
            assert account_link_calls[0]["account"] == "acct_ViewerConnect123"
            assert account_link_calls[0]["return_url"].endswith(
                "/studio/monetization?stripe_connect=return"
            )
            assert account_link_calls[0]["refresh_url"].endswith(
                "/studio/monetization?stripe_connect=refresh"
            )

            # Returning from Stripe is only navigation. It does not mutate provider truth.
            waiting = owner_client.get("/admin/viewer-monetization")
            assert waiting.status_code == 200
            assert waiting.json()["connection"] == "onboarding_required"
            assert waiting.json()["access_mode"] == "free"
            assert waiting.json()["details_submitted"] is False
            assert waiting.json()["charges_enabled"] is False
            assert waiting.json()["payouts_enabled"] is False
            assert waiting.json()["subscription_mode_eligible"] is False

            monkeypatch.setattr(
                "app.viewer_monetization_service.stripe.Account.retrieve",
                lambda account_id, **kwargs: {
                    "id": account_id,
                    "livemode": False,
                    "details_submitted": True,
                    "charges_enabled": True,
                    "payouts_enabled": True,
                    "requirements": {"currently_due": []},
                    "_test_api_key": kwargs["api_key"],
                },
            )
            refreshed = owner_client.post("/admin/viewer-monetization/refresh")
            assert refreshed.status_code == 200, refreshed.text
            body = refreshed.json()
            assert body["connection"] == "ready"
            assert body["provider"] == "stripe_connect"
            assert body["connected_account_id"] == "acct_ViewerConnect123"
            assert body["details_submitted"] is True
            assert body["charges_enabled"] is True
            assert body["payouts_enabled"] is True
            assert body["requirements_due"] == []
            assert body["active_plan_count"] >= 1
            assert body["subscription_mode_eligible"] is True
            assert body["access_mode"] == "free"
            assert body["access_mode_change_available"] is False
            assert "separately enabled" in body["notice"]

        with SessionLocal() as db:
            stored = db.get_one(ViewerPaymentConnection, 1)
            assert stored.owner_admin_id == owner_id
            assert stored.provider == "stripe_connect"
            assert stored.access_mode == "free"
            assert stored.revision == 2
            assert stored.details_submitted is True
            assert stored.charges_enabled is True
            assert stored.payouts_enabled is True
            audit_rows = list(
                db.scalars(
                    select(AuditLog).where(
                        AuditLog.actor_id == owner_id,
                        AuditLog.action.like("viewer_monetization.%"),
                    )
                )
            )
            assert {item.action for item in audit_rows} == {
                "viewer_monetization.stripe_account.created",
                "viewer_monetization.onboarding_link.created",
                "viewer_monetization.connection.refreshed",
            }
            serialized = json.dumps(
                {
                    "responses": [connected.json(), waiting.json(), body],
                    "audits": [item.detail for item in audit_rows],
                }
            )
            assert private_key not in serialized
            assert webhook_secret not in serialized
    finally:
        with SessionLocal() as db:
            db.execute(delete(ViewerPaymentConnection))
            db.execute(delete(SiteBrandConfiguration))
            db.execute(delete(AuditLog).where(AuditLog.actor_id.in_([owner_id, other_id])))
            db.execute(delete(Admin).where(Admin.id.in_([owner_id, other_id])))
            db.commit()
