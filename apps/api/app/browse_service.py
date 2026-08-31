from collections.abc import Sequence

from sqlalchemy import (
    Boolean,
    Integer,
    String,
    and_,
    case,
    cast,
    extract,
    func,
    literal,
    or_,
    select,
    union_all,
)
from sqlalchemy.orm import Session, with_loader_criteria

from app.browse_schemas import (
    BrowseFacet,
    BrowseFacetGroup,
    BrowseFacetOption,
    BrowseQuery,
    BrowseResponse,
    BrowseSort,
)
from app.catalog_models import (
    CatalogStatus,
    Character,
    Company,
    Country,
    Credit,
    Episode,
    Genre,
    Language,
    Movie,
    Person,
    Season,
    Series,
    Tag,
    Theme,
    movie_genres,
    movie_tags,
    movie_themes,
    series_genres,
)
from app.catalog_service import movie_query, series_query
from app.catalog_visibility import public_title_conditions
from app.search_schemas import UniversalTitleResult

FACET_OPTION_LIMIT = 100


def _text_match(column, token: str):
    return column.ilike(f"%{token}%")


def _credit_text_match(token: str):
    return or_(
        _text_match(Person.name, token),
        _text_match(Character.name, token),
        _text_match(Company.name, token),
        _text_match(Credit.role, token),
    )


def _movie_text_token(token: str):
    credit_match = (
        select(Credit.id)
        .outerjoin(Person, Credit.person_id == Person.id)
        .outerjoin(Character, Credit.character_id == Character.id)
        .outerjoin(Company, Credit.company_id == Company.id)
        .where(Credit.movie_id == Movie.id, _credit_text_match(token))
        .correlate(Movie)
        .exists()
    )
    return or_(
        _text_match(Movie.title, token),
        _text_match(Movie.original_title, token),
        _text_match(Movie.short_description, token),
        _text_match(Movie.synopsis, token),
        Movie.genres.any(_text_match(Genre.name, token)),
        Movie.themes.any(_text_match(Theme.name, token)),
        Movie.tags.any(_text_match(Tag.name, token)),
        credit_match,
    )


def _series_text_token(token: str):
    episode_ids = (
        select(Episode.id)
        .join(Season, Episode.season_id == Season.id)
        .where(Season.series_id == Series.id)
        .correlate(Series)
    )
    credit_match = (
        select(Credit.id)
        .outerjoin(Person, Credit.person_id == Person.id)
        .outerjoin(Character, Credit.character_id == Character.id)
        .outerjoin(Company, Credit.company_id == Company.id)
        .where(
            or_(Credit.series_id == Series.id, Credit.episode_id.in_(episode_ids)),
            _credit_text_match(token),
        )
        .correlate(Series)
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
        Series.genres.any(_text_match(Genre.name, token)),
        episode_match,
        credit_match,
    )


def _movie_character_filter(slugs: Sequence[str]):
    return (
        select(Credit.id)
        .join(Character, Credit.character_id == Character.id)
        .where(Credit.movie_id == Movie.id, Character.slug.in_(slugs))
        .correlate(Movie)
        .exists()
    )


def _series_character_filter(slugs: Sequence[str]):
    episode_ids = (
        select(Episode.id)
        .join(Season, Episode.season_id == Season.id)
        .where(Season.series_id == Series.id)
        .correlate(Series)
    )
    return (
        select(Credit.id)
        .join(Character, Credit.character_id == Character.id)
        .where(
            or_(Credit.series_id == Series.id, Credit.episode_id.in_(episode_ids)),
            Character.slug.in_(slugs),
        )
        .correlate(Series)
        .exists()
    )


def _release_conditions(column, filters: BrowseQuery):
    conditions = []
    if filters.release_year_from is not None:
        conditions.append(extract("year", column) >= filters.release_year_from)
    if filters.release_year_to is not None:
        conditions.append(extract("year", column) <= filters.release_year_to)
    if filters.release_decade:
        conditions.append(
            or_(
                *(
                    and_(extract("year", column) >= decade, extract("year", column) <= decade + 9)
                    for decade in filters.release_decade
                )
            )
        )
    return conditions


