import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.catalog_models import (
    ArtworkKind,
    CatalogStatus,
    EditionDifferenceKind,
    PreviewKind,
    TitleRelationshipKind,
)


def validate_schedule(model):
    values = (
        model.publish_at,
        model.unpublish_at,
        model.rights_start_at,
        model.rights_end_at,
    )
    if any(value is not None and value.tzinfo is None for value in values):
        raise ValueError("Schedule timestamps must include a timezone")
    if model.publish_at and model.unpublish_at and model.unpublish_at <= model.publish_at:
        raise ValueError("Unpublish time must be after publish time")
    if (
        model.rights_start_at
        and model.rights_end_at
        and model.rights_end_at <= model.rights_start_at
    ):
        raise ValueError("Rights end must be after rights start")
    return model


def normalize_territories(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    normalized = [country.strip().upper() for country in value]
    if any(len(country) != 2 or not country.isalpha() for country in normalized):
        raise ValueError("Territories must be ISO 3166-1 alpha-2 country codes")
    if len(normalized) != len(set(normalized)):
        raise ValueError("Territories must not contain duplicates")
    return sorted(normalized)


class CatalogModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class NamedRecordCreate(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)


class NamedRecordUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=180)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=200)


class NamedRecordResponse(CatalogModel):
    id: uuid.UUID
    name: str
    slug: str


class LocaleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=16)
    name: str = Field(min_length=1, max_length=100)


class LocaleResponse(CatalogModel):
    code: str
    name: str


class LocaleUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class MovieCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=280)
    original_title: str | None = Field(default=None, max_length=250)
    short_description: str = Field(min_length=1, max_length=500)
    synopsis: str = Field(min_length=1)
    release_date: date | None = None
    runtime_minutes: int = Field(gt=0, le=1440)
    maturity_rating: str | None = Field(default=None, max_length=32)
    status: CatalogStatus = CatalogStatus.draft
    publish_at: datetime | None = None
    unpublish_at: datetime | None = None
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    original_language_code: str | None = Field(default=None, max_length=16)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    allowed_territories: list[str] = Field(default_factory=list, max_length=249)
    franchise_id: uuid.UUID | None = None
    genre_ids: list[uuid.UUID] = Field(default_factory=list)
    theme_ids: list[uuid.UUID] = Field(default_factory=list)
    tag_ids: list[uuid.UUID] = Field(default_factory=list)

    _schedule = model_validator(mode="after")(validate_schedule)
    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)


class MovieUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=280)
    original_title: str | None = Field(default=None, max_length=250)
    short_description: str | None = Field(default=None, min_length=1, max_length=500)
    synopsis: str | None = Field(default=None, min_length=1)
    release_date: date | None = None
    runtime_minutes: int | None = Field(default=None, gt=0, le=1440)
    maturity_rating: str | None = Field(default=None, max_length=32)
    status: CatalogStatus | None = None
    publish_at: datetime | None = None
    unpublish_at: datetime | None = None
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    original_language_code: str | None = Field(default=None, max_length=16)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    allowed_territories: list[str] | None = Field(default=None, max_length=249)
    franchise_id: uuid.UUID | None = None
    genre_ids: list[uuid.UUID] | None = None
    theme_ids: list[uuid.UUID] | None = None
    tag_ids: list[uuid.UUID] | None = None

    _schedule = model_validator(mode="after")(validate_schedule)
    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)


class MovieResponse(CatalogModel):
    id: uuid.UUID
    title: str
    slug: str
    original_title: str | None
    short_description: str
    synopsis: str
    release_date: date | None
    runtime_minutes: int
    maturity_rating: str | None
    status: CatalogStatus
    publish_at: datetime | None
    unpublish_at: datetime | None
    rights_start_at: datetime | None
    rights_end_at: datetime | None
    original_language_code: str | None
    country_code: str | None
    allowed_territories: list[str]
    franchise_id: uuid.UUID | None
    metadata_provider: str | None
    external_id: str | None
    poster_url: str | None
    backdrop_url: str | None
    content_format: str | None
    studios: list[str]
    genres: list[NamedRecordResponse]
    themes: list[NamedRecordResponse]
    tags: list[NamedRecordResponse]
    created_at: datetime
    updated_at: datetime


