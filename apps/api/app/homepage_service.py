import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload, selectinload

from app.catalog_models import Country, Credit, Movie, Person, Series
from app.curation_models import Collection, CollectionKind, CurationStatus
from app.homepage_schemas import HomepagePublicRail, HomepagePublicResponse, HomepageTitle
from app.models import HomepageConfiguration, HomepageRail
from app.scheduling import availability_clause, synchronize_due_schedules, utc_now


def get_configuration(db: Session) -> HomepageConfiguration:
    config = (
        db.scalars(
            select(HomepageConfiguration).options(
                joinedload(HomepageConfiguration.rails).joinedload(HomepageRail.items)
            )
        )
        .unique()
        .first()
    )
    if config is None:
        config = HomepageConfiguration()
        db.add(config)
        db.commit()
        db.refresh(config)
    return config


def draft_snapshot(config: HomepageConfiguration) -> dict[str, Any]:
    hero = None
    if config.draft_hero_movie_id:
        hero = {"kind": "movie", "id": str(config.draft_hero_movie_id)}
    elif config.draft_hero_series_id:
        hero = {"kind": "series", "id": str(config.draft_hero_series_id)}
    return {
        "hero": hero,
        "rails": [
            {
                "id": str(rail.id),
                "title": rail.title,
                "eyebrow": rail.eyebrow,
                "source": rail.source.value,
                "query": rail.query,
                "position": rail.position,
                "enabled": rail.enabled,
                "starts_at": rail.starts_at.isoformat() if rail.starts_at else None,
                "ends_at": rail.ends_at.isoformat() if rail.ends_at else None,
                "items": [
                    {
                        "kind": "movie" if item.movie_id else "series",
                        "id": str(item.movie_id or item.series_id),
                        "position": item.position,
                    }
                    for item in rail.items
                ],
            }
            for rail in config.rails
        ],
    }


def _title(record: Movie | Series) -> HomepageTitle:
    return HomepageTitle(
        id=record.id,
        kind="movie" if isinstance(record, Movie) else "series",
        title=record.title,
        slug=record.slug,
        short_description=record.short_description,
        maturity_rating=record.maturity_rating,
        runtime_minutes=record.runtime_minutes if isinstance(record, Movie) else None,
        poster_url=record.poster_url,
        backdrop_url=record.backdrop_url,
        metadata_provider=record.metadata_provider,
    )


def _pinned_records(
    db: Session,
    snapshot: dict[str, Any],
    preview: bool,
    country: str | None,
) -> dict[tuple[str, str], Movie | Series]:
    ids: dict[str, set[uuid.UUID]] = {"movie": set(), "series": set()}
    references = [
        snapshot.get("hero"),
        *(item for rail in snapshot.get("rails", []) for item in rail.get("items", [])),
    ]
    for reference in references:
        if not reference or reference.get("kind") not in ids:
            continue
        try:
            ids[reference["kind"]].add(uuid.UUID(reference["id"]))
        except (KeyError, TypeError, ValueError):
            continue

    records: dict[tuple[str, str], Movie | Series] = {}
    for kind, model in (("movie", Movie), ("series", Series)):
        if not ids[kind]:
            continue
        statement = select(model).where(model.id.in_(ids[kind]))
        if not preview:
            statement = statement.where(availability_clause(model, country=country))
        for record in db.scalars(statement):
            records[(kind, str(record.id))] = record
    return records


def _dynamic(
    db: Session,
    source: str,
    query: str | None,
    preview: bool,
    country: str | None,
) -> list[Movie | Series]:
    models: tuple[type[Movie] | type[Series], ...]
    if source == "latest_movies":
        models = (Movie,)
    elif source == "latest_series":
        models = (Series,)
    elif source == "mixed":
        models = (Movie, Series)
    else:
        return []
    records: list[Movie | Series] = []
    for model in models:
        statement = select(model)
        if not preview:
            statement = statement.where(availability_clause(model, country=country))
        if query == "provider:tmdb":
            statement = statement.where(model.metadata_provider == "tmdb")
        elif query:
            pattern = f"%{query.strip()}%"
            statement = statement.where(
                or_(model.title.ilike(pattern), model.short_description.ilike(pattern))
            )
        records.extend(
            db.scalars(statement.order_by(model.release_date.desc().nullslast()).limit(20))
        )
    records.sort(key=lambda item: item.release_date or datetime.min.date(), reverse=True)
    return records[:20]


