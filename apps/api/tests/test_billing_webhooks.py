import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.db import SessionLocal
from app.main import app
from app.models import (
    BillingWebhookEvent,
    PaymentReference,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)


def test_stripe_webhook_is_verified_and_idempotent(monkeypatch) -> None:
    event_id = f"evt_test_{uuid.uuid4().hex}"
    monkeypatch.setattr(
        "app.routes.billing_webhooks.get_settings",
        lambda: SimpleNamespace(
            billing_provider="stripe",
            stripe_secret_key="sk_test_fake_only",
            stripe_webhook_secret="whsec_fake_only",
        ),
    )
    monkeypatch.setattr(
        "app.routes.billing_webhooks.stripe.Webhook.construct_event",
        lambda payload, signature, secret: (
            {
                "id": event_id,
                "type": "checkout.session.completed",
                "data": {"object": {}},
            }
            if payload == b"fake-signed-payload"
            and signature == "fake-signature"
            and secret == "whsec_fake_only"
            else (_ for _ in ()).throw(ValueError("invalid"))
        ),
    )
    client = TestClient(app)
    try:
        for _ in range(2):
            response = client.post(
                "/billing/stripe/webhook",
                content=b"fake-signed-payload",
                headers={"stripe-signature": "fake-signature"},
            )
            assert response.status_code == 204, response.text
        with SessionLocal() as db:
            assert (
                db.scalar(
                    select(func.count())
                    .select_from(BillingWebhookEvent)
                    .where(BillingWebhookEvent.external_event_id == event_id)
                )
                == 1
            )
    finally:
        client.close()
        with SessionLocal() as db:
            db.execute(
                delete(BillingWebhookEvent).where(BillingWebhookEvent.external_event_id == event_id)
            )
            db.commit()


def test_invoice_webhooks_persist_success_and_failed_payment_state(monkeypatch) -> None:
    token = uuid.uuid4().hex
    email = f"billing-{token}@example.com"
    subscription_ref = f"sub_test_{token}"
    paid_invoice = f"in_paid_{token}"
    failed_invoice = f"in_failed_{token}"
    with SessionLocal() as db:
        plan = db.scalar(select(Plan).where(Plan.code == "essential-monthly"))
        user = User(email=email, password_hash="not-used-in-this-test")
        db.add(user)
        db.flush()
        user_id = user.id
        db.add(
            Subscription(
                user_id=user.id,
                plan_id=plan.id,
                status=SubscriptionStatus.active,
                provider="stripe",
                provider_customer_ref=f"cus_test_{token}",
                provider_subscription_ref=subscription_ref,
            )
        )
        db.commit()
    monkeypatch.setattr(
        "app.routes.billing_webhooks.get_settings",
        lambda: SimpleNamespace(
            billing_provider="stripe",
            stripe_secret_key="sk_test_fake_only",
            stripe_webhook_secret="whsec_fake_only",
        ),
    )

    def construct(payload, *_):
        if payload == b"subscription":
            return {
                "id": f"evt_subscription_{token}",
                "type": "customer.subscription.updated",
                "data": {"object": {"id": subscription_ref}},
            }
        failed = payload == b"failed"
        invoice_id = failed_invoice if failed else paid_invoice
        return {
            "id": f"evt_{invoice_id}",
            "type": "invoice.payment_failed" if failed else "invoice.paid",
            "data": {
                "object": {
                    "id": invoice_id,
                    "subscription": subscription_ref,
                    "amount_paid": 1299,
                    "amount_due": 1299,
                    "currency": "cad",
                    "status_transitions": {"paid_at": int(datetime.now(UTC).timestamp())},
                }
            },
        }

    monkeypatch.setattr("app.routes.billing_webhooks.stripe.Webhook.construct_event", construct)
    monkeypatch.setattr(
        "app.routes.billing_webhooks.stripe.Invoice.retrieve",
        lambda invoice_id, **_: {
            "id": invoice_id,
            "subscription": subscription_ref,
            "status": "paid" if invoice_id == paid_invoice else "open",
            "amount_paid": 1299,
            "amount_due": 1299,
            "currency": "cad",
            "status_transitions": {"paid_at": int(datetime.now(UTC).timestamp())},
        },
    )
    monkeypatch.setattr(
        "app.routes.billing_webhooks.stripe.Subscription.retrieve",
        lambda subscription_id, **_: {
            "id": subscription_id,
            "customer": f"cus_test_{token}",
            "status": "past_due",
            "metadata": {"user_id": str(user_id), "plan_code": "essential-monthly"},
            "current_period_start": None,
            "current_period_end": None,
            "cancel_at_period_end": False,
            "canceled_at": None,
        },
    )
    client = TestClient(app)
    try:
        assert client.post("/billing/stripe/webhook", content=b"paid").status_code == 204
        assert client.post("/billing/stripe/webhook", content=b"failed").status_code == 204
        assert client.post("/billing/stripe/webhook", content=b"subscription").status_code == 204
        with SessionLocal() as db:
            payments = list(
                db.scalars(
                    select(PaymentReference)
                    .where(PaymentReference.external_reference.in_([paid_invoice, failed_invoice]))
                    .order_by(PaymentReference.external_reference)
                )
            )
            assert {payment.status for payment in payments} == {
                PaymentStatus.succeeded,
                PaymentStatus.failed,
            }
            assert all(payment.amount_cents == 1299 for payment in payments)
            subscription = db.scalar(
                select(Subscription).where(
                    Subscription.provider_subscription_ref == subscription_ref
                )
            )
            assert subscription.status == SubscriptionStatus.past_due
    finally:
        client.close()
        with SessionLocal() as db:
            db.execute(delete(User).where(User.email == email))
            db.commit()
