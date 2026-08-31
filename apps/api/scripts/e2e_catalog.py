#!/usr/bin/env python3
"""Inspect or remove isolated Playwright catalog records."""

import json
import sys
from pathlib import Path

from sqlalchemy import delete, select

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e_guard import require_e2e_test_environment  # noqa: E402

from app.catalog_models import Character, Company, Movie, Person, Series  # noqa: E402
from app.curation_models import Collection, Journey  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def main() -> None:
    require_e2e_test_environment()
    command = json.load(sys.stdin)
    prefix = str(command["slug_prefix"])
    if not prefix.startswith("e2e-studio-draft-"):
        raise ValueError("Refusing to operate outside the E2E catalog namespace")
    with SessionLocal() as db:
        if command["action"] == "inspect":
            movie = db.scalar(select(Movie).where(Movie.slug == command["slug"]))
            print(
                json.dumps(
                    None
                    if movie is None
                    else {
                        "id": str(movie.id),
                        "title": movie.title,
                        "slug": movie.slug,
                        "status": movie.status.value,
                    }
                )
            )
            return
        if command["action"] == "inspect_series":
            series = db.scalar(select(Series).where(Series.slug == command["slug"]))
            print(
                json.dumps(
                    None
                    if series is None
                    else {
                        "id": str(series.id),
                        "title": series.title,
                        "slug": series.slug,
                        "status": series.status.value,
                        "season_count": len(series.seasons),
                        "episode_count": sum(len(season.episodes) for season in series.seasons),
                    }
                )
            )
            return
        if command["action"] == "delete_prefix":
            collection_result = db.execute(
                delete(Collection).where(Collection.slug.startswith(prefix))
            )
            journey_result = db.execute(delete(Journey).where(Journey.slug.startswith(prefix)))
            result = db.execute(delete(Movie).where(Movie.slug.startswith(prefix)))
            series_result = db.execute(delete(Series).where(Series.slug.startswith(prefix)))
            person_result = db.execute(delete(Person).where(Person.slug.startswith(prefix)))
            company_result = db.execute(delete(Company).where(Company.slug.startswith(prefix)))
            character_result = db.execute(
                delete(Character).where(Character.slug.startswith(prefix))
            )
            db.commit()
            print(
                json.dumps(
                    {
                        "deleted": result.rowcount
                        + collection_result.rowcount
                        + journey_result.rowcount
                        + series_result.rowcount
                        + person_result.rowcount
                        + company_result.rowcount
                        + character_result.rowcount
                    }
                )
            )
            return
        raise ValueError("Unknown action")


if __name__ == "__main__":
    main()
