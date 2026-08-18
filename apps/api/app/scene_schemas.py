import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.scene_models import (
    EnrichmentJobState,
    IntelligenceVersionState,
    ProvenanceKind,
)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class VersionCreate(BaseModel):
    playback_source_id: uuid.UUID
    notes: str | None = Field(default=None, max_length=1000)


class VersionResponse(OrmModel):
    id: uuid.UUID
    playback_source_id: uuid.UUID
    number: int
    state: IntelligenceVersionState
    notes: str | None
    validated_at: datetime | None
    published_at: datetime | None
    created_at: datetime


class SourceCreate(BaseModel):
    kind: ProvenanceKind
    label: str = Field(min_length=1, max_length=200)
    source_uri: str | None = Field(default=None, max_length=1000)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    license_basis: str = Field(min_length=1, max_length=500)
    captured_at: datetime | None = None


class SourceResponse(OrmModel):
    id: uuid.UUID
    version_id: uuid.UUID
    kind: ProvenanceKind
    label: str
    source_uri: str | None
    checksum_sha256: str | None
    license_basis: str
    captured_at: datetime | None
    created_at: datetime


class TimedCreate(BaseModel):
    source_id: uuid.UUID
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)

    @model_validator(mode="after")
    def increasing_range(self):
        if self.end_seconds <= self.start_seconds:
            raise ValueError("End time must be after start time")
        return self


class SceneCreate(TimedCreate):
    ordinal: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=250)
    summary: str = Field(min_length=1, max_length=5000)
    confidence: float = Field(ge=0, le=1)
    manually_verified: bool = False


class SceneUpdate(BaseModel):
    source_id: uuid.UUID | None = None
    ordinal: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    summary: str | None = Field(default=None, min_length=1, max_length=5000)
    start_seconds: float | None = Field(default=None, ge=0)
    end_seconds: float | None = Field(default=None, gt=0)
    confidence: float | None = Field(default=None, ge=0, le=1)
    manually_verified: bool | None = None


class SceneResponse(OrmModel):
    id: uuid.UUID
    version_id: uuid.UUID
    source_id: uuid.UUID
    ordinal: int
    title: str
    summary: str
    start_seconds: float
    end_seconds: float
    confidence: float
    manually_verified: bool


class ChapterCreate(TimedCreate):
    ordinal: int = Field(gt=0)
    title: str = Field(min_length=1, max_length=250)


class EntityCreate(BaseModel):
    source_id: uuid.UUID
    entity_type: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=250)
    canonical_key: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=280)
    description: str | None = Field(default=None, max_length=5000)
    confidence: float = Field(ge=0, le=1)
    reveal_seconds: float = Field(ge=0)


class CharacterCreate(BaseModel):
    source_id: uuid.UUID
    character_id: uuid.UUID
    confidence: float = Field(ge=0, le=1)
    reveal_seconds: float = Field(ge=0)
    manually_verified: bool = False


class RelationshipCreate(BaseModel):
    source_id: uuid.UUID
    subject_entity_id: uuid.UUID
    object_entity_id: uuid.UUID
    relationship: str = Field(min_length=1, max_length=250)
    confidence: float = Field(ge=0, le=1)
    reveal_seconds: float = Field(ge=0)


class MusicCueCreate(TimedCreate):
    title: str = Field(min_length=1, max_length=250)
    composer: str | None = Field(default=None, max_length=250)
    performer: str | None = Field(default=None, max_length=250)


class ProductionNoteCreate(BaseModel):
    source_id: uuid.UUID
    category: str = Field(min_length=1, max_length=100)
    note: str = Field(min_length=1, max_length=5000)
    reveal_seconds: float = Field(ge=0)


class SpoilerBoundaryCreate(BaseModel):
    source_id: uuid.UUID
    label: str = Field(min_length=1, max_length=250)
    description: str = Field(min_length=1, max_length=5000)
    reveal_seconds: float = Field(ge=0)


class JobResponse(OrmModel):
    id: uuid.UUID
    version_id: uuid.UUID
    state: EnrichmentJobState
    stage: str
    progress_percent: int
    attempts: int
    error_message: str | None
    created_at: datetime


class VersionDetail(BaseModel):
    version: VersionResponse
    playback_label: str
    duration_seconds: float
    available_evidence: list[dict]
    sources: list[SourceResponse]
    scenes: list[SceneResponse]
    chapters: list[dict]
    entities: list[dict]
    characters: list[dict]
    relationships: list[dict]
    music_cues: list[dict]
    production_notes: list[dict]
    spoiler_boundaries: list[dict]
    transcript_cues: list[dict]
    jobs: list[JobResponse]
    validation_errors: list[str]
