import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PlaybackSourceCreate(BaseModel):
    processing_job_id: uuid.UUID
    movie_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    edition_id: uuid.UUID | None = None
    intro_start_seconds: float | None = Field(default=None, ge=0)
    intro_end_seconds: float | None = Field(default=None, gt=0)
    recap_start_seconds: float | None = Field(default=None, ge=0)
    recap_end_seconds: float | None = Field(default=None, gt=0)
    credits_start_seconds: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_parent_and_ranges(self) -> "PlaybackSourceCreate":
        if (self.movie_id is None) == (self.episode_id is None):
            raise ValueError("Exactly one movie or episode must be assigned")
        for label, start, end in (
            ("intro", self.intro_start_seconds, self.intro_end_seconds),
            ("recap", self.recap_start_seconds, self.recap_end_seconds),
        ):
            if (start is None) != (end is None) or (
                start is not None and end is not None and end <= start
            ):
                raise ValueError(f"{label.title()} start and end must form an increasing pair")
        return self


class PlaybackSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    processing_job_id: uuid.UUID
    movie_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    edition_id: uuid.UUID | None
    intro_start_seconds: float | None
    intro_end_seconds: float | None
    recap_start_seconds: float | None
    recap_end_seconds: float | None
    credits_start_seconds: float | None
    created_at: datetime


class ProgressUpdate(BaseModel):
    position_seconds: float = Field(ge=0)
    duration_seconds: float = Field(gt=0)
    watched_seconds_delta: float | None = Field(default=None, ge=0, le=60)


class ProgressResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    position_seconds: float
    duration_seconds: float
    percentage: float
    completed: bool
    last_watched_at: datetime


class PlaybackConfig(BaseModel):
    source_id: uuid.UUID
    movie_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    edition_id: uuid.UUID | None
    original_language_code: str | None
    preferred_audio_language: str | None
    preferred_subtitle_language: str | None
    preferred_secondary_subtitle_language: str | None
    subtitles_enabled: bool
    caption_size: str
    caption_background: str
    caption_position: str
    title: str
    subtitle: str | None = None
    manifest_url: str
    duration_seconds: float
    qualities: list[dict[str, Any]]
    audio_tracks: list[dict[str, Any]]
    subtitle_tracks: list[dict[str, Any]]
    intro: tuple[float, float] | None
    recap: tuple[float, float] | None
    credits_start_seconds: float | None
    next_episode_id: uuid.UUID | None = None
    progress: ProgressResponse | None
