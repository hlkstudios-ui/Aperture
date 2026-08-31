from typing import Annotated

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import String, and_, cast, func, or_, select
from sqlalchemy.orm import with_loader_criteria

from app.auth import DbSession
from app.browse_schemas import (
    BrowseQuery,
    BrowseResponse,
    TmdbBrowseSectionsResponse,
    TmdbTrendingTitlesResponse,
)
from app.browse_service import browse_catalog
from app.catalog_models import (
    Artwork,
    CatalogStatus,
    Character,
    Company,
    Country,
    Credit,
    Episode,
    Franchise,
    Genre,
    Language,
    Movie,
    Person,
    Season,
    Series,
    Tag,
    Theme,
    TrailerClip,
)
from app.catalog_schemas import (
    ArtworkResponse,
    CreditResponse,
    LocaleResponse,
    MovieResponse,
    NamedRecordResponse,
    PreviewResponse,
    SeriesResponse,
)
from app.catalog_service import movie_query, series_query
from app.catalog_visibility import public_named_record_condition, public_title_conditions
from app.geo import OptionalViewerCountry
from app.knowledge_schemas import CreditDestination, FilmKnowledgeGraph
from app.knowledge_service import credit_destination, film_graph
from app.models import PlaybackSource, ProcessingJob, ProcessingState
from app.movie_api_client import movie_api_enabled
from app.scheduling import synchronize_due_schedules
from app.search_schemas import UniversalEntityResult, UniversalSearchResponse, UniversalTitleResult
from app.tmdb_browse_service import tmdb_browse_sections, tmdb_trending_titles
from app.tmdb_discovery import aperture_title, search_tmdb, tmdb_title

router = APIRouter(prefix="/catalog", tags=["customer catalog"])


PUBLIC_NAMED_RESOURCES = {
    "genres": Genre,
    "themes": Theme,
    "tags": Tag,
    "franchises": Franchise,
    "companies": Company,
    "people": Person,
    "characters": Character,
}
PUBLIC_LOCALE_RESOURCES = {"languages": Language, "countries": Country}


def _text_match(column, token: str):
    return column.ilike(f"%{token}%")


def _movie_token(token: str):
    credit_match = (
        select(Credit.id)
        .outerjoin(Person, Credit.person_id == Person.id)
        .outerjoin(Character, Credit.character_id == Character.id)
        .outerjoin(Company, Credit.company_id == Company.id)
        .where(
            Credit.movie_id == Movie.id,
            or_(
                _text_match(Person.name, token),
                _text_match(Character.name, token),
                _text_match(Company.name, token),
                _text_match(Credit.role, token),
            ),
        )
        .exists()
    )
    franchise_match = (
        select(Franchise.id)
        .where(Franchise.id == Movie.franchise_id, _text_match(Franchise.name, token))
        .exists()
    )
    return or_(
        _text_match(Movie.title, token),
        _text_match(Movie.original_title, token),
        _text_match(Movie.short_description, token),
        _text_match(Movie.synopsis, token),
        _text_match(Movie.slug, token),
        _text_match(Movie.external_id, token),
        _text_match(Movie.metadata_provider, token),
        _text_match(Movie.original_language_code, token),
        _text_match(Movie.country_code, token),
        _text_match(Movie.content_format, token),
        _text_match(Movie.maturity_rating, token),
        _text_match(cast(Movie.release_date, String), token),
        _text_match(cast(Movie.runtime_minutes, String), token),
        _text_match(cast(Movie.studios, String), token),
        Movie.genres.any(_text_match(Genre.name, token)),
        Movie.genres.any(func.similarity(Genre.name, token) > 0.28) if len(token) >= 4 else False,
        Movie.themes.any(_text_match(Theme.name, token)),
        Movie.tags.any(_text_match(Tag.name, token)),
        franchise_match,
        credit_match,
        func.similarity(Movie.title, token) > 0.28 if len(token) >= 4 else False,
        func.word_similarity(token, cast(Movie.studios, String)) > 0.35
        if len(token) >= 4
        else False,
    )


