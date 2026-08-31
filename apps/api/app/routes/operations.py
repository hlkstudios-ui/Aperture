import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

import redis
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.config import get_settings
from app.models import (
    Admin,
    AnalyticsEvent,
    AnalyticsEventType,
    MediaAsset,
    ProcessingJob,
    ProcessingState,
)
from app.object_storage import s3_client
from app.observability import metrics
from app.processing_queue import PROCESSING_QUEUE
from app.scene_models import SceneIntelligenceJob
from app.scene_queue import SCENE_QUEUE

router = APIRouter(tags=["operations"])
admin_router = APIRouter(
    prefix="/admin/operations",
    tags=["administrator operations"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def metric_key(name: str, **labels: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    return name, tuple(sorted(labels.items()))


def operational_snapshot(db: DbSession) -> tuple[dict, dict]:
    settings = get_settings()
    media_states = dict(
        db.execute(select(MediaAsset.state, func.count()).group_by(MediaAsset.state)).all()
    )
    processing_states = dict(
        db.execute(select(ProcessingJob.state, func.count()).group_by(ProcessingJob.state)).all()
    )
    scene_states = dict(
        db.execute(
            select(SceneIntelligenceJob.state, func.count()).group_by(SceneIntelligenceJob.state)
        ).all()
    )
    registered_bytes = db.scalar(select(func.coalesce(func.sum(MediaAsset.size_bytes), 0))) or 0
    average_transcode_seconds = db.scalar(
        select(
            func.avg(func.extract("epoch", ProcessingJob.completed_at - ProcessingJob.started_at))
        ).where(
            ProcessingJob.state == ProcessingState.ready,
            ProcessingJob.started_at.is_not(None),
            ProcessingJob.completed_at.is_not(None),
        )
    )
    since = datetime.now(UTC) - timedelta(hours=1)
    recent_failures = (
        db.scalar(
            select(func.count())
            .select_from(ProcessingJob)
            .where(
                ProcessingJob.state == ProcessingState.failed,
                ProcessingJob.completed_at >= since,
            )
        )
        or 0
    )
    playback_since = datetime.now(UTC) - timedelta(minutes=5)
    playback_counts = dict(
        db.execute(
            select(AnalyticsEvent.event_type, func.count())
            .where(
                AnalyticsEvent.occurred_at >= playback_since,
                AnalyticsEvent.event_type.in_(
                    (
                        AnalyticsEventType.play_start,
                        AnalyticsEventType.playback_buffer,
                        AnalyticsEventType.playback_error,
                    )
                ),
                AnalyticsEvent.is_bot.is_(False),
                AnalyticsEvent.is_internal.is_(False),
            )
            .group_by(AnalyticsEvent.event_type)
        ).all()
    )
    oldest_queued = db.scalar(
        select(func.min(ProcessingJob.created_at)).where(
            ProcessingJob.state == ProcessingState.queued
        )
    )
    oldest_age = max(0, (datetime.now(UTC) - oldest_queued).total_seconds()) if oldest_queued else 0
    redis_client = redis.from_url(
        settings.redis_url,
        socket_connect_timeout=1,
        socket_timeout=1,
        retry_on_timeout=False,
    )
    try:
        media_backlog = redis_client.llen(PROCESSING_QUEUE)
        scene_backlog = redis_client.llen(SCENE_QUEUE)
    finally:
        redis_client.close()
    storage_available = True
    try:
        s3_client().head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        storage_available = False

    values: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {
        metric_key("aperture_queue_backlog", queue="media"): media_backlog,
        metric_key("aperture_queue_backlog", queue="scene"): scene_backlog,
        metric_key("aperture_processing_oldest_queued_seconds"): oldest_age,
        metric_key("aperture_processing_failures_last_hour"): recent_failures,
        metric_key("aperture_transcode_duration_seconds_average"): float(
            average_transcode_seconds or 0
        ),
        metric_key("aperture_storage_registered_bytes"): registered_bytes,
        metric_key("aperture_storage_available"): 1 if storage_available else 0,
        metric_key("aperture_playback_starts_last_5m"): playback_counts.get(
            AnalyticsEventType.play_start, 0
        ),
        metric_key("aperture_playback_buffers_last_5m"): playback_counts.get(
            AnalyticsEventType.playback_buffer, 0
        ),
        metric_key("aperture_playback_errors_last_5m"): playback_counts.get(
            AnalyticsEventType.playback_error, 0
        ),
    }
    for state, count in media_states.items():
        values[metric_key("aperture_media_assets", state=state.value)] = count
    for state, count in processing_states.items():
        values[metric_key("aperture_processing_jobs", state=state.value)] = count
    for state, count in scene_states.items():
        values[metric_key("aperture_scene_jobs", state=state.value)] = count

    alerts = []
    if media_backlog >= settings.queue_backlog_alert_threshold:
        alerts.append({"code": "media_queue_backlog", "severity": "warning"})
    if scene_backlog >= settings.queue_backlog_alert_threshold:
        alerts.append({"code": "scene_queue_backlog", "severity": "warning"})
    if oldest_age >= settings.queued_job_age_alert_seconds:
        alerts.append({"code": "queued_job_stale", "severity": "critical"})
    if recent_failures >= settings.processing_failure_alert_threshold:
        alerts.append({"code": "processing_failures", "severity": "critical"})
    if not storage_available:
        alerts.append({"code": "storage_unavailable", "severity": "critical"})
    snapshot = {
        "status": "alerting" if alerts else "healthy",
        "queues": {"media": media_backlog, "scene": scene_backlog},
        "storage": {"available": storage_available, "registered_bytes": registered_bytes},
        "processing": {
            "states": {state.value: count for state, count in processing_states.items()},
            "oldest_queued_seconds": round(oldest_age, 3),
            "failures_last_hour": recent_failures,
            "average_transcode_seconds": round(float(average_transcode_seconds or 0), 3),
        },
        "scene_jobs": {state.value: count for state, count in scene_states.items()},
        "alerts": alerts,
    }
    return snapshot, values


@router.get("/metrics", include_in_schema=False, response_class=PlainTextResponse)
def prometheus_metrics(
    db: DbSession, authorization: Annotated[str | None, Header()] = None
) -> PlainTextResponse:
    expected = f"Bearer {get_settings().metrics_bearer_token}"
    if authorization is None or not secrets.compare_digest(authorization, expected):
        raise HTTPException(401, "Metrics authentication required")
    _, operational = operational_snapshot(db)
    return PlainTextResponse(metrics.render(operational), media_type="text/plain; version=0.0.4")


@admin_router.get("/observability")
def observability(db: DbSession, _: AdminIdentity) -> dict:
    snapshot, _ = operational_snapshot(db)
    return snapshot