def render_homepage(
    db: Session,
    snapshot: dict[str, Any] | None,
    *,
    preview: bool = False,
    published_at: datetime | None = None,
    country: str | None = None,
) -> HomepagePublicResponse:
    if not preview:
        synchronize_due_schedules(db)
    if not snapshot:
        return HomepagePublicResponse(hero=None, rails=[], published_at=published_at)
    pinned_records = _pinned_records(db, snapshot, preview, country)
    hero_data = snapshot.get("hero")
    hero_record = pinned_records.get((hero_data["kind"], hero_data["id"])) if hero_data else None
    now = utc_now()
    rails: list[HomepagePublicRail] = []
    for rail in sorted(snapshot.get("rails", []), key=lambda value: value["position"]):
        starts_at = datetime.fromisoformat(rail["starts_at"]) if rail.get("starts_at") else None
        ends_at = datetime.fromisoformat(rail["ends_at"]) if rail.get("ends_at") else None
        if not preview and (
            not rail["enabled"] or (starts_at and starts_at > now) or (ends_at and ends_at <= now)
        ):
            continue
        seen: set[uuid.UUID] = set()
        items: list[HomepageTitle] = []
        for item in sorted(rail.get("items", []), key=lambda value: value["position"]):
            record = pinned_records.get((item["kind"], item["id"]))
            if record and record.id not in seen:
                items.append(_title(record))
                seen.add(record.id)
        for record in _dynamic(db, rail["source"], rail.get("query"), preview, country):
            if record.id not in seen:
                items.append(_title(record))
                seen.add(record.id)
        if items or preview:
            rails.append(
                HomepagePublicRail(
                    id=uuid.UUID(rail["id"]),
                    title=rail["title"],
                    eyebrow=rail.get("eyebrow"),
                    items=items,
                )
            )
    return HomepagePublicResponse(
        hero=_title(hero_record) if hero_record else None,
        rails=rails,
        published_at=published_at,
    )


def _stable_rail_id(key: str) -> uuid.UUID:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"aperture:no-algorithm:{key}")


def _rail(key: str, title: str, eyebrow: str, records: list[Movie | Series]):
    return HomepagePublicRail(
        id=_stable_rail_id(key),
        title=title,
        eyebrow=eyebrow,
        items=[_title(record) for record in records[:20]],
    )


def render_no_algorithm_homepage(db: Session, country: str | None = None) -> HomepagePublicResponse:
    """Render transparent, deterministic catalog indexes without behavioral ranking."""
    synchronize_due_schedules(db)
    movies = list(
        db.scalars(
            select(Movie)
            .options(selectinload(Movie.genres))
            .where(availability_clause(Movie, country=country))
        ).unique()
    )
    series = list(
        db.scalars(
            select(Series)
            .options(selectinload(Series.genres))
            .where(availability_clause(Series, country=country))
        ).unique()
    )
    titles: list[Movie | Series] = [*movies, *series]
    alphabetical = sorted(titles, key=lambda item: (item.title.casefold(), str(item.id)))
    newest = sorted(
        titles,
        key=lambda item: (
            item.created_at,
            item.title.casefold(),
            str(item.id),
        ),
        reverse=True,
    )
    by_year = sorted(
        titles,
        key=lambda item: (
            item.release_date.year if item.release_date else -1,
            item.title.casefold(),
            str(item.id),
        ),
        reverse=True,
    )
    rails = [
        _rail("new", "Recently added", "Newest catalog entries", newest),
        _rail("az", "A–Z", "Alphabetical title index", alphabetical),
        _rail("year", "Release year", "Newest release year first", by_year),
    ]

    title_lookup = {(type(item).__name__.lower(), item.id): item for item in titles}
    director_groups: dict[str, list[Movie | Series]] = {}
    for person, credit in db.execute(
        select(Person, Credit)
        .join(Credit, Credit.person_id == Person.id)
        .where(Credit.role.ilike("%director%"))
        .order_by(Person.name, Credit.billing_order.asc().nullslast(), Credit.id)
    ):
        key = "movie" if credit.movie_id else "series" if credit.series_id else ""
        record = title_lookup.get((key, credit.movie_id or credit.series_id))
        if record and record not in director_groups.setdefault(person.name, []):
            director_groups[person.name].append(record)
    for name in sorted(director_groups, key=str.casefold):
        rails.append(_rail(f"director:{name}", name, "Browse by director", director_groups[name]))

    country_names = {row.code: row.name for row in db.scalars(select(Country))}
    country_groups: dict[str, list[Movie | Series]] = {}
    for record in alphabetical:
        if record.country_code:
            country_name = country_names.get(record.country_code, record.country_code)
            country_groups.setdefault(country_name, []).append(record)
    for name in sorted(country_groups, key=str.casefold):
        rails.append(_rail(f"country:{name}", name, "Browse by country", country_groups[name]))

    genre_groups: dict[str, list[Movie | Series]] = {}
    for record in alphabetical:
        for genre in record.genres:
            genre_groups.setdefault(genre.name, []).append(record)
    for name in sorted(genre_groups, key=str.casefold):
        rails.append(_rail(f"genre:{name}", name, "Browse by genre", genre_groups[name]))

    collections = db.scalars(
        select(Collection)
        .options(selectinload(Collection.items))
        .where(
            Collection.status == CurationStatus.published,
            Collection.kind != CollectionKind.user_list,
        )
        .order_by(Collection.title, Collection.id)
    ).unique()
    for collection in collections:
        records = []
        for item in collection.items:
            kind = "movie" if item.movie_id else "series"
            record = title_lookup.get((kind, item.movie_id or item.series_id))
            if record:
                records.append(record)
        if records:
            rails.append(
                _rail(
                    f"collection:{collection.id}",
                    collection.title,
                    "Browse by collection",
                    records,
                )
            )
    return HomepagePublicResponse(
        hero=_title(newest[0]) if newest else None,
        rails=rails,
        published_at=None,
        mode="no_algorithm",
        strategy="deterministic_catalog_indexes_v1",
    )