def _series_token(token: str):
    credit_match = (
        select(Credit.id)
        .outerjoin(Person, Credit.person_id == Person.id)
        .outerjoin(Character, Credit.character_id == Character.id)
        .outerjoin(Company, Credit.company_id == Company.id)
        .where(
            Credit.series_id == Series.id,
            or_(
                _text_match(Person.name, token),
                _text_match(Character.name, token),
                _text_match(Company.name, token),
                _text_match(Credit.role, token),
            ),
        )
        .exists()
    )
    franchise_match = (
        select(Franchise.id)
        .where(Franchise.id == Series.franchise_id, _text_match(Franchise.name, token))
        .exists()
    )
    episode_match = Series.seasons.any(
        or_(
            _text_match(Season.title, token),
            _text_match(Season.synopsis, token),
            Season.episodes.any(
                or_(_text_match(Episode.title, token), _text_match(Episode.synopsis, token))
            ),
        )
    )
    return or_(
        _text_match(Series.title, token),
        _text_match(Series.original_title, token),
        _text_match(Series.short_description, token),
        _text_match(Series.synopsis, token),
        _text_match(Series.slug, token),
        _text_match(Series.external_id, token),
        _text_match(Series.metadata_provider, token),
        _text_match(Series.original_language_code, token),
        _text_match(Series.country_code, token),
        _text_match(Series.content_format, token),
        _text_match(Series.maturity_rating, token),
        _text_match(cast(Series.release_date, String), token),
        _text_match(cast(Series.studios, String), token),
        Series.genres.any(_text_match(Genre.name, token)),
        Series.genres.any(func.similarity(Genre.name, token) > 0.28) if len(token) >= 4 else False,
        franchise_match,
        credit_match,
        episode_match,
        func.similarity(Series.title, token) > 0.28 if len(token) >= 4 else False,
        func.word_similarity(token, cast(Series.studios, String)) > 0.35
        if len(token) >= 4
        else False,
    )


def _title_rank(title: str, original_title: str | None, query: str) -> tuple[int, str]:
    normalized, original = title.casefold(), (original_title or "").casefold()
    needle = query.casefold()
    if normalized == needle or original == needle:
        return (0, normalized)
    if normalized.startswith(needle) or original.startswith(needle):
        return (1, normalized)
    if needle in normalized or needle in original:
        return (2, normalized)
    return (3, normalized)


