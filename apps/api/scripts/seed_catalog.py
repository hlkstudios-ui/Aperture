#!/usr/bin/env python3
"""Idempotently seed the minimal licensed/generated development catalog."""

import sys
from datetime import date
from pathlib import Path

from sqlalchemy import select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog_models import (  # noqa: E402
    CatalogStatus,
    Country,
    Episode,
    Genre,
    Language,
    Movie,
    Season,
    Series,
)
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def seed() -> None:
    settings = get_settings()
    if settings.app_env not in {"development", "test"}:
        raise RuntimeError("Catalog seed is restricted to development and test environments")

    with SessionLocal() as db:
        language = db.get(Language, "en")
        if language is None:
            language = Language(code="en", name="English")
            db.add(language)
        country = db.get(Country, "CA")
        if country is None:
            country = Country(code="CA", name="Canada")
            db.add(country)
        genre = db.scalar(select(Genre).where(Genre.slug == "speculative-drama"))
        if genre is None:
            genre = Genre(name="Speculative Drama", slug="speculative-drama")
            db.add(genre)
        db.flush()

        movie = db.scalar(select(Movie).where(Movie.slug == "the-lantern-sea"))
        if movie is None:
            movie = Movie(
                title="The Lantern Sea",
                slug="the-lantern-sea",
                short_description="A cartographer follows a light beyond the known coast.",
                synopsis=(
                    "An original development-only catalog record created to exercise discovery "
                    "without relying on unlicensed commercial metadata."
                ),
                release_date=date(2026, 8, 15),
                runtime_minutes=104,
                maturity_rating="PG",
                status=CatalogStatus.published,
                original_language_code="en",
                country_code="CA",
                genres=[genre],
            )
            db.add(movie)
        else:
            movie.release_date = date(2026, 8, 15)

        series = db.scalar(select(Series).where(Series.slug == "harbor-signals"))
        if series is None:
            series = Series(
                title="Harbor Signals",
                slug="harbor-signals",
                short_description="Signals cross a quiet harbor after midnight.",
                synopsis=(
                    "An original development-only episodic record for testing series hierarchy."
                ),
                release_date=date(2026, 8, 15),
                maturity_rating="TV-PG",
                status=CatalogStatus.published,
                original_language_code="en",
                country_code="CA",
                genres=[genre],
            )
            season = Season(number=1, title="First Light")
            season.episodes.append(
                Episode(
                    number=1,
                    title="The Bell",
                    synopsis="A bell rings across an empty harbor.",
                    runtime_minutes=42,
                    status=CatalogStatus.published,
                )
            )
            series.seasons.append(season)
            db.add(series)
        else:
            series.release_date = date(2026, 8, 15)

        db.commit()
        print("Development catalog seed is ready.")


if __name__ == "__main__":
    seed()
