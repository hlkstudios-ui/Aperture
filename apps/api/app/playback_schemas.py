import uuid
from datetime import datetime
from typing import Any

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field, model_validator


class PlaybackSourceCreate(BaseModel):
    processing_job_id: uuid.UUID | None = None
    external_manifest_url: AnyHttpUrl | None = None
    external_format: str | None = None
    duration_seconds: float | None = Field(default=None, gt=0)
    rights_basis: str | None = Field(default=None, min_length=12, max_length=500)
    rights_reference: str | None = Field(default=None, min_length=3, max_length=500)
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    allowed_territories: list[str] = Field(default_factory=list)
    is_active: bool = False
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
        if (self.processing_job_id is None) == (self.external_manifest_url is None):
            raise ValueError("Exactly one processed job or external CDN manifest is required")
        if self.external_manifest_url is not None:
            if self.external_manifest_url.scheme != "https":
                raise ValueError("External CDN URLs must use HTTPS")
            path = self.external_manifest_url.path.lower()
            inferred = "hls" if path.endswith(".m3u8") else "mp4" if path.endswith(".mp4") else None
            self.external_format = self.external_format or inferred
            if self.external_format not in {"hls", "mp4"}:
                raise ValueError("External source must be an HLS .m3u8 or MP4 URL")
            if not self.rights_basis or not self.rights_reference:
                raise ValueError("External sources require licensing evidence")
        if (
            self.rights_start_at
            and self.rights_end_at
            and self.rights_end_at <= self.rights_start_at
        ):
            raise ValueError("Rights end must be after rights start")
        self.allowed_territories = sorted(
            {item.strip().upper() for item in self.allowed_territories if item.strip()}
        )
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
    processing_job_id: uuid.UUID | None
    external_manifest_url: str | None
    external_format: str | None
    duration_seconds: float | None
    rights_basis: str | None
    rights_reference: str | None
    rights_start_at: datetime | None
    rights_end_at: datetime | None
    allowed_territories: list[str]
    is_active: bool
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
