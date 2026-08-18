from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.analytics_schemas import AnalyticsBatchCreate, AnalyticsIngestResponse
from app.analytics_service import (
    purge_expired_events,
    recompute_metric,
    store_event,
    title_dimension,
)
from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.models import DeviceSession, ProfilePreference
from app.rate_limit import enforce_rate_limit

router = APIRouter(
    prefix="/analytics",
    tags=["customer analytics"],
    dependencies=[Depends(require_trusted_origin)],
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


@router.post(
    "/events", response_model=AnalyticsIngestResponse, status_code=status.HTTP_202_ACCEPTED
)
async def ingest(
    payload: AnalyticsBatchCreate,
    request: Request,
    db: DbSession,
    session: CurrentSession,
) -> AnalyticsIngestResponse:
    if session.active_profile_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Select a profile before recording events")
    preference = db.get(ProfilePreference, session.active_profile_id)
    if preference is None or not preference.analytics_enabled:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Optional analytics are disabled")
    await enforce_rate_limit(
        f"analytics:{session.active_profile_id}",
        limit=240,
        window_seconds=60,
        weight=len(payload.events),
    )
    accepted = []
    try:
        for event in payload.events:
            record = store_event(db, session, event)
            if record is not None:
                accepted.append((record, title_dimension(event)))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    for record, (movie_id, episode_id) in accepted:
        recompute_metric(
            db,
            record.occurred_at.astimezone(UTC).date(),
            record.event_type,
            movie_id,
            episode_id,
        )
    purge_expired_events(db)
    session.last_seen_at = datetime.now(UTC)
    db.commit()
    return AnalyticsIngestResponse(
        accepted=len(accepted),
        duplicate_or_coalesced=len(payload.events) - len(accepted),
    )