@router.get("/search", response_model=UniversalSearchResponse)
def universal_search(
    db: DbSession,
    country: OptionalViewerCountry,
    q: str = Query(min_length=1, max_length=100),
    page: int = Query(default=1, ge=1, le=100),
    page_size: int = Query(default=24, ge=1, le=48),
) -> UniversalSearchResponse:
    """Search every public catalog dimension without sending the catalog to the browser."""
    synchronize_due_schedules(db)
    query = " ".join(q.split())
    tokens = [token for token in query.split(" ") if token][:8]
    movie_filter = and_(*(_movie_token(token) for token in tokens))
    series_filter = and_(*(_series_token(token) for token in tokens))
    movie_base = movie_query().where(*public_title_conditions(Movie, country=country), movie_filter)
    series_base = (
        series_query()
        .options(
            with_loader_criteria(
                Episode, Episode.status == CatalogStatus.published, include_aliases=True
            )
        )
        .where(*public_title_conditions(Series, country=country), series_filter)
    )
    total_movies = (
        db.scalar(
            select(func.count()).select_from(
                select(Movie.id)
                .where(
                    *public_title_conditions(Movie, country=country),
                    movie_filter,
                )
                .subquery()
            )
        )
        or 0
    )
    total_series = (
        db.scalar(
            select(func.count()).select_from(
                select(Series.id)
                .where(*public_title_conditions(Series, country=country), series_filter)
                .subquery()
            )
        )
        or 0
    )
    offset = (page - 1) * page_size
    candidate_limit = min(offset + page_size, 4800)
    movies_found = list(db.scalars(movie_base.limit(candidate_limit)).unique())
    series_found = list(db.scalars(series_base.limit(candidate_limit)).unique())
    combined = [("movie", item) for item in movies_found] + [
        ("series", item) for item in series_found
    ]
    combined.sort(key=lambda pair: _title_rank(pair[1].title, pair[1].original_title, query))
    page_records = combined[offset : offset + page_size]
    titles: list[UniversalTitleResult] = []
    for kind, record in page_records:
        seasons = record.seasons if kind == "series" else []
        titles.append(
            UniversalTitleResult(
                id=str(record.id),
                kind=kind,
                title=record.title,
                original_title=record.original_title,
                slug=record.slug,
                short_description=record.short_description,
                release_date=record.release_date,
                maturity_rating=record.maturity_rating,
                poster_url=record.poster_url,
                content_format=record.content_format,
                country_code=record.country_code,
                original_language_code=record.original_language_code,
                studios=record.studios,
                genres=[genre.name for genre in record.genres],
                duration_minutes=record.runtime_minutes if kind == "movie" else None,
                is_ongoing=record.is_ongoing if kind == "series" else None,
                season_count=len(seasons),
                episode_count=sum(len(season.episodes) for season in seasons),
                href=f"/{'movies' if kind == 'movie' else 'series'}/{record.slug}",
            )
        )
    entity_models = (
        ("person", Person),
        ("company", Company),
        ("character", Character),
        ("genre", Genre),
        ("theme", Theme),
        ("tag", Tag),
        ("franchise", Franchise),
    )
    entities: list[UniversalEntityResult] = []
    total_entities = 0
    for kind, model in entity_models:
        condition = or_(
            *(_text_match(model.name, token) for token in tokens),
            *(func.similarity(model.name, token) > 0.28 for token in tokens if len(token) >= 4),
        )
        public_condition = public_named_record_condition(model, country=country)
        matches = list(
            db.scalars(
                select(model).where(condition, public_condition).order_by(model.name).limit(12)
            )
        )
        total_entities += (
            db.scalar(select(func.count()).select_from(model).where(condition, public_condition))
            or 0
        )
        for item in matches:
            href = (
                f"/{'people' if kind == 'person' else 'companies'}/{item.slug}"
                if kind in {"person", "company"}
                else None
            )
            entities.append(
                UniversalEntityResult(
                    id=item.id, kind=kind, name=item.name, slug=item.slug, href=href
                )
            )
    external, external_total = search_tmdb(query, page)
    local_tmdb_ids = {
        f"tmdb:{kind}:{record.external_id}"
        for kind, record in combined
        if record.metadata_provider == "tmdb" and record.external_id
    }
    local_gateway_ids = {
        str(record.external_id)
        for _kind, record in combined
        if record.metadata_provider == "aperture_movie_api" and record.external_id
    }
    external_ids = {item.id for item in external}
    overlap_count = len(local_tmdb_ids & external_ids)
    external = [
        item
        for item in external
        if item.id not in local_tmdb_ids and item.id not in local_gateway_ids
    ]
    remaining = max(0, page_size - len(titles))
    titles.extend(external[:remaining])
    unique_external_total = max(len(external), external_total - overlap_count)
    total_titles = total_movies + total_series + unique_external_total
    return UniversalSearchResponse(
        query=query,
        page=page,
        page_size=page_size,
        total_titles=total_titles,
        total_entities=total_entities,
        has_more=offset + len(titles) < total_titles,
        titles=titles,
        entities=entities[:24],
    )


@router.get("/external/tmdb/{kind}/{external_id}", response_model=UniversalTitleResult)
def external_tmdb_title(kind: str, external_id: int) -> UniversalTitleResult:
    if movie_api_enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Title was not found")
    result = tmdb_title(kind, external_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "External title was not found")
    return result