class SeriesCreate(BaseModel):
    title: str = Field(min_length=1, max_length=250)
    slug: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=280)
    original_title: str | None = Field(default=None, max_length=250)
    short_description: str = Field(min_length=1, max_length=500)
    synopsis: str = Field(min_length=1)
    release_date: date | None = None
    maturity_rating: str | None = Field(default=None, max_length=32)
    status: CatalogStatus = CatalogStatus.draft
    publish_at: datetime | None = None
    unpublish_at: datetime | None = None
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    original_language_code: str | None = Field(default=None, max_length=16)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    allowed_territories: list[str] = Field(default_factory=list, max_length=249)
    franchise_id: uuid.UUID | None = None
    genre_ids: list[uuid.UUID] = Field(default_factory=list)

    _schedule = model_validator(mode="after")(validate_schedule)
    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)


class SeriesUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=250)
    slug: str | None = Field(default=None, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=280)
    original_title: str | None = Field(default=None, max_length=250)
    short_description: str | None = Field(default=None, min_length=1, max_length=500)
    synopsis: str | None = Field(default=None, min_length=1)
    release_date: date | None = None
    maturity_rating: str | None = Field(default=None, max_length=32)
    status: CatalogStatus | None = None
    publish_at: datetime | None = None
    unpublish_at: datetime | None = None
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    original_language_code: str | None = Field(default=None, max_length=16)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    allowed_territories: list[str] | None = Field(default=None, max_length=249)
    franchise_id: uuid.UUID | None = None
    genre_ids: list[uuid.UUID] | None = None

    _schedule = model_validator(mode="after")(validate_schedule)
    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)


class EpisodeResponse(CatalogModel):
    id: uuid.UUID
    season_id: uuid.UUID
    number: int
    title: str
    synopsis: str
    runtime_minutes: int
    release_date: date | None
    still_url: str | None
    status: CatalogStatus


class SeasonResponse(CatalogModel):
    id: uuid.UUID
    series_id: uuid.UUID
    number: int
    title: str | None
    synopsis: str | None
    episodes: list[EpisodeResponse]


class SeriesResponse(CatalogModel):
    id: uuid.UUID
    title: str
    slug: str
    original_title: str | None
    short_description: str
    synopsis: str
    release_date: date | None
    maturity_rating: str | None
    status: CatalogStatus
    publish_at: datetime | None
    unpublish_at: datetime | None
    rights_start_at: datetime | None
    rights_end_at: datetime | None
    original_language_code: str | None
    country_code: str | None
    allowed_territories: list[str]
    franchise_id: uuid.UUID | None
    metadata_provider: str | None
    external_id: str | None
    poster_url: str | None
    backdrop_url: str | None
    is_ongoing: bool | None
    content_format: str | None
    studios: list[str]
    genres: list[NamedRecordResponse]
    seasons: list[SeasonResponse]
    created_at: datetime
    updated_at: datetime


class SeasonCreate(BaseModel):
    series_id: uuid.UUID
    number: int = Field(ge=0, le=1000)
    title: str | None = Field(default=None, max_length=250)
    synopsis: str | None = None


class SeasonUpdate(BaseModel):
    number: int | None = Field(default=None, ge=0, le=1000)
    title: str | None = Field(default=None, max_length=250)
    synopsis: str | None = None


class EpisodeCreate(BaseModel):
    season_id: uuid.UUID
    number: int = Field(ge=0, le=10000)
    title: str = Field(min_length=1, max_length=250)
    synopsis: str = Field(min_length=1)
    runtime_minutes: int = Field(gt=0, le=1440)
    release_date: date | None = None
    status: CatalogStatus = CatalogStatus.draft


class EpisodeUpdate(BaseModel):
    number: int | None = Field(default=None, ge=0, le=10000)
    title: str | None = Field(default=None, min_length=1, max_length=250)
    synopsis: str | None = Field(default=None, min_length=1)
    runtime_minutes: int | None = Field(default=None, gt=0, le=1440)
    release_date: date | None = None
    status: CatalogStatus | None = None