def _movie_conditions(filters: BrowseQuery, country: str | None):
    conditions = [
        *public_title_conditions(Movie, country=country),
    ]
    if filters.q:
        tokens = filters.q.split()[:8]
        conditions.extend(_movie_text_token(token) for token in tokens)
    if filters.genre:
        conditions.append(Movie.genres.any(Genre.slug.in_(filters.genre)))
    if filters.theme:
        conditions.append(Movie.themes.any(Theme.slug.in_(filters.theme)))
    if filters.tag:
        conditions.append(Movie.tags.any(Tag.slug.in_(filters.tag)))
    if filters.character:
        conditions.append(_movie_character_filter(filters.character))
    if filters.language:
        conditions.append(Movie.original_language_code.in_(filters.language))
    if filters.country:
        conditions.append(Movie.country_code.in_(filters.country))
    if filters.content_format:
        conditions.append(Movie.content_format.in_(filters.content_format))
    if filters.maturity_rating:
        conditions.append(Movie.maturity_rating.in_(filters.maturity_rating))
    if filters.studio:
        conditions.append(or_(*(Movie.studios.contains([studio]) for studio in filters.studio)))
    conditions.extend(_release_conditions(Movie.release_date, filters))
    if filters.runtime_minutes_min is not None:
        conditions.append(Movie.runtime_minutes >= filters.runtime_minutes_min)
    if filters.runtime_minutes_max is not None:
        conditions.append(Movie.runtime_minutes <= filters.runtime_minutes_max)
    if filters.runtime_band:
        runtime_bands = {
            "short": Movie.runtime_minutes < 30,
            "standard": Movie.runtime_minutes.between(30, 90),
            "long": Movie.runtime_minutes > 90,
        }
        conditions.append(or_(*(runtime_bands[band] for band in filters.runtime_band)))
    return conditions


def _series_conditions(filters: BrowseQuery, country: str | None):
    conditions = [*public_title_conditions(Series, country=country)]
    if filters.q:
        tokens = filters.q.split()[:8]
        conditions.extend(_series_text_token(token) for token in tokens)
    if filters.genre:
        conditions.append(Series.genres.any(Genre.slug.in_(filters.genre)))
    if filters.character:
        conditions.append(_series_character_filter(filters.character))
    if filters.language:
        conditions.append(Series.original_language_code.in_(filters.language))
    if filters.country:
        conditions.append(Series.country_code.in_(filters.country))
    if filters.content_format:
        conditions.append(Series.content_format.in_(filters.content_format))
    if filters.maturity_rating:
        conditions.append(Series.maturity_rating.in_(filters.maturity_rating))
    if filters.studio:
        conditions.append(or_(*(Series.studios.contains([studio]) for studio in filters.studio)))
    if filters.airing == "ongoing":
        conditions.append(Series.is_ongoing.is_(True))
    elif filters.airing == "completed":
        conditions.append(Series.is_ongoing.is_(False))
    conditions.extend(_release_conditions(Series.release_date, filters))
    return conditions


def _title_statements(filters: BrowseQuery, country: str | None):
    requested_kinds = set(filters.kind) or {"movie", "series"}
    statements = []
    movie_only_filter = bool(
        filters.theme
        or filters.tag
        or filters.runtime_band
        or filters.runtime_minutes_min is not None
        or filters.runtime_minutes_max is not None
    )
    if "movie" in requested_kinds and filters.airing is None:
        statements.append(
            select(
                Movie.id.label("id"),
                literal("movie").label("kind"),
                Movie.title.label("title"),
                Movie.release_date.label("release_date"),
                Movie.maturity_rating.label("maturity_rating"),
                Movie.content_format.label("content_format"),
                Movie.country_code.label("country_code"),
                Movie.original_language_code.label("original_language_code"),
                Movie.studios.label("studios"),
                Movie.runtime_minutes.label("duration_minutes"),
                cast(literal(None), Boolean).label("is_ongoing"),
            ).where(*_movie_conditions(filters, country))
        )
    if "series" in requested_kinds and not movie_only_filter:
        statements.append(
            select(
                Series.id.label("id"),
                literal("series").label("kind"),
                Series.title.label("title"),
                Series.release_date.label("release_date"),
                Series.maturity_rating.label("maturity_rating"),
                Series.content_format.label("content_format"),
                Series.country_code.label("country_code"),
                Series.original_language_code.label("original_language_code"),
                Series.studios.label("studios"),
                cast(literal(None), Integer).label("duration_minutes"),
                Series.is_ongoing.label("is_ongoing"),
            ).where(*_series_conditions(filters, country))
        )
    return statements


