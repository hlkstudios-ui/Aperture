import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import (
    Admin,
    Entitlement,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
    ViewerPaymentConnection,
)


def test_account_subscription_entitlements_and_owned_session_revocation() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"account-{token}@example.com"
    password = "AccountPassword123"
    next_password = "ChangedAccountPassword456"
    first = TestClient(app, headers={"user-agent": "Aperture Desktop Test"})
    second = TestClient(app, headers={"user-agent": "Aperture Mobile Test"})
    third = TestClient(app, headers={"user-agent": "Aperture TV Test"})
    try:
        registered = first.post(
            "/auth/register",
            json={"email": email, "password": password, "profile_name": "Account Viewer"},
        )
        assert registered.status_code == 201, registered.text
        assert (
            second.post("/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )
        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            plan = db.scalar(select(Plan).where(Plan.code == "cinephile-monthly"))
            subscription = Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.active,
                provider="test_provider",
                provider_customer_ref=f"customer-{token}",
                provider_subscription_ref=f"subscription-{token}",
                current_period_start=datetime.now(UTC),
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )
            db.add(subscription)
            db.flush()
            db.add(
                Entitlement(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    key="simultaneous_streams",
                    value={"limit": 4},
                    source="test_provider",
                )
            )
            db.commit()

        account = first.get("/account")
        assert account.status_code == 200, account.text
        assert account.json()["subscription"]["status"] == "active"
        assert account.json()["subscription"]["plan"]["code"] == "cinephile-monthly"
        assert account.json()["entitlements"][0]["value"] == {"limit": 4}
        assert len(account.json()["sessions"]) == 2
        assert account.json()["billing"] == {
            "provider": "disabled",
            "production_ready": False,
            "checkout_available": False,
            "notice": (
                "Payments are intentionally disabled for this launch. No payment can be accepted."
            ),
        }
        checkout = first.post("/account/checkout", json={"plan_code": "essential-monthly"})
        assert checkout.status_code == 409
        assert "existing subscription" in checkout.json()["detail"]
        portal = first.post("/account/billing-portal")
        assert portal.status_code == 404
        assert "No provider billing account" in portal.json()["detail"]

        other_session = next(item for item in account.json()["sessions"] if not item["current"])
        assert first.delete(f"/account/sessions/{other_session['id']}").status_code == 204
        assert second.get("/account").status_code == 401

        assert (
            third.post("/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )
        changed = first.post(
            "/account/password",
            json={"current_password": password, "new_password": next_password},
        )
        assert changed.status_code == 204, changed.text
        assert third.get("/account").status_code == 401
        assert first.get("/account").status_code == 200
        assert (
            TestClient(app)
            .post("/auth/login", json={"email": email, "password": next_password})
            .status_code
            == 200
        )
    finally:
        first.close()
        second.close()
        third.close()
        with SessionLocal() as db:
            db.execute(delete(User).where(User.email == email))
            db.commit()


def test_viewer_monetization_row_isolates_legacy_customer_billing(monkeypatch) -> None:
    token = uuid.uuid4().hex[:12]
    email = f"billing-boundary-{token}@example.com"
    admin_email = f"billing-boundary-owner-{token}@example.com"
    password = "BillingBoundaryPassword123"
    client = TestClient(app)

    def legacy_provider_must_not_be_resolved():
        pytest.fail("a viewer payment connection must isolate the legacy billing provider")

    try:
        registered = client.post(
            "/auth/register",
            json={"email": email, "password": password, "profile_name": "Billing Boundary"},
        )
        assert registered.status_code == 201, registered.text

        with SessionLocal() as db:
            owner = Admin(email=admin_email, password_hash="not-used-by-this-test")
            db.add(owner)
            db.flush()
            db.add(
                ViewerPaymentConnection(
                    id=1,
                    owner_admin_id=owner.id,
                    provider="stripe_connect",
                    access_mode="free",
                    stripe_connected_account_id=f"acct_{token}",
                    livemode=False,
                    details_submitted=False,
                    charges_enabled=False,
                    payouts_enabled=False,
                    requirements_due=[],
                    revision=1,
                )
            )
            db.commit()

        monkeypatch.setattr(
            "app.routes.account.get_billing_provider",
            legacy_provider_must_not_be_resolved,
        )
        dashboard = client.get("/account")
        assert dashboard.status_code == 200, dashboard.text
        assert dashboard.json()["billing"] == {
            "provider": "stripe_connect",
            "production_ready": False,
            "checkout_available": False,
            "notice": (
                "Viewer monetization is isolated from legacy billing. Checkout and the legacy "
                "billing portal remain disabled."
            ),
        }
        checkout = client.post(
            "/account/checkout",
            json={"plan_code": "essential-monthly"},
        )
        assert checkout.status_code == 503
        assert "isolated from legacy billing" in checkout.json()["detail"]
        portal = client.post("/account/billing-portal")
        assert portal.status_code == 503
        assert "isolated from legacy billing" in portal.json()["detail"]

        with SessionLocal() as db:
            db.execute(delete(ViewerPaymentConnection).where(ViewerPaymentConnection.id == 1))
            db.commit()

        checkout_calls: list[str] = []
        portal_calls: list[str] = []

        def create_checkout(user, plan, return_origin=None):
            checkout_calls.append(f"{user.id}:{plan.code}:{return_origin}")
            return SimpleNamespace(provider="stripe", checkout_url="https://checkout.stripe.test")

        def create_portal(customer_reference, return_origin=None):
            portal_calls.append(f"{customer_reference}:{return_origin}")
            return SimpleNamespace(provider="stripe", portal_url="https://portal.stripe.test")

        legacy_provider = SimpleNamespace(
            name="stripe",
            production_ready=True,
            create_checkout=create_checkout,
            create_portal=create_portal,
        )
        monkeypatch.setattr(
            "app.routes.account.get_billing_provider",
            lambda: legacy_provider,
        )
        legacy_dashboard = client.get("/account")
        assert legacy_dashboard.status_code == 200, legacy_dashboard.text
        assert legacy_dashboard.json()["billing"] == {
            "provider": "stripe",
            "production_ready": True,
            "checkout_available": True,
            "notice": None,
        }
        legacy_checkout = client.post(
            "/account/checkout",
            json={"plan_code": "essential-monthly"},
        )
        assert legacy_checkout.status_code == 200, legacy_checkout.text
        assert legacy_checkout.json()["provider"] == "stripe"
        assert len(checkout_calls) == 1

        with SessionLocal() as db:
            user = db.scalar(select(User).where(User.email == email))
            plan = db.scalar(select(Plan).where(Plan.code == "essential-monthly"))
            db.add(
                Subscription(
                    user_id=user.id,
                    plan_id=plan.id,
                    status=SubscriptionStatus.active,
                    provider="stripe",
                    provider_customer_ref=f"cus_{token}",
                    provider_subscription_ref=f"sub_{token}",
                )
            )
            db.commit()

        legacy_portal = client.post("/account/billing-portal")
        assert legacy_portal.status_code == 200, legacy_portal.text
        assert legacy_portal.json()["provider"] == "stripe"
        assert len(portal_calls) == 1
    finally:
        client.close()
        with SessionLocal() as db:
            db.execute(delete(ViewerPaymentConnection).where(ViewerPaymentConnection.id == 1))
            db.execute(delete(Admin).where(Admin.email == admin_email))
            db.execute(delete(User).where(User.email == email))
            db.commit()
