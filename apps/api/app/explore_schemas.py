import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.search_schemas import UniversalTitleResult


class ExploreInputModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ExploreCriteria(ExploreInputModel):
    content_type: Literal["all", "movie", "series", "ova"] = "all"
    query: str | None = Field(default=None, max_length=100)
    genre: str | None = Field(default=None, max_length=100)
    studio: str | None = Field(default=None, max_length=120)
    country_code: str | None = Field(default=None, pattern=r"^[A-Z]{2}$")
    original_language_code: str | None = Field(default=None, pattern=r"^[a-z]{2,10}$")
    maturity_rating: str | None = Field(default=None, max_length=32)
    release_period: Literal["all", "2020s", "2010s", "classic"] = "all"
    duration: Literal["all", "short", "standard", "long"] = "all"
    airing: Literal["all", "ongoing", "finished"] = "all"


class ExploreEntryWrite(ExploreInputModel):
    label: str = Field(min_length=1, max_length=64)
    description: str = Field(default="", max_length=180)
    icon: str = Field(default="↗", min_length=1, max_length=16, pattern=r"^[^\x00-\x1f\x7f]+$")
    position: int = Field(ge=0, le=1000)
    enabled: bool = True
    criteria: ExploreCriteria = Field(default_factory=ExploreCriteria)


class ExploreCardCreate(ExploreInputModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    position: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def one_title(self):
        if (self.movie_id is None) == (self.series_id is None):
            raise ValueError("Choose exactly one movie or series")
        return self


class ExploreCardOrder(ExploreInputModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Ordering identifiers must be unique")
        return self


class ExploreCardResponse(BaseModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    series_id: uuid.UUID | None
    position: int
    title: UniversalTitleResult


class ExploreEntryPublicResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    label: str
    description: str
    icon: str
    position: int
    criteria: ExploreCriteria
    cards: list[ExploreCardResponse] = Field(default_factory=list)


class ExploreEntryResponse(ExploreEntryPublicResponse):
    enabled: bool
    created_at: datetime
    updated_at: datetime


class ExploreEntryOrder(ExploreInputModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=24)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Ordering identifiers must be unique")
        return self
