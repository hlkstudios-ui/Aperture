"""Provision subscription state for an isolated browser-test customer."""

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta

from e2e_guard import require_e2e_test_environment
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Entitlement, Plan, Subscription, SubscriptionStatus, User


def main() -> None:
    require_e2e_test_environment()
    payload = json.load(sys.stdin)
    email = payload["email"].lower()
    if not email.endswith("@example.com"):
        raise SystemExit("E2E customer email must use example.com")
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email))
        plan = db.scalar(select(Plan).where(Plan.code == "cinephile-monthly"))
        if user is None or plan is None:
            raise SystemExit("E2E customer or seeded plan was not found")
        now = datetime.now(UTC)
        subscription = Subscription(
            user_id=user.id,
            plan_id=plan.id,
            status=SubscriptionStatus.active,
            provider="staging_acceptance",
            provider_customer_ref=f"e2e-customer-{uuid.uuid4()}",
            provider_subscription_ref=f"e2e-subscription-{uuid.uuid4()}",
            current_period_start=now,
            current_period_end=now + timedelta(days=30),
        )
        db.add(subscription)
        db.flush()
        db.add_all(
            [
                Entitlement(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    key="simultaneous_streams",
                    value={"limit": plan.max_streams},
                    source="staging_acceptance",
                ),
                Entitlement(
                    user_id=user.id,
                    subscription_id=subscription.id,
                    key="video_quality",
                    value={"max_resolution": plan.max_resolution},
                    source="staging_acceptance",
                ),
            ]
        )
        db.commit()


if __name__ == "__main__":
    main()
