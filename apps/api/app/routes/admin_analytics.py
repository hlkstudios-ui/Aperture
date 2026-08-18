import uuid
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.analytics_schemas import (
    AnalyticsSummaryResponse,
    PlaybackQualityResponse,
    RecentEventResponse,
    TitleAnalyticsResponse,
)
from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Episode, Movie
from app.config import get_settings
from app.models import Admin, AggregatedMetric, AnalyticsEvent, AnalyticsEventType

router = APIRouter(
    prefix="/admin/analytics",
    tags=["administrator analytics"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


@router.get("/summary", response_model=AnalyticsSummaryResponse)
def summary(
    db: DbSession,
    _: AdminIdentity,
    days: int = Query(default=30, ge=1, le=90),
) -> AnalyticsSummaryResponse:
    since = datetime.now(UTC) - timedelta(days=days)
    metrics = list(
        db.scalars(
            select(AggregatedMetric)
            .where(AggregatedMetric.day >= since.date())
            .order_by(AggregatedMetric.day.desc(), AggregatedMetric.event_type)
        )
    )
    totals: dict[str, int] = {}
    for metric in metrics:
        totals[metric.event_type.value] = (
            totals.get(metric.event_type.value, 0) + metric.event_count
        )
    unique_viewers = (
        db.scalar(
            select(func.count(func.distinct(AnalyticsEvent.profile_id))).where(
                AnalyticsEvent.occurred_at >= since,
                AnalyticsEvent.is_bot.is_(False),
                AnalyticsEvent.is_internal.is_(False),
            )
        )
        or 0
    )
    watch_seconds = sum(
        metric.total_value for metric in metrics if metric.event_type == AnalyticsEventType.progress
    )
    plays = totals.get(AnalyticsEventType.play_start.value, 0)
    completions = totals.get(AnalyticsEventType.completion.value, 0)
    startup_samples = totals.get(AnalyticsEventType.playback_startup.value, 0)
    startup_total = sum(
        metric.total_value
        for metric in metrics
        if metric.event_type == AnalyticsEventType.playback_startup
    )
    buffer_events = totals.get(AnalyticsEventType.playback_buffer.value, 0)
    buffer_seconds = sum(
        metric.total_value
        for metric in metrics
        if metric.event_type == AnalyticsEventType.playback_buffer
    )
    fatal_errors = totals.get(AnalyticsEventType.playback_error.value, 0)
    recent = list(
        db.scalars(
            select(AnalyticsEvent)
            .where(AnalyticsEvent.occurred_at >= since)
            .order_by(AnalyticsEvent.occurred_at.desc())
            .limit(50)
        )
    )
    movie_ids = {item.movie_id for item in [*metrics, *recent] if item.movie_id is not None}
    episode_ids = {item.episode_id for item in [*metrics, *recent] if item.episode_id is not None}
    movie_titles = {
        item.id: item.title for item in db.scalars(select(Movie).where(Movie.id.in_(movie_ids)))
    }
    episode_titles = {
        item.id: item.title
        for item in db.scalars(select(Episode).where(Episode.id.in_(episode_ids)))
    }

    def title_label(movie_id: uuid.UUID | None, episode_id: uuid.UUID | None) -> str | None:
        if movie_id is not None:
            return movie_titles.get(movie_id)
        if episode_id is not None:
            return episode_titles.get(episode_id)
        return None

    title_rows: dict[tuple, dict] = {}
    for metric in metrics:
        if metric.movie_id is None and metric.episode_id is None:
            continue
        key = (metric.movie_id, metric.episode_id)
        row = title_rows.setdefault(key, {"plays": 0, "completions": 0, "seconds": 0.0})
        if metric.event_type == AnalyticsEventType.play_start:
            row["plays"] += metric.event_count
        elif metric.event_type == AnalyticsEventType.completion:
            row["completions"] += metric.event_count
        elif metric.event_type == AnalyticsEventType.progress:
            row["seconds"] += metric.total_value
    titles = []
    for (movie_id, episode_id), values in title_rows.items():
        titles.append(
            TitleAnalyticsResponse(
                title_label=title_label(movie_id, episode_id) or "Deleted title",
                movie_id=movie_id,
                episode_id=episode_id,
                plays=values["plays"],
                completions=values["completions"],
                watch_hours=round(values["seconds"] / 3600, 3),
            )
        )
    titles.sort(key=lambda item: (item.plays, item.watch_hours), reverse=True)
    return AnalyticsSummaryResponse(
        retention_days=get_settings().analytics_retention_days,
        totals=totals,
        unique_viewers=unique_viewers,
        watch_hours=round(watch_seconds / 3600, 3),
        completion_rate=round(completions / plays * 100, 1) if plays else 0,
        playback_quality=PlaybackQualityResponse(
            startup_samples=startup_samples,
            average_startup_ms=(
                round(startup_total / startup_samples, 1) if startup_samples else 0
            ),
            buffer_events=buffer_events,
            buffer_seconds=round(buffer_seconds, 3),
            fatal_errors=fatal_errors,
            error_rate_percent=round(fatal_errors / plays * 100, 2) if plays else 0,
            quality_changes=totals.get(AnalyticsEventType.quality_change.value, 0),
        ),
        daily=metrics,
        recent=[
            RecentEventResponse(
                id=event.id,
                event_type=event.event_type,
                title_label=title_label(event.movie_id, event.episode_id),
                profile_id=event.profile_id,
                position_seconds=event.position_seconds,
                duration_seconds=event.duration_seconds,
                query=event.query,
                result_count=event.result_count,
                is_bot=event.is_bot,
                is_internal=event.is_internal,
                occurred_at=event.occurred_at,
            )
            for event in recent
        ],
        titles=titles[:20],
    )
