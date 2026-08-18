import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.models import ProcessingState


class ProcessingJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    asset_id: uuid.UUID
    state: ProcessingState
    progress_percent: int
    source_metadata: dict[str, Any]
    rendition_status: list[dict[str, Any]]
    audio_tracks: list[dict[str, Any]]
    subtitle_tracks: list[dict[str, Any]]
    chapters: list[dict[str, Any]]
    duration_seconds: float | None
    manifest_key: str | None
    thumbnail_key: str | None
    sprite_key: str | None
    error_message: str | None
    attempts: int
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None


class ProcessingJobDetail(ProcessingJobResponse):
    original_filename: str
    playback_source_id: uuid.UUID | None = None
