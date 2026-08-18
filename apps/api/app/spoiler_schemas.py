import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CurrentScene(BaseModel):
    id: uuid.UUID
    ordinal: int
    title: str
    start_seconds: float
    end_seconds: float


class LensBookmarkCreate(BaseModel):
    scene_id: uuid.UUID | None = None
    timestamp_seconds: float = Field(ge=0)
    title: str = Field(min_length=1, max_length=180)


class LensNoteCreate(BaseModel):
    scene_id: uuid.UUID | None = None
    timestamp_seconds: float = Field(ge=0)
    body: str = Field(min_length=1, max_length=5000)


class LensBookmarkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    scene_id: uuid.UUID | None
    timestamp_seconds: float
    title: str


class LensNoteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    scene_id: uuid.UUID | None
    timestamp_seconds: float
    body: str


class AskMovieRequest(BaseModel):
    question: str = Field(min_length=2, max_length=500)
    timestamp_seconds: float = Field(ge=0)
    mode: Literal["protected", "full"] = "protected"


class AskEvidence(BaseModel):
    kind: str
    reveal_seconds: float


class AskMovieResponse(BaseModel):
    answer: str
    intent: str
    confidence: Literal["supported", "limited", "unavailable"]
    uncertainty: str | None
    strategy: Literal["structured_templates_v1"] = "structured_templates_v1"
    evidence: list[AskEvidence]
    safety_state: str


class WhoCharacter(BaseModel):
    character_id: uuid.UUID
    character_name: str
    actor_name: str | None
    prior_appearance_seconds: list[float]
    summary: str


class WhoWasThatResponse(BaseModel):
    characters: list[WhoCharacter]
    known_relationships: list[str]
    confidence: Literal["supported", "unavailable"]
    uncertainty: str | None
    safety_state: str


class MissedIntervalRequest(BaseModel):
    start_seconds: float = Field(ge=0)
    end_seconds: float = Field(gt=0)
    current_timestamp: float = Field(ge=0)


class WhatDidIMissResponse(BaseModel):
    start_seconds: float
    end_seconds: float
    recap: str
    confidence: Literal["supported", "unavailable"]
    uncertainty: str | None
    evidence: list[AskEvidence]
    safety_state: str


class RelationshipNode(BaseModel):
    id: str
    label: str
    entity_type: str
    current_character: bool
    first_reveal_seconds: float


class RelationshipEdge(BaseModel):
    id: uuid.UUID
    source: str
    target: str
    label: str
    reveal_seconds: float


class RelationshipGraphResponse(BaseModel):
    nodes: list[RelationshipNode]
    edges: list[RelationshipEdge]
    effective_cutoff: float
    equality_policy: Literal["inclusive"] = "inclusive"
    safety_state: str


class SpoilerFact(BaseModel):
    id: uuid.UUID
    kind: Literal[
        "scene",
        "character",
        "entity",
        "relationship",
        "music_cue",
        "production_note",
        "spoiler_boundary",
        "transcript_cue",
    ]
    scene_id: uuid.UUID | None = None
    reveal_seconds: float
    payload: dict


class SpoilerContextResponse(BaseModel):
    playback_source_id: uuid.UUID
    version_id: uuid.UUID | None
    mode: Literal["protected", "full"]
    equality_policy: Literal["inclusive"] = "inclusive"
    requested_timestamp: float
    effective_cutoff: float
    completion_unlock: bool
    current_scene: CurrentScene | None = None
    facts: list[SpoilerFact]
    bookmarks: list[LensBookmarkResponse] = []
    notes: list[LensNoteResponse] = []
    withheld: dict[str, int]
    safety_state: Literal["ok", "no_published_evidence", "malformed_evidence_omitted"]
