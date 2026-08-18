import json
import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.config import get_settings
from app.models import AnalyticsEventType

TITLE_EVENTS = {
    AnalyticsEventType.detail_open,
    AnalyticsEventType.play_start,
    AnalyticsEventType.progress,
    AnalyticsEventType.pause,
    AnalyticsEventType.seek,
    AnalyticsEventType.completion,
    AnalyticsEventType.search_click,
    AnalyticsEventType.my_list,
    AnalyticsEventType.rating,
    AnalyticsEventType.scenelens_open,
    AnalyticsEventType.ask_movie,
    AnalyticsEventType.playback_startup,
    AnalyticsEventType.playback_buffer,
    AnalyticsEventType.playback_error,
    AnalyticsEventType.quality_change,
}
PLAYBACK_EVENTS = {
    AnalyticsEventType.play_start,
    AnalyticsEventType.progress,
    AnalyticsEventType.pause,
    AnalyticsEventType.seek,
    AnalyticsEventType.completion,
    AnalyticsEventType.playback_startup,
    AnalyticsEventType.playback_buffer,
    AnalyticsEventType.playback_error,
    AnalyticsEventType.quality_change,
}
ALLOWED_PROPERTIES = {
    "quality_height",
    "playback_rate",
    "buffered_seconds",
    "error_code",
    "source",
    "surface",
    "action",
    "rating",
    "query_mode",
}


class AnalyticsEventCreate(BaseModel):
    client_event_id: uuid.UUID
    event_type: AnalyticsEventType
    movie_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    position_seconds: float | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, gt=0)
    query: str | None = Field(default=None, min_length=1, max_length=200)
    result_count: int | None = Field(default=None, ge=0, le=10000)
    value: float | None = Field(default=None, ge=0, le=86400)
    properties: dict[str, Any] = Field(default_factory=dict)
    occurred_at: datetime

    @model_validator(mode="after")
    def validate_event(self):
        if (self.movie_id is not None) and (self.episode_id is not None):
            raise ValueError("Choose no more than one title")
        if self.event_type in TITLE_EVENTS and self.movie_id is None and self.episode_id is None:
            raise ValueError("This event requires a title")
        if self.event_type == AnalyticsEventType.search and (
            self.query is None or self.result_count is None
        ):
            raise ValueError("Search events require query and result count")
        if self.event_type in PLAYBACK_EVENTS and self.duration_seconds is None:
            raise ValueError("Playback events require duration")
        if self.event_type in PLAYBACK_EVENTS and self.position_seconds is None:
            raise ValueError("Playback events require position")
        if self.occurred_at.tzinfo is None:
            raise ValueError("Event timestamp must include a timezone")
        now = datetime.now(UTC)
        if self.occurred_at < now - timedelta(days=1) or self.occurred_at > now + timedelta(
            minutes=5
        ):
            raise ValueError("Event timestamp is outside the accepted window")
        if (
            len(self.properties) > 20
            or len(json.dumps(self.properties, separators=(",", ":"))) > 4096
        ):
            raise ValueError("Event properties exceed the bounded payload limit")
        if any(len(str(key)) > 64 for key in self.properties):
            raise ValueError("Event property keys must not exceed 64 characters")
        if set(self.properties) - ALLOWED_PROPERTIES:
            raise ValueError("Event properties contain unsupported keys")
        return self


class AnalyticsBatchCreate(BaseModel):
    events: list[AnalyticsEventCreate] = Field(min_length=1)

    @model_validator(mode="after")
    def bounded_batch(self):
        if len(self.events) > get_settings().analytics_max_batch_size:
            raise ValueError("Analytics batch exceeds the configured maximum")
        return self


class AnalyticsIngestResponse(BaseModel):
    accepted: int
    duplicate_or_coalesced: int


class DailyMetricResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    day: date
    event_type: AnalyticsEventType
    movie_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    event_count: int
    unique_profiles: int
    total_value: float


class RecentEventResponse(BaseModel):
    id: uuid.UUID
    event_type: AnalyticsEventType
    title_label: str | None
    profile_id: uuid.UUID
    position_seconds: float | None
    duration_seconds: float | None
    query: str | None
    result_count: int | None
    is_bot: bool
    is_internal: bool
    occurred_at: datetime


class AnalyticsSummaryResponse(BaseModel):
    retention_days: int
    totals: dict[str, int]
    unique_viewers: int
    watch_hours: float
    completion_rate: float
    playback_quality: "PlaybackQualityResponse"
    daily: list[DailyMetricResponse]
    recent: list[RecentEventResponse]
    titles: list["TitleAnalyticsResponse"]


class PlaybackQualityResponse(BaseModel):
    startup_samples: int
    average_startup_ms: float
    buffer_events: int
    buffer_seconds: float
    fatal_errors: int
    error_rate_percent: float
    quality_changes: int


class TitleAnalyticsResponse(BaseModel):
    title_label: str
    movie_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    plays: int
    completions: int
    watch_hours: float
