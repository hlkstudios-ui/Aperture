"""Inspect privacy state for an isolated browser-test customer."""

import json
import sys

from e2e_guard import require_e2e_test_environment
from sqlalchemy import func, select

from app.db import SessionLocal
from app.models import AnalyticsEvent, Profile, ProfilePreference, User


def main() -> None:
    require_e2e_test_environment()
    email = str(json.load(sys.stdin)["email"]).strip().lower()
    if not email.endswith("@example.com"):
        raise SystemExit("E2E customer email must use example.com")
    with SessionLocal() as db:
        row = db.execute(
            select(Profile.id, ProfilePreference)
            .join(User, User.id == Profile.user_id)
            .join(ProfilePreference, ProfilePreference.profile_id == Profile.id)
            .where(User.email == email)
        ).first()
        if row is None:
            raise SystemExit("E2E customer was not found")
        profile_id, preference = row
        raw_events = db.scalar(
            select(func.count(AnalyticsEvent.id)).where(
                AnalyticsEvent.profile_id == profile_id
            )
        )
        print(
            json.dumps(
                {
                    "analytics_enabled": preference.analytics_enabled,
                    "consent_updated_at": preference.consent_updated_at.isoformat()
                    if preference.consent_updated_at
                    else None,
                    "homepage_mode": preference.homepage_mode,
                    "raw_events": raw_events,
                }
            )
        )


if __name__ == "__main__":
    main()