def _sort_columns(catalog, sort: BrowseSort):
    title = func.lower(catalog.c.title)
    tie_breakers = (catalog.c.kind.asc(), catalog.c.id.asc())
    if sort is BrowseSort.oldest:
        return (catalog.c.release_date.asc().nullslast(), title.asc(), *tie_breakers)
    if sort is BrowseSort.title_asc:
        return (title.asc(), catalog.c.release_date.desc().nullslast(), *tie_breakers)
    if sort is BrowseSort.title_desc:
        return (title.desc(), catalog.c.release_date.desc().nullslast(), *tie_breakers)
    return (catalog.c.release_date.desc().nullslast(), title.asc(), *tie_breakers)


def _to_title_result(kind: str, record: Movie | Series) -> UniversalTitleResult:
    seasons = record.seasons if kind == "series" else []
    return UniversalTitleResult(
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


def _options(rows, labeler=None) -> list[BrowseFacetOption]:
    result = []
    for row in rows:
        value = row.value
        if value is None or value == "":
            continue
        label = row.label if hasattr(row, "label") and row.label else None
        if label is None:
            label = labeler(value) if labeler else str(value)
        result.append(BrowseFacetOption(value=str(value), label=str(label), count=row.count))
    return result


def _value_options(db: Session, catalog, column, *, labeler=None):
    rows = db.execute(
        select(column.label("value"), func.count().label("count"))
        .select_from(catalog)
        .where(column.is_not(None), cast(column, String) != "")
        .group_by(column)
        .order_by(func.count().desc(), column)
        .limit(FACET_OPTION_LIMIT)
    )
    return _options(rows, labeler)


def _locale_options(db: Session, catalog, column, model):
    rows = db.execute(
        select(
            column.label("value"),
            model.name.label("label"),
            func.count().label("count"),
        )
        .select_from(catalog)
        .outerjoin(model, model.code == column)
        .where(column.is_not(None))
        .group_by(column, model.name)
        .order_by(func.count().desc(), model.name, column)
        .limit(FACET_OPTION_LIMIT)
    )
    return _options(rows)


def _named_relation_options(db: Session, catalog, model, movie_table, series_table=None):
    relation_key = f"{model.__tablename__.removesuffix('s')}_id"
    statements = [
        select(
            model.slug.label("value"),
            model.name.label("label"),
            movie_table.c.movie_id.label("title_id"),
            literal("movie").label("kind"),
        )
        .join(movie_table, model.id == movie_table.c[relation_key])
        .where(movie_table.c.movie_id.in_(select(catalog.c.id).where(catalog.c.kind == "movie")))
    ]
    if series_table is not None:
        statements.append(
            select(
                model.slug.label("value"),
                model.name.label("label"),
                series_table.c.series_id.label("title_id"),
                literal("series").label("kind"),
            )
            .join(series_table, model.id == series_table.c[relation_key])
            .where(
                series_table.c.series_id.in_(select(catalog.c.id).where(catalog.c.kind == "series"))
            )
        )
    associations = union_all(*statements).subquery()
    rows = db.execute(
        select(
            associations.c.value,
            associations.c.label,
            func.count().label("count"),
        )
        .group_by(associations.c.value, associations.c.label)
        .order_by(func.count().desc(), associations.c.label)
        .limit(FACET_OPTION_LIMIT)
    )
    return _options(rows)


def _character_options(db: Session, catalog):
    movie_ids = select(catalog.c.id).where(catalog.c.kind == "movie")
    series_ids = select(catalog.c.id).where(catalog.c.kind == "series")
    associations = union_all(
        select(
            Character.slug.label("value"),
            Character.name.label("label"),
            Credit.movie_id.label("title_id"),
            literal("movie").label("kind"),
        )
        .join(Credit, Credit.character_id == Character.id)
        .where(Credit.movie_id.in_(movie_ids)),
        select(
            Character.slug.label("value"),
            Character.name.label("label"),
            Credit.series_id.label("title_id"),
            literal("series").label("kind"),
        )
        .join(Credit, Credit.character_id == Character.id)
        .where(Credit.series_id.in_(series_ids)),
        select(
            Character.slug.label("value"),
            Character.name.label("label"),
            Season.series_id.label("title_id"),
            literal("series").label("kind"),
        )
        .join(Credit, Credit.character_id == Character.id)
        .join(Episode, Credit.episode_id == Episode.id)
        .join(Season, Episode.season_id == Season.id)
        .where(Season.series_id.in_(series_ids)),
    ).subquery()
    distinct_titles = (
        select(
            associations.c.value,
            associations.c.label,
            associations.c.title_id,
            associations.c.kind,
        )
        .distinct()
        .subquery()
    )
    rows = db.execute(
        select(
            distinct_titles.c.value,
            distinct_titles.c.label,
            func.count().label("count"),
        )
        .group_by(distinct_titles.c.value, distinct_titles.c.label)
        .order_by(func.count().desc(), distinct_titles.c.label)
        .limit(FACET_OPTION_LIMIT)
    )
    return _options(rows)


def _studio_options(db: Session, catalog):
    studio = func.jsonb_array_elements_text(catalog.c.studios).table_valued(
        "value", joins_implicitly=True
    )
    rows = db.execute(
        select(studio.c.value.label("value"), func.count().label("count"))
        .select_from(catalog, studio)
        .group_by(studio.c.value)
        .order_by(func.count().desc(), studio.c.value)
        .limit(FACET_OPTION_LIMIT)
    )
    return _options(rows)


def _facet_groups(db: Session, catalog) -> list[BrowseFacetGroup]:
    kind = _value_options(
        db,
        catalog,
        catalog.c.kind,
        labeler=lambda value: "Movies" if value == "movie" else "Series",
    )
    content_format = _value_options(
        db,
        catalog,
        catalog.c.content_format,
        labeler=lambda value: {"tv": "TV", "ova": "OVA"}.get(
            value, str(value).replace("_", " ").title()
        ),
    )
    maturity = _value_options(db, catalog, catalog.c.maturity_rating)
    airing_value = case(
        (and_(catalog.c.kind == "series", catalog.c.is_ongoing.is_(True)), "ongoing"),
        (and_(catalog.c.kind == "series", catalog.c.is_ongoing.is_(False)), "completed"),
    )
    airing = _value_options(db, catalog, airing_value, labeler=lambda value: str(value).title())
    genres = _named_relation_options(db, catalog, Genre, movie_genres, series_genres)
    themes = _named_relation_options(db, catalog, Theme, movie_themes)
    tags = _named_relation_options(db, catalog, Tag, movie_tags)
    characters = _character_options(db, catalog)
    languages = _locale_options(db, catalog, catalog.c.original_language_code, Language)
    countries = _locale_options(db, catalog, catalog.c.country_code, Country)
    studios = _studio_options(db, catalog)
    decade_value = cast(func.floor(extract("year", catalog.c.release_date) / 10) * 10, Integer)
    decades = _value_options(db, catalog, decade_value, labeler=lambda value: f"{int(value)}s")
    runtime_value = case(
        (catalog.c.duration_minutes < 30, "short"),
        (catalog.c.duration_minutes.between(30, 90), "standard"),
        (catalog.c.duration_minutes > 90, "long"),
    )
    runtime = _value_options(
        db,
        catalog,
        runtime_value,
        labeler=lambda value: {
            "short": "Under 30 min",
            "standard": "30–90 min",
            "long": "Over 90 min",
        }[value],
    )
    return [
        BrowseFacetGroup(
            key="format",
            label="Format & viewing",
            icon="clapperboard",
            facets=[
                BrowseFacet(key="kind", label="Title type", icon="library", options=kind),
                BrowseFacet(
                    key="content_format",
                    label="Format",
                    icon="monitor-play",
                    options=content_format,
                ),
                BrowseFacet(
                    key="maturity_rating",
                    label="Maturity rating",
                    icon="badge-check",
                    options=maturity,
                ),
                BrowseFacet(
                    key="airing",
                    label="Series status",
                    icon="radio",
                    selection="single",
                    options=airing,
                ),
            ],
        ),
        BrowseFacetGroup(
            key="taste",
            label="Story & taste",
            icon="sparkles",
            facets=[
                BrowseFacet(key="genre", label="Genre", icon="masks", options=genres),
                BrowseFacet(key="theme", label="Theme", icon="orbit", options=themes),
                BrowseFacet(key="tag", label="Mood & detail", icon="tags", options=tags),
                BrowseFacet(
                    key="character",
                    label="Character",
                    icon="drama",
                    options=characters,
                ),
            ],
        ),
        BrowseFacetGroup(
            key="origin",
            label="Origin & craft",
            icon="globe-2",
            facets=[
                BrowseFacet(
                    key="language",
                    label="Original language",
                    icon="languages",
                    options=languages,
                ),
                BrowseFacet(key="country", label="Country", icon="map-pin", options=countries),
                BrowseFacet(key="studio", label="Studio", icon="building-2", options=studios),
            ],
        ),
        BrowseFacetGroup(
            key="time",
            label="Era & duration",
            icon="calendar-range",
            facets=[
                BrowseFacet(
                    key="release_decade",
                    label="Release decade",
                    icon="calendar-days",
                    options=decades,
                ),
                BrowseFacet(
                    key="runtime_band",
                    label="Movie runtime",
                    icon="timer",
                    options=runtime,
                ),
            ],
        ),
    ]


def browse_catalog(db: Session, *, filters: BrowseQuery, country: str | None) -> BrowseResponse:
    statements = _title_statements(filters, country)
    facet_groups: list[BrowseFacetGroup] = []
    if filters.include_facets:
        # Keep options stable while a viewer combines values within a facet. Counts are scoped
        # to the current text search and territory, before advanced refinements are applied.
        facet_statements = _title_statements(BrowseQuery(q=filters.q), country)
        facet_catalog = union_all(*facet_statements).subquery("browse_facet_titles")
        facet_groups = _facet_groups(db, facet_catalog)
    if not statements:
        return BrowseResponse(
            query=filters.q,
            page=filters.page,
            page_size=filters.page_size,
            total=0,
            has_more=False,
            next_page=None,
            sort=filters.sort,
            items=[],
            facet_groups=facet_groups,
        )

    catalog = union_all(*statements).subquery("browse_titles")
    total = db.scalar(select(func.count()).select_from(catalog)) or 0
    offset = (filters.page - 1) * filters.page_size
    page_rows = db.execute(
        select(catalog.c.id, catalog.c.kind)
        .order_by(*_sort_columns(catalog, filters.sort))
        .offset(offset)
        .limit(filters.page_size)
    ).all()

    movie_ids = [row.id for row in page_rows if row.kind == "movie"]
    series_ids = [row.id for row in page_rows if row.kind == "series"]
    records: dict[tuple[str, object], Movie | Series] = {}
    if movie_ids:
        movies = db.scalars(movie_query().where(Movie.id.in_(movie_ids))).unique()
        records.update({("movie", record.id): record for record in movies})
    if series_ids:
        series = db.scalars(
            series_query()
            .options(
                with_loader_criteria(
                    Episode, Episode.status == CatalogStatus.published, include_aliases=True
                )
            )
            .where(Series.id.in_(series_ids))
        ).unique()
        records.update({("series", record.id): record for record in series})
    items = [
        _to_title_result(row.kind, records[(row.kind, row.id)])
        for row in page_rows
        if (row.kind, row.id) in records
    ]
    has_more = offset + len(items) < total
    return BrowseResponse(
        query=filters.q,
        page=filters.page,
        page_size=filters.page_size,
        total=total,
        has_more=has_more,
        next_page=filters.page + 1 if has_more else None,
        sort=filters.sort,
        items=items,
        facet_groups=facet_groups,
    )