@router.get("/titles/{aperture_id}", response_model=UniversalTitleResult)
def aperture_movie_api_title(aperture_id: str) -> UniversalTitleResult:
    result = aperture_title(aperture_id)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Title was not found")
    return result


@router.get("/browse", response_model=BrowseResponse)
def browse(
    db: DbSession,
    country: OptionalViewerCountry,
    filters: Annotated[BrowseQuery, Query()],
) -> BrowseResponse:
    """Page through the local catalog with character-aware search and structured facets."""
    synchronize_due_schedules(db)
    return browse_catalog(db, filters=filters, country=country)


@router.get("/browse/sections", response_model=TmdbBrowseSectionsResponse)
def browse_sections(
    page: int = Query(default=1, ge=1, le=100),
    page_size: int = Query(default=6, ge=1, le=10),
    items_per_section: int = Query(default=18, ge=8, le=20),
) -> TmdbBrowseSectionsResponse:
    """Page through 100 stable, server-curated TMDB discovery rails."""
    return tmdb_browse_sections(
        page=page,
        page_size=page_size,
        items_per_section=items_per_section,
    )


@router.get("/trending", response_model=TmdbTrendingTitlesResponse)
def trending_titles(
    page: int = Query(default=1, ge=1, le=500),
) -> TmdbTrendingTitlesResponse:
    """Page through the provider-ranked weekly movie and series pulse."""
    return tmdb_trending_titles(page=page)


@router.get("/metadata/{resource}", response_model=list[NamedRecordResponse])
def metadata(
    resource: str,
    db: DbSession,
    country: OptionalViewerCountry,
    limit: int = Query(default=100, ge=1, le=500),
):
    model = PUBLIC_NAMED_RESOURCES.get(resource)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog metadata resource was not found")
    return list(
        db.scalars(
            select(model)
            .where(public_named_record_condition(model, country=country))
            .order_by(model.name)
            .limit(limit)
        )
    )


@router.get("/metadata/{resource}/{slug}", response_model=NamedRecordResponse)
def metadata_record(resource: str, slug: str, db: DbSession, country: OptionalViewerCountry):
    model = PUBLIC_NAMED_RESOURCES.get(resource)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog metadata resource was not found")
    record = db.scalar(
        select(model).where(
            model.slug == slug,
            public_named_record_condition(model, country=country),
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog metadata record was not found")
    return record


@router.get("/locales/{resource}", response_model=list[LocaleResponse])
def locales(resource: str, db: DbSession):
    model = PUBLIC_LOCALE_RESOURCES.get(resource)
    if model is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Catalog locale resource was not found")
    return list(db.scalars(select(model).order_by(model.name)))


@router.get("/movies", response_model=list[MovieResponse])
def movies(
    db: DbSession,
    country: OptionalViewerCountry,
    query: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=40, ge=1, le=100),
) -> list[Movie]:
    synchronize_due_schedules(db)
    statement = movie_query().where(
        *public_title_conditions(Movie, country=country),
    )
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(Movie.title.ilike(pattern), Movie.short_description.ilike(pattern))
        )
    return list(
        db.scalars(statement.order_by(Movie.release_date.desc().nullslast()).limit(limit)).unique()
    )


