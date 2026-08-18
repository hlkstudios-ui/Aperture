import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.main import app
from app.models import Entitlement, Plan, Subscription, SubscriptionStatus, User


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
            "provider": "development_stub",
            "production_ready": False,
            "checkout_available": False,
            "notice": "Billing is not configured and never simulates completed payment.",
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
