import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.catalog_schemas import NamedRecordResponse
from app.models import HomepageSource


class HomepageModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class HeroUpdate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def one_hero(self):
        if self.movie_id is not None and self.series_id is not None:
            raise ValueError("Choose only one hero title")
        return self


class RailCreate(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    eyebrow: str | None = Field(default=None, max_length=80)
    source: HomepageSource = HomepageSource.pinned
    query: str | None = Field(default=None, max_length=100)
    position: int = Field(ge=0, le=1000)
    enabled: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def valid_schedule(self):
        for value in (self.starts_at, self.ends_at):
            if value is not None and value.tzinfo is None:
                raise ValueError("Schedule timestamps must include a timezone")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("Rail end must be after its start")
        return self


class RailUpdate(RailCreate):
    pass


class ItemCreate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    position: int = Field(ge=0, le=1000)

    @model_validator(mode="after")
    def one_title(self):
        if (self.movie_id is None) == (self.series_id is None):
            raise ValueError("Choose exactly one movie or series")
        return self


class OrderedIds(BaseModel):
    ids: list[uuid.UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_ids(self):
        if len(set(self.ids)) != len(self.ids):
            raise ValueError("Ordering identifiers must be unique")
        return self


class ItemResponse(HomepageModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    series_id: uuid.UUID | None
    position: int


class RailResponse(HomepageModel):
    id: uuid.UUID
    title: str
    eyebrow: str | None
    source: HomepageSource
    query: str | None
    position: int
    enabled: bool
    starts_at: datetime | None
    ends_at: datetime | None
    items: list[ItemResponse]


class HomepageDraftResponse(BaseModel):
    id: uuid.UUID
    hero_movie_id: uuid.UUID | None
    hero_series_id: uuid.UUID | None
    rails: list[RailResponse]
    published_at: datetime | None


class HomepageTitle(BaseModel):
    id: uuid.UUID
    kind: str
    title: str
    slug: str
    short_description: str
    release_date: date | None
    maturity_rating: str | None
    runtime_minutes: int | None = None
    season_count: int | None = None
    genres: list[NamedRecordResponse] = Field(default_factory=list)
    poster_url: str | None = None
    backdrop_url: str | None = None
    metadata_provider: str | None = None


class HomepagePublicRail(BaseModel):
    id: uuid.UUID
    title: str
    eyebrow: str | None
    items: list[HomepageTitle]


class HomepagePublicResponse(BaseModel):
    hero: HomepageTitle | None
    rails: list[HomepagePublicRail]
    published_at: datetime | None
    mode: str = "curated"
    strategy: str = "published_editorial_snapshot"


class HomepageModeUpdate(BaseModel):
    mode: str = Field(pattern="^(curated|no_algorithm)$")
