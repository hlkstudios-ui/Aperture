from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, model_validator

from app.search_schemas import UniversalTitleResult


class BrowseSort(StrEnum):
    newest = "newest"
    oldest = "oldest"
    title_asc = "title_asc"
    title_desc = "title_desc"


SlugFilter = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=200,
        pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$",
    ),
]
LanguageFilter = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=2,
        max_length=16,
        pattern=r"^[a-z][a-z0-9-]+$",
    ),
]
CountryFilter = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_upper=True,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Za-z]{2}$",
    ),
]
FormatFilter = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        to_lower=True,
        min_length=1,
        max_length=32,
        pattern=r"^[a-z0-9][a-z0-9_-]*$",
    ),
]
RatingFilter = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=32)]
StudioFilter = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=180)
]
SearchQuery = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]


class BrowseQuery(BaseModel):
    """Validated query-string contract for the local browse catalog."""

    q: SearchQuery | None = None
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=32, ge=1, le=32)
    sort: BrowseSort = BrowseSort.newest
    kind: list[Literal["movie", "series"]] = Field(default_factory=list, max_length=2)
    genre: list[SlugFilter] = Field(default_factory=list, max_length=20)
    theme: list[SlugFilter] = Field(default_factory=list, max_length=20)
    tag: list[SlugFilter] = Field(default_factory=list, max_length=20)
    character: list[SlugFilter] = Field(default_factory=list, max_length=20)
    language: list[LanguageFilter] = Field(default_factory=list, max_length=20)
    country: list[CountryFilter] = Field(default_factory=list, max_length=20)
    content_format: list[FormatFilter] = Field(default_factory=list, max_length=20)
    maturity_rating: list[RatingFilter] = Field(default_factory=list, max_length=20)
    studio: list[StudioFilter] = Field(default_factory=list, max_length=20)
    release_decade: list[int] = Field(default_factory=list, max_length=20)
    runtime_band: list[Literal["short", "standard", "long"]] = Field(
        default_factory=list, max_length=3
    )
    airing: Literal["ongoing", "completed"] | None = None
    release_year_from: int | None = Field(default=None, ge=1888, le=2100)
    release_year_to: int | None = Field(default=None, ge=1888, le=2100)
    runtime_minutes_min: int | None = Field(default=None, ge=1, le=1440)
    runtime_minutes_max: int | None = Field(default=None, ge=1, le=1440)
    include_facets: bool = True

    @model_validator(mode="after")
    def validate_ranges_and_decades(self):
        if (
            self.release_year_from is not None
            and self.release_year_to is not None
            and self.release_year_from > self.release_year_to
        ):
            raise ValueError("release_year_from must not exceed release_year_to")
        if (
            self.runtime_minutes_min is not None
            and self.runtime_minutes_max is not None
            and self.runtime_minutes_min > self.runtime_minutes_max
        ):
            raise ValueError("runtime_minutes_min must not exceed runtime_minutes_max")
        if any(decade < 1880 or decade > 2100 or decade % 10 for decade in self.release_decade):
            raise ValueError("release_decade values must be decade starts from 1880 through 2100")
        return self


class BrowseFacetOption(BaseModel):
    value: str
    label: str
    count: int = Field(ge=0)


class BrowseFacet(BaseModel):
    key: str
    label: str
    icon: str
    selection: Literal["multiple", "single"] = "multiple"
    options: list[BrowseFacetOption]


class BrowseFacetGroup(BaseModel):
    key: str
    label: str
    icon: str
    facets: list[BrowseFacet]


class BrowseResponse(BaseModel):
    query: str | None
    page: int
    page_size: int
    total: int
    has_more: bool
    next_page: int | None
    sort: BrowseSort
    items: list[UniversalTitleResult]
    facet_groups: list[BrowseFacetGroup]


class TmdbBrowseTitle(UniversalTitleResult):
    """A card-sized TMDB discovery result with optional editorial signals."""

    backdrop_url: str | None = None
    vote_average: float | None = None
    vote_count: int = Field(default=0, ge=0)
    popularity: float | None = None


class TmdbBrowseSection(BaseModel):
    id: str
    slug: str
    eyebrow: str
    title: str
    description: str
    media_type: Literal["movie", "series", "mixed"]
    source: Literal["aperture", "tmdb"] = "aperture"
    status: Literal["ready", "stale", "unavailable"] = "ready"
    items: list[TmdbBrowseTitle]


class TmdbAttribution(BaseModel):
    provider: Literal["TMDB"] = "TMDB"
    notice: str
    url: str


class TmdbBrowseSectionsResponse(BaseModel):
    page: int = Field(ge=1)
    page_size: int = Field(ge=1, le=10)
    total_sections: int = Field(ge=0)
    has_more: bool
    next_page: int | None
    items_per_section: int = Field(ge=8, le=20)
    sections: list[TmdbBrowseSection]
    attribution: TmdbAttribution
    partial: bool = False


class TmdbTrendingTitlesResponse(BaseModel):
    """One provider-ranked page from the mixed weekly movie and series pulse."""

    page: int = Field(ge=1, le=500)
    page_size: int = Field(ge=0, le=20)
    total_results: int = Field(ge=0)
    total_pages: int = Field(ge=0, le=500)
    has_more: bool
    next_page: int | None
    source: Literal["aperture", "tmdb"]
    status: Literal["ready", "unavailable"]
    items: list[TmdbBrowseTitle]
    attribution: TmdbAttribution
