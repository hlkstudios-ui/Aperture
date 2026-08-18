import uuid
from datetime import date

from pydantic import BaseModel


class UniversalTitleResult(BaseModel):
    id: str
    kind: str
    title: str
    original_title: str | None
    slug: str
    short_description: str
    release_date: date | None
    maturity_rating: str | None
    poster_url: str | None
    content_format: str | None
    country_code: str | None
    original_language_code: str | None
    studios: list[str]
    genres: list[str]
    season_count: int = 0
    episode_count: int = 0
    href: str
    source: str = "local"
    availability: str = "In the Aperture catalog"


class UniversalEntityResult(BaseModel):
    id: uuid.UUID
    kind: str
    name: str
    slug: str
    detail: str | None = None
    href: str | None = None


class UniversalSearchResponse(BaseModel):
    query: str
    page: int
    page_size: int
    total_titles: int
    total_entities: int
    has_more: bool
    titles: list[UniversalTitleResult]
    entities: list[UniversalEntityResult]
