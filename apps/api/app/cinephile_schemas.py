import uuid
from typing import Any

from pydantic import BaseModel


class GalleryStill(BaseModel):
    id: uuid.UUID
    alt_text: str
    width: int | None
    height: int | None
    timestamp_seconds: float
    image_url: str


class MusicTimelineEntry(BaseModel):
    title: str
    composer: str | None
    performer: str | None
    start_seconds: float
    end_seconds: float


class FilmmakingEntry(BaseModel):
    category: str
    note: str
    reveal_seconds: float


class ExplorerCredit(BaseModel):
    person_id: uuid.UUID
    person_name: str
    person_slug: str
    role: str
    character_name: str | None
    company_name: str | None
    billing_order: int | None


class EditionEntry(BaseModel):
    id: uuid.UUID
    name: str
    runtime_minutes: int | None
    notes: str | None
    is_default: bool
    available: bool
    playback_source_id: uuid.UUID | None
    intended_presentation: bool
    aspect_ratio: str | None
    frame_rate: float | None
    presentation_format: str | None
    capture_format: str | None
    audio_format: str | None
    original_language_code: str | None
    restoration_info: str | None
    source_info: str | None
    audio_tracks: list[dict[str, Any]]
    subtitle_tracks: list[dict[str, Any]]


class EditionComparisonEntry(BaseModel):
    id: uuid.UUID
    source_edition_id: uuid.UUID
    target_edition_id: uuid.UUID
    kind: str
    description: str
    reveal_seconds: float | None


class RewatchIntelligence(BaseModel):
    viewings_started: int
    completed_viewings: int
    rewatches_started: int
    latest_completed_at: str | None
    enabled: bool
    active: bool
    saved_scenes: list[dict[str, Any]]
    personal_notes: list[dict[str, Any]]
    spoiler_aware_insights_available: bool


class CinephileToolkitResponse(BaseModel):
    playback_source_id: uuid.UUID
    title: str
    effective_cutoff: float
    stills: list[GalleryStill]
    music_timeline: list[MusicTimelineEntry]
    filmmaking: list[FilmmakingEntry]
    credits: list[ExplorerCredit]
    editions: list[EditionEntry]
    edition_comparison_unlocked: bool
    edition_comparisons: list[EditionComparisonEntry]
    rewatch: RewatchIntelligence
    safety_state: str
