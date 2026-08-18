from datetime import UTC, datetime

import stripe
from fastapi import APIRouter, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.config import get_settings
from app.db import SessionLocal
from app.models import (
    BillingWebhookEvent,
    Entitlement,
    PaymentReference,
    PaymentStatus,
    Plan,
    Subscription,
    SubscriptionStatus,
    User,
)

router = APIRouter(prefix="/billing", tags=["billing"])
STATUS_MAP = {
    "incomplete": SubscriptionStatus.incomplete,
    "incomplete_expired": SubscriptionStatus.expired,
    "trialing": SubscriptionStatus.trialing,
    "active": SubscriptionStatus.active,
    "past_due": SubscriptionStatus.past_due,
    "canceled": SubscriptionStatus.canceled,
    "unpaid": SubscriptionStatus.expired,
    "paused": SubscriptionStatus.past_due,
}


def timestamp(value: int | None) -> datetime | None:
    return datetime.fromtimestamp(value, UTC) if value else None


def reconcile_subscription(db, payload: dict) -> None:
    metadata = payload.get("metadata") or {}
    user_id = metadata.get("user_id")
    plan_code = metadata.get("plan_code")
    if not user_id or not plan_code or payload.get("status") not in STATUS_MAP:
        raise ValueError("subscription_metadata_or_status_invalid")
    user = db.get(User, user_id)
    plan = db.scalar(select(Plan).where(Plan.code == plan_code, Plan.is_active.is_(True)))
    if user is None or plan is None:
        raise ValueError("subscription_owner_or_plan_missing")
    subscription = db.scalar(
        select(Subscription).where(Subscription.provider_subscription_ref == payload["id"])
    )
    if subscription is None:
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            provider="stripe",
            provider_subscription_ref=payload["id"],
            status=STATUS_MAP[payload["status"]],
        )
        db.add(subscription)
        db.flush()
    elif subscription.user_id != user.id or subscription.provider != "stripe":
        raise ValueError("subscription_owner_or_provider_mismatch")
    elif (
        subscription.provider_customer_ref
        and payload.get("customer") != subscription.provider_customer_ref
    ):
        raise ValueError("subscription_customer_mismatch")
    subscription.plan_id = plan.id
    subscription.status = STATUS_MAP[payload["status"]]
    subscription.provider_customer_ref = payload.get("customer")
    subscription.current_period_start = timestamp(payload.get("current_period_start"))
    subscription.current_period_end = timestamp(payload.get("current_period_end"))
    subscription.cancel_at_period_end = bool(payload.get("cancel_at_period_end", False))
    subscription.canceled_at = timestamp(payload.get("canceled_at"))
    db.execute(
        delete(Entitlement).where(
            Entitlement.subscription_id == subscription.id,
            Entitlement.source == "stripe",
        )
    )
    if subscription.status in {SubscriptionStatus.trialing, SubscriptionStatus.active}:
        db.add_all(
            [
                Entitlement(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    key="simultaneous_streams",
                    value={"limit": plan.max_streams},
                    source="stripe",
                    starts_at=subscription.current_period_start,
                    ends_at=subscription.current_period_end,
                ),
                Entitlement(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    key="max_resolution",
                    value={"value": plan.max_resolution},
                    source="stripe",
                    starts_at=subscription.current_period_start,
                    ends_at=subscription.current_period_end,
                ),
            ]
        )


def invoice_subscription_reference(payload: dict) -> str | None:
    reference = payload.get("subscription")
    if isinstance(reference, str):
        return reference
    parent = payload.get("parent") or {}
    details = parent.get("subscription_details") or {}
    nested = details.get("subscription")
    return nested if isinstance(nested, str) else None


def reconcile_invoice(db, payload: dict) -> None:
    subscription_ref = invoice_subscription_reference(payload)
    subscription = db.scalar(
        select(Subscription).where(Subscription.provider_subscription_ref == subscription_ref)
    )
    if subscription is None:
        raise ValueError("invoice_subscription_missing")
    payment_status = (
        PaymentStatus.succeeded if payload.get("status") == "paid" else PaymentStatus.failed
    )
    payment = db.scalar(
        select(PaymentReference).where(PaymentReference.external_reference == payload["id"])
    )
    if payment is None:
        payment = PaymentReference(
            subscription_id=subscription.id,
            provider="stripe",
            external_reference=payload["id"],
            status=payment_status,
            amount_cents=0,
            currency=str(payload.get("currency") or subscription.plan.currency).upper(),
            occurred_at=timestamp(payload.get("status_transitions", {}).get("paid_at"))
            or datetime.now(UTC),
        )
        db.add(payment)
    payment.status = payment_status
    payment.amount_cents = int(
        payload.get("amount_paid" if payment_status == PaymentStatus.succeeded else "amount_due")
        or 0
    )


@router.post("/stripe/webhook", status_code=status.HTTP_204_NO_CONTENT)
async def stripe_webhook(request: Request) -> None:
    settings = get_settings()
    if settings.billing_provider != "stripe" or not settings.stripe_webhook_secret:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe billing is unavailable")
    body = await request.body()
    try:
        event = stripe.Webhook.construct_event(
            body, request.headers.get("stripe-signature", ""), settings.stripe_webhook_secret
        )
    except (ValueError, stripe.SignatureVerificationError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid Stripe webhook") from exc
    event_id = event["id"]
    event_type = event["type"]
    with SessionLocal() as db:
        if db.scalar(
            select(BillingWebhookEvent).where(BillingWebhookEvent.external_event_id == event_id)
        ):
            return
        try:
            if event_type.startswith("customer.subscription."):
                current = stripe.Subscription.retrieve(
                    event["data"]["object"]["id"], api_key=settings.stripe_secret_key
                )
                reconcile_subscription(db, dict(current))
            elif event_type in {"invoice.paid", "invoice.payment_failed"}:
                current = stripe.Invoice.retrieve(
                    event["data"]["object"]["id"], api_key=settings.stripe_secret_key
                )
                reconcile_invoice(db, dict(current))
            db.add(
                BillingWebhookEvent(
                    provider="stripe", external_event_id=event_id, event_type=event_type
                )
            )
            db.commit()
        except IntegrityError:
            db.rollback()  # a concurrent delivery already won the idempotency race
        except ValueError as exc:
            db.rollback()
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except stripe.StripeError as exc:
            db.rollback()
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "Stripe reconciliation is temporarily unavailable",
            ) from exc
