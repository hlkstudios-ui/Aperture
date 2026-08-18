import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import (
    Admin,
    AuditLog,
    BillingInterval,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)


def test_admin_support_customer_billing_and_storage_workflow() -> None:
    suffix = uuid.uuid4().hex[:10]
    admin_email = f"support-admin-{suffix}@example.com"
    customer_email = f"support-customer-{suffix}@example.com"
    password = "AdministratorPass123"
    with SessionLocal() as db:
        admin = Admin(email=admin_email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    customer = TestClient(app, headers={"user-agent": "Support fixture browser"})
    registration = customer.post(
        "/auth/register",
        json={"email": customer_email, "password": password, "profile_name": "Viewer"},
    )
    assert registration.status_code == 201, registration.text
    with SessionLocal() as db:
        user_id = db.scalar(select(User.id).where(User.email == customer_email))
        assert user_id is not None
        plan = Plan(
            code=f"support-{suffix}",
            name=f"Support plan {suffix}",
            description="Support workflow fixture.",
            price_cents=1299,
            currency="CAD",
            interval=BillingInterval.month,
            max_streams=2,
            max_resolution="1080p",
        )
        db.add(plan)
        db.flush()
        db.add(
            Subscription(
                user_id=user_id,
                plan_id=plan.id,
                status=SubscriptionStatus.active,
                provider="fixture-provider",
                current_period_start=datetime.now(UTC),
                current_period_end=datetime.now(UTC) + timedelta(days=30),
            )
        )
        db.commit()
        plan_id = plan.id

    with TestClient(app) as anonymous:
        assert anonymous.get("/admin/support/users").status_code == 401

    with TestClient(app) as support:
        login = support.post("/admin/auth/login", json={"email": admin_email, "password": password})
        assert login.status_code == 200, login.text
        listing = support.get(f"/admin/support/users?q={customer_email}")
        assert listing.status_code == 200, listing.text
        assert listing.json()["total"] == 1
        assert listing.json()["items"][0]["plan_name"] == f"Support plan {suffix}"

        detail = support.get(f"/admin/support/users/{user_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["active_session_count"] == 1
        assert "password_hash" not in detail.text
        assert "token_hash" not in detail.text

        exported = support.get(f"/admin/support/users/{user_id}/export")
        assert exported.status_code == 200, exported.text
        assert exported.json()["format"] == "aperture-portable-customer-record-v1"
        assert exported.json()["customer"]["email"] == customer_email
        assert "records" in exported.json()["customer"]["profiles"][0]
        assert "provider_customer_ref" not in exported.text

        subscriptions = support.get(f"/admin/support/subscriptions?q={customer_email}")
        assert subscriptions.status_code == 200, subscriptions.text
        assert subscriptions.json()["items"][0]["provider"] == "fixture-provider"

        storage = support.get("/admin/support/storage")
        assert storage.status_code == 200, storage.text
        assert storage.json()["versioning"] in {"enabled", "suspended", "disabled", "unknown"}

        revoked = support.post(
            f"/admin/support/users/{user_id}/revoke-sessions",
            json={"reason": "Customer requested global sign-out"},
        )
        assert revoked.status_code == 200, revoked.text
        assert revoked.json()["sessions_revoked"] == 1
        assert customer.get("/account").status_code == 401

        disabled = support.patch(
            f"/admin/support/users/{user_id}/state",
            json={"is_active": False, "reason": "Fraud review hold"},
        )
        assert disabled.status_code == 200, disabled.text
        enabled = support.patch(
            f"/admin/support/users/{user_id}/state",
            json={"is_active": True, "reason": "Fraud review cleared"},
        )
        assert enabled.status_code == 200, enabled.text
        refused_delete = support.request(
            "DELETE",
            f"/admin/support/users/{user_id}",
            json={
                "confirmation_email": customer_email,
                "confirmation_phrase": "DELETE",
                "reason": "Approved customer privacy request",
                "authorization_reference": f"PRIVACY-{suffix}",
            },
        )
        assert refused_delete.status_code == 409
        deleted = support.request(
            "DELETE",
            f"/admin/support/users/{user_id}",
            json={
                "confirmation_email": customer_email,
                "confirmation_phrase": "DELETE CUSTOMER",
                "reason": "Approved customer privacy request",
                "authorization_reference": f"PRIVACY-{suffix}",
            },
        )
        assert deleted.status_code == 200, deleted.text
        assert deleted.json()["deleted_profiles"] == 1

    with SessionLocal() as db:
        actions = set(db.scalars(select(AuditLog.action).where(AuditLog.actor_id == admin_id)))
        assert {
            "support.customer.exported",
            "support.customer.sessions_revoked",
            "support.customer.state_updated",
            "support.customer.deleted",
        } <= actions
        assert db.get(User, user_id) is None
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Plan).where(Plan.id == plan_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
