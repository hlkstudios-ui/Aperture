"""Bounded scheduled production maintenance."""

import json

from app.analytics_service import purge_expired_events
from app.db import SessionLocal
from app.scheduling import synchronize_due_schedules


def run_maintenance(*, max_cleanup_batches: int = 20) -> dict[str, int]:
    purged = 0
    batches = 0
    with SessionLocal() as db:
        synchronize_due_schedules(db)
        while batches < max_cleanup_batches:
            removed = purge_expired_events(db)
            purged += removed
            batches += 1
            db.commit()
            if removed < 500:
                break
    return {"catalog_schedule_syncs": 1, "analytics_events_purged": purged, "batches": batches}


def main() -> None:
    result = run_maintenance()
    print(json.dumps({"event": "maintenance.completed", **result}, sort_keys=True))


if __name__ == "__main__":
    main()
