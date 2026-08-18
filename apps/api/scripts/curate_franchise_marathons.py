#!/usr/bin/env python3
"""Import and publish ordered franchise-marathon rails for local development."""

import os
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.catalog_models import CatalogStatus, Movie  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.models import HomepageConfiguration  # noqa: E402
from scripts.import_tmdb_catalog import (  # noqa: E402
    IMAGE,
    load_root_env,
    parsed_date,
    rating,
    slugify,
    tmdb_get,
    upsert_genres,
    upsert_locale,
)

MARATHONS = (
    (
        "saw-marathon",
        "Every trap has a beginning — The Saw Marathon",
        "Ten chapters. No shortcuts. Follow the game in release order.",
        (176, 215, 214, 663, 11917, 22804, 41439, 298250, 602734, 951491),
    ),
    (
        "mcu-infinity-saga",
        "Before the snap — The Infinity Saga",
        "From Iron Man's first flight to the final stand against Thanos.",
        (
            1726,
            1724,
            10138,
            10195,
            1771,
            24428,
            68721,
            76338,
            100402,
            118340,
            99861,
            102899,
            271110,
            284052,
            283995,
            315635,
            284053,
            284054,
            299536,
            363088,
            299537,
            299534,
        ),
    ),
    (
        "mission-impossible",
        "Your mission, should you choose the whole saga",
        "Every impossible operation, in release order.",
        (954, 955, 956, 56292, 177677, 353081, 575264, 575265),
    ),
    (
        "middle-earth",
        "There and back again — A Middle-earth journey",
        "Begin in the Shire and follow the story through the end of the Third Age.",
        (49051, 57158, 122917, 120, 121, 122),
    ),
)


def import_movie(db, client: httpx.Client, external_id: int) -> Movie:
    details = tmdb_get(
        client,
        f"/movie/{external_id}",
        append_to_response="release_dates,keywords",
        language=os.getenv("TMDB_LANGUAGE", "en-CA"),
    )
    record = db.scalar(
        select(Movie).where(
            Movie.metadata_provider == "tmdb", Movie.external_id == str(external_id)
        )
    )
    title = details["title"]
    overview = (details.get("overview") or f"No synopsis is available for {title}.").strip()
    language_code, country_code = upsert_locale(db, details)
    if record is None:
        record = Movie(
            title=title,
            slug=f"{slugify(title)}-tmdb-{external_id}",
            short_description=overview[:500],
            synopsis=overview,
            runtime_minutes=max(1, details.get("runtime") or 1),
            status=CatalogStatus.published,
            metadata_provider="tmdb",
            external_id=str(external_id),
        )
        db.add(record)
    record.title = title
    original_title = details.get("original_title")
    record.original_title = original_title if original_title != title else None
    record.short_description = overview[:500]
    record.synopsis = overview
    record.release_date = parsed_date(details.get("release_date"))
    record.runtime_minutes = max(1, details.get("runtime") or record.runtime_minutes)
    record.maturity_rating = rating(details, "movie")
    record.status = CatalogStatus.published
    record.original_language_code = language_code
    record.country_code = country_code
    record.poster_url = f"{IMAGE}{details['poster_path']}" if details.get("poster_path") else None
    record.backdrop_url = (
        f"{IMAGE}{details['backdrop_path']}" if details.get("backdrop_path") else None
    )
    record.content_format = "movie"
    record.studios = [
        item["name"] for item in details.get("production_companies", []) if item.get("name")
    ][:12]
    record.genres = upsert_genres(db, details.get("genres", []))
    db.flush()
    return record


def main() -> None:
    load_root_env()
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("Franchise curation is restricted to development and test")
    token = os.getenv("TMDB_API_READ_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("TMDB_API_READ_ACCESS_TOKEN is missing")
    with (
        httpx.Client(
            headers={"Authorization": f"Bearer {token}", "accept": "application/json"}, timeout=30
        ) as client,
        SessionLocal() as db,
    ):
        rails = []
        for position, (key, title, eyebrow, ids) in enumerate(MARATHONS):
            records = [import_movie(db, client, external_id) for external_id in ids]
            rails.append(
                {
                    "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"aperture:marathon:{key}")),
                    "title": title,
                    "eyebrow": eyebrow,
                    "source": "pinned",
                    "query": None,
                    "position": position,
                    "enabled": True,
                    "starts_at": None,
                    "ends_at": None,
                    "items": [
                        {"kind": "movie", "id": str(record.id), "position": index}
                        for index, record in enumerate(records)
                    ],
                }
            )
        config = db.scalar(select(HomepageConfiguration))
        if config is None:
            config = HomepageConfiguration()
            db.add(config)
            db.flush()
        marathon_ids = {rail["id"] for rail in rails}
        existing = [
            rail
            for rail in (config.published_snapshot or {}).get("rails", [])
            if rail.get("id") not in marathon_ids
        ]
        for index, rail in enumerate([*rails, *existing]):
            rail["position"] = index
        current_hero = (config.published_snapshot or {}).get("hero")
        config.published_snapshot = {
            "hero": current_hero or rails[0]["items"][0],
            "rails": [*rails, *existing],
        }
        config.published_at = datetime.now(UTC)
        db.commit()
        placement_count = sum(len(rail["items"]) for rail in rails)
        print(
            f"Published {len(rails)} franchise marathons with "
            f"{placement_count} ordered placements."
        )


if __name__ == "__main__":
    main()
