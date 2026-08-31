import uuid
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import hash_password
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog


def make_admin() -> tuple[str, str, uuid.UUID]:
    token = uuid.uuid4().hex[:10]
    email = f"revenue-admin-{token}@example.com"
    password = "AdministratorPass123"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        return email, password, admin.id


def test_revenue_is_truthful_and_fail_closed_without_stripe(monkeypatch) -> None:
    email, password, admin_id = make_admin()
    monkeypatch.setattr(
        "app.routes.admin_revenue.get_settings",
        lambda: SimpleNamespace(
            billing_provider="disabled",
            stripe_secret_key="sk_live_unused_must_not_be_called",
            stripe_payouts_enabled=False,
        ),
    )
    monkeypatch.setattr(
        "app.routes.admin_revenue.stripe.Balance.retrieve",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("disabled billing must not retrieve Stripe balances")
        ),
    )
    monkeypatch.setattr(
        "app.routes.admin_revenue.stripe.Payout.create",
        lambda **_: (_ for _ in ()).throw(
            AssertionError("disabled billing must not create Stripe payouts")
        ),
    )
    with TestClient(app) as client:
        assert (
            client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        snapshot = client.get("/admin/revenue")
        assert snapshot.status_code == 200
        assert snapshot.json()["provider"] == "disabled"
        assert snapshot.json()["connection"] == "not_configured"
        assert snapshot.json()["available"] == []
        refused = client.post(
            "/admin/revenue/payouts",
            json={
                "amount": 100,
                "currency": "cad",
                "confirmation": "CREATE PAYOUT",
                "request_id": str(uuid.uuid4()),
            },
        )
        assert refused.status_code == 503
    with SessionLocal() as db:
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()


def test_stripe_balance_and_idempotent_payout_are_audited(monkeypatch) -> None:
    email, password, admin_id = make_admin()
    monkeypatch.setattr(
        "app.routes.admin_revenue.get_settings",
        lambda: SimpleNamespace(
            billing_provider="stripe",
            stripe_secret_key="sk_test_fixture",
            stripe_payouts_enabled=True,
        ),
    )
    balance = SimpleNamespace(
        livemode=False,
        available=[SimpleNamespace(amount=2500, currency="cad")],
        pending=[SimpleNamespace(amount=900, currency="cad")],
    )
    monkeypatch.setattr("app.routes.admin_revenue.stripe.Balance.retrieve", lambda **_: balance)
    monkeypatch.setattr(
        "app.routes.admin_revenue.stripe.Payout.list",
        lambda **_: SimpleNamespace(data=[]),
    )
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(
            id="po_test_aperture",
            amount=1200,
            currency="cad",
            status="pending",
            arrival_date=1787356800,
            livemode=False,
        )

    monkeypatch.setattr("app.routes.admin_revenue.stripe.Payout.create", create)
    request_id = uuid.uuid4()
    with TestClient(app) as client:
        assert (
            client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        snapshot = client.get("/admin/revenue").json()
        assert snapshot["available"] == [{"amount": 2500, "currency": "cad"}]
        payout = client.post(
            "/admin/revenue/payouts",
            json={
                "amount": 1200,
                "currency": "CAD",
                "confirmation": "CREATE PAYOUT",
                "request_id": str(request_id),
            },
        )
        assert payout.status_code == 201, payout.text
        assert payout.json()["id"] == "po_test_aperture"
        assert captured["idempotency_key"] == f"studio-payout-{request_id}"
        assert captured["api_key"] == "sk_test_fixture"
    with SessionLocal() as db:
        action = db.scalar(
            select(AuditLog).where(
                AuditLog.actor_id == admin_id, AuditLog.action == "revenue.payout.created"
            )
        )
        assert action is not None
        assert action.detail["amount"] == 1200
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