@router.get("/movies/{slug}", response_model=MovieResponse)
def movie(slug: str, db: DbSession, country: OptionalViewerCountry) -> Movie:
    synchronize_due_schedules(db)
    record = db.scalar(
        movie_query().where(
            Movie.slug == slug,
            *public_title_conditions(Movie, country=country),
        )
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie was not found")
    return record


@router.get("/movies/{slug}/knowledge-graph", response_model=FilmKnowledgeGraph)
def movie_knowledge_graph(
    slug: str, db: DbSession, country: OptionalViewerCountry
) -> FilmKnowledgeGraph:
    return film_graph(db, movie(slug, db, country), country)


@router.get("/people/{slug}/credits", response_model=CreditDestination)
def person_credits(slug: str, db: DbSession, country: OptionalViewerCountry) -> CreditDestination:
    eligible = db.scalar(
        select(Person.id).where(
            Person.slug == slug,
            public_named_record_condition(Person, country=country),
        )
    )
    if eligible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person was not found")
    result = credit_destination(db, kind="person", slug=slug, country=country)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Person was not found")
    return result


@router.get("/companies/{slug}/credits", response_model=CreditDestination)
def company_credits(slug: str, db: DbSession, country: OptionalViewerCountry) -> CreditDestination:
    eligible = db.scalar(
        select(Company.id).where(
            Company.slug == slug,
            public_named_record_condition(Company, country=country),
        )
    )
    if eligible is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company was not found")
    result = credit_destination(db, kind="company", slug=slug, country=country)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Company was not found")
    return result


@router.get("/movies/{slug}/playback-availability")
def movie_playback_availability(
    slug: str, db: DbSession, country: OptionalViewerCountry
) -> dict[str, bool]:
    record = movie(slug, db, country)
    available = db.scalar(
        select(PlaybackSource.id)
        .join(Movie, PlaybackSource.movie_id == Movie.id)
        .join(ProcessingJob, PlaybackSource.processing_job_id == ProcessingJob.id)
        .where(
            Movie.id == record.id,
            ProcessingJob.state == ProcessingState.ready,
        )
    )
    return {"available": available is not None}


@router.get("/movies/{slug}/credits", response_model=list[CreditResponse])
def movie_credits(slug: str, db: DbSession, country: OptionalViewerCountry) -> list[Credit]:
    record = movie(slug, db, country)
    return list(
        db.scalars(
            select(Credit)
            .where(Credit.movie_id == record.id)
            .order_by(Credit.billing_order.asc().nullslast())
        )
    )


@router.get("/movies/{slug}/artwork", response_model=list[ArtworkResponse])
def movie_artwork(slug: str, db: DbSession, country: OptionalViewerCountry) -> list[Artwork]:
    record = movie(slug, db, country)
    return list(db.scalars(select(Artwork).where(Artwork.movie_id == record.id)))


@router.get("/movies/{slug}/previews", response_model=list[PreviewResponse])
def movie_previews(slug: str, db: DbSession, country: OptionalViewerCountry) -> list[TrailerClip]:
    record = movie(slug, db, country)
    return list(db.scalars(select(TrailerClip).where(TrailerClip.movie_id == record.id)))


@router.get("/series", response_model=list[SeriesResponse])
def series_list(
    db: DbSession,
    country: OptionalViewerCountry,
    query: str | None = Query(default=None, min_length=1, max_length=100),
    limit: int = Query(default=40, ge=1, le=100),
) -> list[Series]:
    synchronize_due_schedules(db)
    statement = (
        series_query()
        .options(
            with_loader_criteria(
                Episode, Episode.status == CatalogStatus.published, include_aliases=True
            )
        )
        .where(*public_title_conditions(Series, country=country))
    )
    if query:
        pattern = f"%{query.strip()}%"
        statement = statement.where(
            or_(Series.title.ilike(pattern), Series.short_description.ilike(pattern))
        )
    return list(
        db.scalars(statement.order_by(Series.release_date.desc().nullslast()).limit(limit)).unique()
    )


@router.get("/series/{slug}", response_model=SeriesResponse)
def series(slug: str, db: DbSession, country: OptionalViewerCountry) -> Series:
    synchronize_due_schedules(db)
    record = db.scalar(
        series_query()
        .options(
            with_loader_criteria(
                Episode, Episode.status == CatalogStatus.published, include_aliases=True
            )
        )
        .where(Series.slug == slug, *public_title_conditions(Series, country=country))
    )
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Series was not found")
    return record
