import uuid
from collections.abc import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload, with_loader_criteria

from app.catalog_models import CatalogStatus, Episode, Movie, Series
from app.catalog_service import movie_query, series_query
from app.catalog_visibility import public_title_conditions
from app.explore_models import ExploreEntry, ExploreEntryCard
from app.explore_schemas import (
    ExploreCardResponse,
    ExploreEntryPublicResponse,
    ExploreEntryResponse,
)
from app.scheduling import synchronize_due_schedules
from app.search_schemas import UniversalTitleResult


def load_explore_entries(db: Session, *, enabled_only: bool = False) -> list[ExploreEntry]:
    statement = select(ExploreEntry).options(selectinload(ExploreEntry.cards))
    if enabled_only:
        statement = statement.where(ExploreEntry.enabled.is_(True))
    return list(
        db.scalars(statement.order_by(ExploreEntry.position, ExploreEntry.created_at)).unique()
    )


def load_explore_entry(db: Session, entry_id: uuid.UUID) -> ExploreEntry | None:
    return db.scalar(
        select(ExploreEntry)
        .options(selectinload(ExploreEntry.cards))
        .where(ExploreEntry.id == entry_id)
    )


def _title_result(record: Movie | Series) -> UniversalTitleResult:
    is_series = isinstance(record, Series)
    seasons = record.seasons if is_series else []
    episodes = [episode for season in seasons for episode in season.episodes]
    average_runtime = (
        round(sum(episode.runtime_minutes for episode in episodes) / len(episodes))
        if episodes
        else None
    )
    kind = "series" if is_series else "movie"
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
        duration_minutes=average_runtime if is_series else record.runtime_minutes,
        is_ongoing=record.is_ongoing if is_series else None,
        season_count=len(seasons),
        episode_count=len(episodes),
        href=f"/{'series' if is_series else 'movies'}/{record.slug}",
    )


def _records_for_cards(
    db: Session,
    cards: Sequence[ExploreEntryCard],
    *,
    public: bool,
    country: str | None,
) -> dict[tuple[str, uuid.UUID], Movie | Series]:
    movie_ids = {card.movie_id for card in cards if card.movie_id is not None}
    series_ids = {card.series_id for card in cards if card.series_id is not None}
    records: dict[tuple[str, uuid.UUID], Movie | Series] = {}
    if movie_ids:
        statement = movie_query().where(Movie.id.in_(movie_ids))
        if public:
            statement = statement.where(*public_title_conditions(Movie, country=country))
        records.update({("movie", record.id): record for record in db.scalars(statement).unique()})
    if series_ids:
        statement = series_query().where(Series.id.in_(series_ids))
        if public:
            statement = statement.options(
                with_loader_criteria(
                    Episode,
                    Episode.status == CatalogStatus.published,
                    include_aliases=True,
                )
            ).where(*public_title_conditions(Series, country=country))
        records.update({("series", record.id): record for record in db.scalars(statement).unique()})
    return records


def _card_responses(
    db: Session,
    cards: Sequence[ExploreEntryCard],
    *,
    public: bool,
    country: str | None,
) -> list[ExploreCardResponse]:
    ordered = sorted(cards, key=lambda card: (card.position, card.created_at, card.id))
    records = _records_for_cards(db, ordered, public=public, country=country)
    return _card_responses_from_records(ordered, records)


def _card_responses_from_records(
    cards: Sequence[ExploreEntryCard],
    records: dict[tuple[str, uuid.UUID], Movie | Series],
) -> list[ExploreCardResponse]:
    responses: list[ExploreCardResponse] = []
    for card in sorted(cards, key=lambda value: (value.position, value.created_at, value.id)):
        kind = "movie" if card.movie_id is not None else "series"
        title_id = card.movie_id or card.series_id
        record = records.get((kind, title_id)) if title_id is not None else None
        if record is None:
            continue
        responses.append(
            ExploreCardResponse(
                id=card.id,
                movie_id=card.movie_id,
                series_id=card.series_id,
                position=card.position,
                title=_title_result(record),
            )
        )
    return responses


def admin_card_responses(
    db: Session, cards: Sequence[ExploreEntryCard]
) -> list[ExploreCardResponse]:
    return _card_responses(db, cards, public=False, country=None)


def admin_entry_responses(
    db: Session, entries: Sequence[ExploreEntry] | None = None
) -> list[ExploreEntryResponse]:
    entry_records = list(entries) if entries is not None else load_explore_entries(db)
    cards = [card for entry in entry_records for card in entry.cards]
    title_records = _records_for_cards(db, cards, public=False, country=None)
    return [
        ExploreEntryResponse(
            id=entry.id,
            label=entry.label,
            description=entry.description,
            icon=entry.icon,
            position=entry.position,
            enabled=entry.enabled,
            criteria=entry.criteria,
            cards=_card_responses_from_records(entry.cards, title_records),
            created_at=entry.created_at,
            updated_at=entry.updated_at,
        )
        for entry in entry_records
    ]


def public_entry_responses(db: Session, *, country: str | None) -> list[ExploreEntryPublicResponse]:
    synchronize_due_schedules(db)
    entries = load_explore_entries(db, enabled_only=True)
    cards = [card for entry in entries for card in entry.cards]
    visible_records = _records_for_cards(db, cards, public=True, country=country)
    responses: list[ExploreEntryPublicResponse] = []
    for entry in entries:
        entry_cards = _card_responses_from_records(entry.cards, visible_records)
        responses.append(
            ExploreEntryPublicResponse(
                id=entry.id,
                label=entry.label,
                description=entry.description,
                icon=entry.icon,
                position=entry.position,
                criteria=entry.criteria,
                cards=entry_cards,
            )
        )
    return responses
