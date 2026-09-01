"""Recovery for interrupted platform email-verification delivery attempts."""

from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.platform_models import (
    PlatformAuditEvent,
    PlatformEmailVerificationToken,
)


def reconcile_stale_platform_verification_deliveries(
    db: Session,
    *,
    limit: int = 100,
) -> int:
    """Terminalize pending deliveries whose worker lease was abandoned."""
    if not 1 <= limit <= 500:
        raise ValueError("Verification delivery reconciliation limit must be between 1 and 500")

    observed_at = db.scalar(select(func.transaction_timestamp()))
    if not isinstance(observed_at, datetime):
        raise RuntimeError("Database clock is unavailable")
    stale_before = observed_at - timedelta(
        seconds=get_settings().platform_email_delivery_lease_seconds
    )
    deliveries = list(
        db.scalars(
            select(PlatformEmailVerificationToken)
            .where(
                PlatformEmailVerificationToken.state == "pending_delivery",
                PlatformEmailVerificationToken.created_at <= stale_before,
            )
            .order_by(
                PlatformEmailVerificationToken.created_at,
                PlatformEmailVerificationToken.id,
            )
            .limit(limit)
            .with_for_update(
                of=PlatformEmailVerificationToken,
                skip_locked=True,
            )
        )
    )
    for delivery in deliveries:
        delivery.state = "delivery_failed"
        delivery.used_at = observed_at
        db.add(
            PlatformAuditEvent(
                actor_type="system",
                actor_account_id=None,
                action="platform_account.email_verification_delivery",
                outcome="failed",
                resource_type="platform_account",
                resource_id=delivery.account_id,
                detail={
                    "schema_version": 1,
                    "reason": "delivery_lease_expired",
                },
            )
        )
    return len(deliveries)
