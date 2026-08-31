from datetime import UTC, datetime, timedelta
from typing import Annotated

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select

from app.admin_revenue_schemas import MoneyAmount, PayoutRequest, PayoutResponse, RevenueSnapshot
from app.auth import DbSession, require_admin, require_trusted_origin
from app.config import get_settings
from app.models import Admin, AuditLog, PaymentReference, PaymentStatus

router = APIRouter(
    prefix="/admin/revenue",
    tags=["administrator revenue"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def recorded_receipts(db: DbSession, since: datetime | None = None) -> list[MoneyAmount]:
    query = select(PaymentReference.currency, func.sum(PaymentReference.amount_cents)).where(
        PaymentReference.status == PaymentStatus.succeeded
    )
    if since is not None:
        query = query.where(PaymentReference.occurred_at >= since)
    rows = db.execute(query.group_by(PaymentReference.currency)).all()
    return [
        MoneyAmount(amount=int(amount or 0), currency=currency.lower()) for currency, amount in rows
    ]


def stripe_money(items) -> list[MoneyAmount]:
    return [
        MoneyAmount(amount=int(item.amount), currency=str(item.currency).lower()) for item in items
    ]


@router.get("", response_model=RevenueSnapshot)
def revenue_snapshot(db: DbSession, _: AdminIdentity) -> RevenueSnapshot:
    settings = get_settings()
    all_time = recorded_receipts(db)
    last_30_days = recorded_receipts(db, datetime.now(UTC) - timedelta(days=30))
    if settings.billing_provider != "stripe" or not settings.stripe_secret_key:
        return RevenueSnapshot(
            provider=settings.billing_provider,
            connection="not_configured",
            livemode=None,
            payouts_enabled=False,
            recorded_receipts=all_time,
            recorded_receipts_30d=last_30_days,
            available=[],
            pending=[],
            recent_payouts=[],
            notice="Add Stripe credentials and enable Stripe billing to load live balances.",
        )
    try:
        balance = stripe.Balance.retrieve(api_key=settings.stripe_secret_key)
        payouts = stripe.Payout.list(limit=5, api_key=settings.stripe_secret_key)
    except stripe.StripeError:
        return RevenueSnapshot(
            provider="stripe",
            connection="unavailable",
            livemode=None,
            payouts_enabled=False,
            recorded_receipts=all_time,
            recorded_receipts_30d=last_30_days,
            available=[],
            pending=[],
            recent_payouts=[],
            notice="Stripe could not be reached or authenticated. No payout action is available.",
        )
    recent = [
        {
            "id": item.id,
            "amount": int(item.amount),
            "currency": str(item.currency).lower(),
            "status": item.status,
            "arrival_date": datetime.fromtimestamp(item.arrival_date, UTC),
            "created": datetime.fromtimestamp(item.created, UTC),
        }
        for item in payouts.data
    ]
    return RevenueSnapshot(
        provider="stripe",
        connection="connected",
        livemode=bool(balance.livemode),
        payouts_enabled=settings.stripe_payouts_enabled,
        recorded_receipts=all_time,
        recorded_receipts_30d=last_30_days,
        available=stripe_money(balance.available),
        pending=stripe_money(balance.pending),
        recent_payouts=recent,
        notice=None
        if settings.stripe_payouts_enabled
        else "Balances are read-only until STRIPE_PAYOUTS_ENABLED=true.",
    )


@router.post("/payouts", response_model=PayoutResponse, status_code=status.HTTP_201_CREATED)
def create_payout(payload: PayoutRequest, request: Request, db: DbSession, admin: AdminIdentity):
    settings = get_settings()
    if settings.billing_provider != "stripe" or not settings.stripe_secret_key:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe is not configured")
    if not settings.stripe_payouts_enabled:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Stripe payouts are disabled")
    if payload.confirmation != "CREATE PAYOUT":
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirmation phrase is incorrect")
    try:
        balance = stripe.Balance.retrieve(api_key=settings.stripe_secret_key)
        available = next(
            (
                int(item.amount)
                for item in balance.available
                if str(item.currency).lower() == payload.currency
            ),
            0,
        )
        if payload.amount > available:
            raise HTTPException(
                status.HTTP_409_CONFLICT, "Payout exceeds the available Stripe balance"
            )
        payout = stripe.Payout.create(
            amount=payload.amount,
            currency=payload.currency,
            description="Aperture Studio payout",
            metadata={"admin_id": str(admin.id), "request_id": str(payload.request_id)},
            api_key=settings.stripe_secret_key,
            idempotency_key=f"studio-payout-{payload.request_id}",
        )
    except HTTPException:
        raise
    except stripe.StripeError as exc:
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, "Stripe could not create the payout"
        ) from exc
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action="revenue.payout.created",
            outcome="success",
            ip_address=request.client.host if request.client else None,
            detail={
                "payout_id": payout.id,
                "amount": int(payout.amount),
                "currency": payout.currency,
                "livemode": bool(payout.livemode),
                "request_id": str(payload.request_id),
            },
        )
    )
    db.commit()
    arrival = datetime.fromtimestamp(payout.arrival_date, UTC) if payout.arrival_date else None
    return PayoutResponse(
        id=payout.id,
        amount=int(payout.amount),
        currency=payout.currency,
        status=payout.status,
        arrival_date=arrival,
        livemode=bool(payout.livemode),
    )