class ParentBoundModel(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None

    @model_validator(mode="after")
    def exactly_one_title(self):
        if (
            sum(value is not None for value in (self.movie_id, self.series_id, self.episode_id))
            != 1
        ):
            raise ValueError("Exactly one title parent must be supplied")
        return self


class EditionCreate(BaseModel):
    movie_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    name: str = Field(min_length=1, max_length=120)
    runtime_minutes: int | None = Field(default=None, gt=0, le=1440)
    notes: str | None = None
    is_default: bool = False
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    allowed_territories: list[str] = Field(default_factory=list, max_length=249)
    intended_presentation: bool = False
    aspect_ratio: str | None = Field(default=None, max_length=32)
    frame_rate: float | None = Field(default=None, gt=0, le=1000)
    presentation_format: str | None = Field(default=None, max_length=120)
    capture_format: str | None = Field(default=None, max_length=120)
    audio_format: str | None = Field(default=None, max_length=120)
    original_language_code: str | None = Field(default=None, max_length=16)
    restoration_info: str | None = None
    source_info: str | None = None

    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)

    @model_validator(mode="after")
    def exactly_one_parent(self):
        if (self.movie_id is None) == (self.episode_id is None):
            raise ValueError("Exactly one movie or episode parent must be supplied")
        if (
            self.rights_start_at
            and self.rights_end_at
            and self.rights_end_at <= self.rights_start_at
        ):
            raise ValueError("Rights end must be after rights start")
        return self


