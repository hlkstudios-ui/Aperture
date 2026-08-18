import math
import re
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from app.analytics_schemas import AnalyticsEventCreate
from app.catalog_models import Episode, Movie
from app.config import get_settings
from app.models import (
    AggregatedMetric,
    AnalyticsEvent,
    AnalyticsEventType,
    DeviceSession,
)

BOT_PATTERN = re.compile(r"\b(bot|crawler|spider|slurp|bingpreview)\b", re.IGNORECASE)


def nullable_id(column, value: uuid.UUID | None) -> ColumnElement[bool]:
    return column.is_(None) if value is None else column == value


def title_dimension(event: AnalyticsEventCreate) -> tuple[uuid.UUID | None, uuid.UUID | None]:
    return event.movie_id, event.episode_id


def event_dedupe_key(
    profile_id: uuid.UUID, session_id: uuid.UUID, event: AnalyticsEventCreate
) -> str:
    if event.event_type == AnalyticsEventType.progress:
        title_id = event.movie_id or event.episode_id
        bucket = math.floor((event.position_seconds or 0) / 30)
        return f"progress:{profile_id}:{title_id}:{bucket}"
    return f"event:{session_id}:{event.client_event_id}"


def validate_title(db: Session, event: AnalyticsEventCreate) -> None:
    if event.movie_id and db.get(Movie, event.movie_id) is None:
        raise ValueError("Movie analytics target was not found")
    if event.episode_id and db.get(Episode, event.episode_id) is None:
        raise ValueError("Episode analytics target was not found")


def store_event(
    db: Session,
    session: DeviceSession,
    event: AnalyticsEventCreate,
) -> AnalyticsEvent | None:
    validate_title(db, event)
    record = AnalyticsEvent(
        profile_id=session.active_profile_id,
        device_session_id=session.id,
        client_event_id=event.client_event_id,
        dedupe_key=event_dedupe_key(session.active_profile_id, session.id, event),
        event_type=event.event_type,
        movie_id=event.movie_id,
        episode_id=event.episode_id,
        position_seconds=event.position_seconds,
        duration_seconds=event.duration_seconds,
        query=event.query,
        result_count=event.result_count,
        value=event.value,
        properties=event.properties,
        is_bot=bool(BOT_PATTERN.search(session.user_agent or "")),
        is_internal=False,
        occurred_at=event.occurred_at.astimezone(UTC),
    )
    try:
        with db.begin_nested():
            db.add(record)
            db.flush()
    except IntegrityError:
        return None
    return record


def recompute_metric(
    db: Session,
    day: date,
    event_type: AnalyticsEventType,
    movie_id: uuid.UUID | None,
    episode_id: uuid.UUID | None,
) -> None:
    filters = (
        func.date(func.timezone("UTC", AnalyticsEvent.occurred_at)) == day,
        AnalyticsEvent.event_type == event_type,
        nullable_id(AnalyticsEvent.movie_id, movie_id),
        nullable_id(AnalyticsEvent.episode_id, episode_id),
        AnalyticsEvent.is_bot.is_(False),
        AnalyticsEvent.is_internal.is_(False),
    )
    values = db.execute(
        select(
            func.count(AnalyticsEvent.id),
            func.count(func.distinct(AnalyticsEvent.profile_id)),
            func.coalesce(func.sum(AnalyticsEvent.value), 0.0),
        ).where(*filters)
    ).one()
    metric = db.scalar(
        select(AggregatedMetric).where(
            AggregatedMetric.day == day,
            AggregatedMetric.event_type == event_type,
            nullable_id(AggregatedMetric.movie_id, movie_id),
            nullable_id(AggregatedMetric.episode_id, episode_id),
        )
    )
    if metric is None:
        metric = AggregatedMetric(
            day=day, event_type=event_type, movie_id=movie_id, episode_id=episode_id
        )
        db.add(metric)
    metric.event_count = values[0]
    metric.unique_profiles = values[1]
    metric.total_value = float(values[2])


def event_title_label(db: Session, event: AnalyticsEvent) -> str | None:
    if event.movie_id:
        movie = db.get(Movie, event.movie_id)
        return movie.title if movie else None
    if event.episode_id:
        episode = db.get(Episode, event.episode_id)
        return episode.title if episode else None
    return None


def purge_expired_events(db: Session, *, limit: int = 500) -> int:
    """Bound cleanup work while retaining anonymous daily aggregates."""
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().analytics_retention_days)
    expired_ids = select(AnalyticsEvent.id).where(AnalyticsEvent.received_at < cutoff).limit(limit)
    return db.execute(delete(AnalyticsEvent).where(AnalyticsEvent.id.in_(expired_ids))).rowcount
