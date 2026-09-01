"""Bounded scheduled production maintenance."""

import json

from app.analytics_service import purge_expired_events
from app.config import get_settings
from app.db import SessionLocal
from app.platform_marketplace_service import reconcile_expired_rental_intents
from app.platform_verification_service import (
    reconcile_stale_platform_verification_deliveries,
)
from app.scheduling import synchronize_due_schedules


def run_maintenance(*, max_cleanup_batches: int = 20) -> dict[str, int]:
    purged = 0
    batches = 0
    platform_rental_intents_expired = 0
    platform_verification_deliveries_failed = 0
    with SessionLocal() as db:
        synchronize_due_schedules(db)
        if get_settings().platform_control_plane_enabled:
            platform_rental_intents_expired = reconcile_expired_rental_intents(
                db,
                limit=100,
            )
            platform_verification_deliveries_failed = (
                reconcile_stale_platform_verification_deliveries(
                    db,
                    limit=100,
                )
            )
            db.commit()
        while batches < max_cleanup_batches:
            removed = purge_expired_events(db)
            purged += removed
            batches += 1
            db.commit()
            if removed < 500:
                break
    return {
        "catalog_schedule_syncs": 1,
        "platform_rental_intents_expired": platform_rental_intents_expired,
        "platform_verification_deliveries_failed": platform_verification_deliveries_failed,
        "analytics_events_purged": purged,
        "batches": batches,
    }


def main() -> None:
    result = run_maintenance()
    print(json.dumps({"event": "maintenance.completed", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