class EditionResponse(CatalogModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    name: str
    runtime_minutes: int | None
    notes: str | None
    is_default: bool
    rights_start_at: datetime | None
    rights_end_at: datetime | None
    allowed_territories: list[str]
    intended_presentation: bool
    aspect_ratio: str | None
    frame_rate: float | None
    presentation_format: str | None
    capture_format: str | None
    audio_format: str | None
    original_language_code: str | None
    restoration_info: str | None
    source_info: str | None


class EditionUpdate(BaseModel):
    movie_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    runtime_minutes: int | None = Field(default=None, gt=0, le=1440)
    notes: str | None = None
    is_default: bool | None = None
    rights_start_at: datetime | None = None
    rights_end_at: datetime | None = None
    allowed_territories: list[str] | None = Field(default=None, max_length=249)
    intended_presentation: bool | None = None
    aspect_ratio: str | None = Field(default=None, max_length=32)
    frame_rate: float | None = Field(default=None, gt=0, le=1000)
    presentation_format: str | None = Field(default=None, max_length=120)
    capture_format: str | None = Field(default=None, max_length=120)
    audio_format: str | None = Field(default=None, max_length=120)
    original_language_code: str | None = Field(default=None, max_length=16)
    restoration_info: str | None = None
    source_info: str | None = None

    _territories = field_validator("allowed_territories", mode="before")(normalize_territories)


class EditionDifferenceCreate(BaseModel):
    source_edition_id: uuid.UUID
    target_edition_id: uuid.UUID
    kind: EditionDifferenceKind
    description: str = Field(min_length=1, max_length=5000)
    reveal_seconds: float | None = Field(default=None, ge=0)
    source_note: str = Field(min_length=1, max_length=5000)
    manually_verified: bool = False

    @model_validator(mode="after")
    def distinct_editions(self):
        if self.source_edition_id == self.target_edition_id:
            raise ValueError("Edition comparison requires two different editions")
        return self


class EditionDifferenceResponse(CatalogModel):
    id: uuid.UUID
    source_edition_id: uuid.UUID
    target_edition_id: uuid.UUID
    kind: EditionDifferenceKind
    description: str
    reveal_seconds: float | None
    source_note: str
    manually_verified: bool


class TitleRelationshipCreate(BaseModel):
    source_movie_id: uuid.UUID
    target_movie_id: uuid.UUID
    kind: TitleRelationshipKind
    description: str | None = Field(default=None, max_length=5000)
    source_note: str = Field(min_length=1, max_length=5000)
    manually_verified: bool = False

    @model_validator(mode="after")
    def distinct_movies(self):
        if self.source_movie_id == self.target_movie_id:
            raise ValueError("A title relationship requires two different movies")
        return self


class TitleRelationshipResponse(CatalogModel):
    id: uuid.UUID
    source_movie_id: uuid.UUID
    target_movie_id: uuid.UUID
    kind: TitleRelationshipKind
    description: str | None
    source_note: str
    manually_verified: bool


class CreditCreate(ParentBoundModel):
    person_id: uuid.UUID
    character_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    role: str = Field(min_length=1, max_length=100)
    billing_order: int | None = Field(default=None, ge=0)


class CreditResponse(CatalogModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    series_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    person_id: uuid.UUID
    character_id: uuid.UUID | None
    company_id: uuid.UUID | None
    role: str
    billing_order: int | None


class CreditUpdate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    person_id: uuid.UUID | None = None
    character_id: uuid.UUID | None = None
    company_id: uuid.UUID | None = None
    role: str | None = Field(default=None, min_length=1, max_length=100)
    billing_order: int | None = Field(default=None, ge=0)


class ArtworkCreate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    kind: ArtworkKind
    scene_id: uuid.UUID | None = None
    timestamp_seconds: float | None = Field(default=None, ge=0)
    rights_basis: str | None = Field(default=None, min_length=1, max_length=2000)
    permitted_for_gallery: bool = False
    storage_key: str = Field(min_length=1, max_length=500)
    alt_text: str = Field(min_length=1, max_length=500)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def artwork_parent(self):
        values = (self.movie_id, self.series_id, self.season_id, self.episode_id)
        if sum(value is not None for value in values) != 1:
            raise ValueError("Exactly one artwork parent must be supplied")
        if self.permitted_for_gallery and (
            self.kind is not ArtworkKind.still
            or self.scene_id is None
            or self.timestamp_seconds is None
            or self.rights_basis is None
        ):
            raise ValueError(
                "Gallery permission requires a still, scene, timestamp, and rights basis"
            )
        return self


class ArtworkResponse(CatalogModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    series_id: uuid.UUID | None
    season_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    kind: ArtworkKind
    scene_id: uuid.UUID | None
    timestamp_seconds: float | None
    rights_basis: str | None
    permitted_for_gallery: bool
    storage_key: str
    alt_text: str
    width: int | None
    height: int | None


class ArtworkUpdate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    season_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    kind: ArtworkKind | None = None
    scene_id: uuid.UUID | None = None
    timestamp_seconds: float | None = Field(default=None, ge=0)
    rights_basis: str | None = Field(default=None, min_length=1, max_length=2000)
    permitted_for_gallery: bool | None = None
    storage_key: str | None = Field(default=None, min_length=1, max_length=500)
    alt_text: str | None = Field(default=None, min_length=1, max_length=500)
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)


class PreviewCreate(ParentBoundModel):
    kind: PreviewKind
    title: str = Field(min_length=1, max_length=250)
    storage_key: str | None = Field(default=None, max_length=500)
    external_url: str | None = Field(default=None, max_length=1000)
    duration_seconds: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def has_location(self):
        if not self.storage_key and not self.external_url:
            raise ValueError("A storage key or external URL is required")
        return self


class PreviewResponse(CatalogModel):
    id: uuid.UUID
    movie_id: uuid.UUID | None
    series_id: uuid.UUID | None
    episode_id: uuid.UUID | None
    kind: PreviewKind
    title: str
    storage_key: str | None
    external_url: str | None
    duration_seconds: int | None


class PreviewUpdate(BaseModel):
    movie_id: uuid.UUID | None = None
    series_id: uuid.UUID | None = None
    episode_id: uuid.UUID | None = None
    kind: PreviewKind | None = None
    title: str | None = Field(default=None, min_length=1, max_length=250)
    storage_key: str | None = Field(default=None, max_length=500)
    external_url: str | None = Field(default=None, max_length=1000)
    duration_seconds: int | None = Field(default=None, gt=0)
