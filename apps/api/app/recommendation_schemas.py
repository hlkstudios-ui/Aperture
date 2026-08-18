import uuid
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.catalog_schemas import MovieResponse, SeriesResponse


class RecommendationReason(StrEnum):
    editorial = "editorial"
    similar_genres = "similar_genres"
    similar_themes = "similar_themes"
    similar_tags = "similar_tags"
    profile_genre_preference = "profile_genre_preference"
    popular_now = "popular_now"
    cold_start = "cold_start"


class RecommendationItem(BaseModel):
    kind: str
    score: float
    reasons: list[RecommendationReason]
    movie: MovieResponse | None = None
    series: SeriesResponse | None = None


class RecommendationResponse(BaseModel):
    profile_id: uuid.UUID
    strategy: Literal["rules_v1", "editorial_popularity_v1"] = "rules_v1"
    personalized: bool = True
    cold_start: bool
    watched_titles_excluded: int
    items: list[RecommendationItem]


class RecommendationPreferenceUpdate(BaseModel):
    preferred_genre_slugs: list[str] = Field(default_factory=list, max_length=10)


class TasteAffinity(BaseModel):
    key: str
    label: str
    weight: float
    watched_titles: int


class TasteDnaResponse(BaseModel):
    profile_id: uuid.UUID
    derived_from: Literal["persisted_watch_progress"] = "persisted_watch_progress"
    watched_titles: int
    completed_titles: int
    completion_rate: float | None
    average_runtime_minutes: float | None
    confidence: Literal["none", "emerging", "established"]
    genres: list[TasteAffinity]
    themes: list[TasteAffinity]
    tags: list[TasteAffinity]
    decades: list[TasteAffinity]
    countries: list[TasteAffinity]
    languages: list[TasteAffinity]
    insights: list[str]


class PrescriptionRequest(BaseModel):
    time_available_minutes: int | None = Field(default=None, ge=20, le=600)
    mood: (
        Literal["uplifting", "dark", "comforting", "tense", "reflective", "adventurous"] | None
    ) = None
    pacing: Literal["slow", "balanced", "fast"] | None = None
    intensity: Literal["gentle", "moderate", "intense"] | None = None
    preferred_genre_slugs: list[str] = Field(default_factory=list, max_length=5)
    unwanted_genre_slugs: list[str] = Field(default_factory=list, max_length=5)
    unwanted_characteristics: list[str] = Field(default_factory=list, max_length=8)
    language: str | None = Field(default=None, min_length=2, max_length=16)
    release_era_start: int | None = Field(default=None, ge=1880, le=2100)
    release_era_end: int | None = Field(default=None, ge=1880, le=2100)
    watch_state: Literal["unwatched", "watched", "either"] = "unwatched"
    exclude_movie_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def coherent_constraints(self):
        if (
            self.release_era_start is not None
            and self.release_era_end is not None
            and self.release_era_end < self.release_era_start
        ):
            raise ValueError("Release era end must not precede its start")
        if set(self.preferred_genre_slugs) & set(self.unwanted_genre_slugs):
            raise ValueError("A genre cannot be both preferred and unwanted")
        return self


class PrescriptionDimension(BaseModel):
    dimension: str
    status: Literal["matched", "neutral", "unavailable"]
    explanation: str


class PrescriptionResponse(BaseModel):
    profile_id: uuid.UUID
    strategy: Literal["prescription_rules_v1"] = "prescription_rules_v1"
    movie: MovieResponse
    taste_match_score: int
    reason: str
    constraints_satisfied: bool
    match_dimensions: list[PrescriptionDimension]
