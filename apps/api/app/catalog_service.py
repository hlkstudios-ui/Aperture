import uuid
from collections.abc import Sequence
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel
from sqlalchemy import Select, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.catalog_models import (
    Genre,
    Movie,
    Season,
    Series,
    Tag,
    Theme,
)
from app.catalog_schemas import MovieCreate, MovieUpdate, SeriesCreate, SeriesUpdate


def get_or_404[CatalogRecord](
    db: Session, model: type[CatalogRecord], record_id: Any
) -> CatalogRecord:
    record = db.get(model, record_id)
    if record is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} was not found")
    return record


def resolve_ids[CatalogRecord](
    db: Session, model: type[CatalogRecord], record_ids: Sequence[uuid.UUID]
) -> list[CatalogRecord]:
    unique_ids = list(dict.fromkeys(record_ids))
    if not unique_ids:
        return []
    records = list(db.scalars(select(model).where(model.id.in_(unique_ids))).all())
    if len(records) != len(unique_ids):
        found = {record.id for record in records}
        missing = next(record_id for record_id in unique_ids if record_id not in found)
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"{model.__name__} reference {missing} was not found",
        )
    by_id = {record.id: record for record in records}
    return [by_id[record_id] for record_id in unique_ids]


def commit(db: Session, conflict_message: str) -> None:
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, conflict_message) from error


def movie_query() -> Select[tuple[Movie]]:
    return select(Movie).options(
        selectinload(Movie.genres), selectinload(Movie.themes), selectinload(Movie.tags)
    )


def series_query() -> Select[tuple[Series]]:
    return select(Series).options(
        selectinload(Series.genres),
        selectinload(Series.seasons).selectinload(Season.episodes),
    )


def create_movie(db: Session, payload: MovieCreate) -> Movie:
    values = payload.model_dump(exclude={"genre_ids", "theme_ids", "tag_ids"})
    movie = Movie(**values)
    movie.genres = resolve_ids(db, Genre, payload.genre_ids)
    movie.themes = resolve_ids(db, Theme, payload.theme_ids)
    movie.tags = resolve_ids(db, Tag, payload.tag_ids)
    db.add(movie)
    commit(db, "A movie with this slug or metadata combination already exists")
    return db.scalar(movie_query().where(Movie.id == movie.id))


def update_movie(db: Session, movie: Movie, payload: MovieUpdate) -> Movie:
    values = payload.model_dump(exclude_unset=True)
    for field, model in (("genre_ids", Genre), ("theme_ids", Theme), ("tag_ids", Tag)):
        ids = values.pop(field, None)
        if ids is not None:
            setattr(movie, field.removesuffix("_ids") + "s", resolve_ids(db, model, ids))
    for field, value in values.items():
        setattr(movie, field, value)
    commit(db, "A movie with this slug or metadata combination already exists")
    return db.scalar(movie_query().where(Movie.id == movie.id))


def create_series(db: Session, payload: SeriesCreate) -> Series:
    values = payload.model_dump(exclude={"genre_ids"})
    series = Series(**values)
    series.genres = resolve_ids(db, Genre, payload.genre_ids)
    db.add(series)
    commit(db, "A series with this slug or metadata combination already exists")
    return db.scalar(series_query().where(Series.id == series.id))


def update_series(db: Session, series: Series, payload: SeriesUpdate) -> Series:
    values = payload.model_dump(exclude_unset=True)
    genre_ids = values.pop("genre_ids", None)
    if genre_ids is not None:
        series.genres = resolve_ids(db, Genre, genre_ids)
    for field, value in values.items():
        setattr(series, field, value)
    commit(db, "A series with this slug or metadata combination already exists")
    return db.scalar(series_query().where(Series.id == series.id))


def apply_update(record: Any, payload: BaseModel) -> None:
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(record, field, value)
