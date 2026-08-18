#!/usr/bin/env python3
"""Idempotently import display metadata from TMDB into the local catalog."""

import argparse
import os
import re
import sys
import uuid
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
from sqlalchemy import select

ROOT = Path(__file__).resolve().parents[3]
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
from app.models import HomepageConfiguration  # noqa: E402

API = "https://api.themoviedb.org/3"
IMAGE = "https://image.tmdb.org/t/p/original"


def load_root_env() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return slug[:220] or "untitled"


def parsed_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def rating(details: dict, kind: str) -> str | None:
    if kind == "movie":
        entries = details.get("release_dates", {}).get("results", [])
        for region in ("CA", "US"):
            item = next((row for row in entries if row.get("iso_3166_1") == region), None)
            if item:
                value = next(
                    (
                        x.get("certification")
                        for x in item.get("release_dates", [])
                        if x.get("certification")
                    ),
                    None,
                )
                if value:
                    return value
    else:
        entries = details.get("content_ratings", {}).get("results", [])
        for region in ("CA", "US"):
            item = next(
                (row for row in entries if row.get("iso_3166_1") == region and row.get("rating")),
                None,
            )
            if item:
                return item["rating"]
    return None


def upsert_locale(db, details: dict) -> tuple[str | None, str | None]:
    language_code = details.get("original_language")
    if language_code and db.get(Language, language_code) is None:
        language = next(
            (x for x in details.get("spoken_languages", []) if x.get("iso_639_1") == language_code),
            {},
        )
        db.add(
            Language(code=language_code, name=language.get("english_name") or language_code.upper())
        )
    countries = details.get("production_countries") or []
    country_code = (countries[0].get("iso_3166_1") if countries else None) or (
        details.get("origin_country") or [None]
    )[0]
    if country_code and db.get(Country, country_code) is None:
        country = next((x for x in countries if x.get("iso_3166_1") == country_code), {})
        db.add(Country(code=country_code, name=country.get("name") or country_code))
    return language_code, country_code


def upsert_genres(db, values: list[dict]) -> list[Genre]:
    output = []
    for value in values:
        slug = slugify(value["name"])
        genre = db.scalar(select(Genre).where(Genre.slug == slug))
        if genre is None:
            genre = Genre(name=value["name"], slug=slug)
            db.add(genre)
            db.flush()
        output.append(genre)
    return output


def tmdb_get(client: httpx.Client, path: str, **params) -> dict:
    response = client.get(f"{API}{path}", params=params)
    response.raise_for_status()
    return response.json()


GLOBAL_MARKETS = (
    ("en", "US"),
    ("ko", "KR"),
    ("hi", "IN"),
    ("fr", "FR"),
    ("es", "MX"),
    ("zh", "HK"),
)


def discovery_rows(client: httpx.Client, kind: str, limit: int, scope: str) -> list[dict]:
    endpoint = "/discover/movie" if kind == "movie" else "/discover/tv"
    common = dict(
        sort_by="popularity.desc",
        include_adult="false",
        language=os.getenv("TMDB_LANGUAGE", "en-CA"),
        page=1,
    )
    queries: list[dict] = []
    if scope in {"anime", "mixed"}:
        queries.append({"with_genres": "16", "with_original_language": "ja", "region": "JP"})
    if scope in {"global", "mixed"}:
        queries.append({"region": os.getenv("TMDB_REGION", "CA")})
        queries.extend(
            {"with_original_language": language, "region": region}
            for language, region in GLOBAL_MARKETS
        )
        queries.extend(({"with_genres": "99"}, {"with_genres": "27"}, {"with_genres": "878"}))
    pools = [tmdb_get(client, endpoint, **common, **query).get("results", []) for query in queries]
    result_rows: list[dict] = []
    seen: set[int] = set()
    while pools and len(result_rows) < limit:
        remaining = []
        for pool in pools:
            while pool and pool[0].get("id") in seen:
                pool.pop(0)
            if pool:
                row = pool.pop(0)
                seen.add(row["id"])
                result_rows.append(row)
                remaining.append(pool)
                if len(result_rows) >= limit:
                    break
        pools = remaining
    if kind == "tv" and scope in {"anime", "mixed"} and limit >= 3:
        keyword_search = tmdb_get(
            client,
            "/search/keyword",
            query="original video animation",
            page=1,
        )
        keyword = next(iter(keyword_search.get("results", [])), None)
        if keyword:
            ova_rows = tmdb_get(
                client,
                endpoint,
                with_genres="16",
                with_original_language="ja",
                with_keywords=str(keyword["id"]),
                sort_by="popularity.desc",
                include_adult="false",
                language=os.getenv("TMDB_LANGUAGE", "en-CA"),
                page=1,
            ).get("results", [])[:3]
            combined = [*result_rows[: max(0, limit - len(ova_rows))], *ova_rows]
            result_rows = list({row["id"]: row for row in combined}.values())[:limit]
    return result_rows


def import_kind(
    db, client: httpx.Client, kind: str, limit: int, scope: str
) -> list[Movie | Series]:
    result_rows = discovery_rows(client, kind, limit, scope)
    imported: list[Movie | Series] = []
    for item in result_rows:
        external_id = str(item["id"])
        append = "release_dates,keywords" if kind == "movie" else "content_ratings,keywords"
        details = tmdb_get(
            client,
            f"/{kind}/{external_id}",
            append_to_response=append,
            language=os.getenv("TMDB_LANGUAGE", "en-CA"),
        )
        title = details.get("title") if kind == "movie" else details.get("name")
        original_title = (
            details.get("original_title") if kind == "movie" else details.get("original_name")
        )
        overview = (
            details.get("overview") or f"No synopsis is currently available for {title}."
        ).strip()
        language_code, country_code = upsert_locale(db, details)
        model = Movie if kind == "movie" else Series
        record = db.scalar(
            select(model).where(model.metadata_provider == "tmdb", model.external_id == external_id)
        )
        if record is None:
            base_slug = f"{slugify(title)}-tmdb-{external_id}"
            common = dict(
                title=title,
                slug=base_slug,
                original_title=original_title if original_title != title else None,
                short_description=overview[:500],
                synopsis=overview,
                release_date=parsed_date(
                    details.get("release_date")
                    if kind == "movie"
                    else details.get("first_air_date")
                ),
                maturity_rating=rating(details, kind),
                status=CatalogStatus.published,
                original_language_code=language_code,
                country_code=country_code,
                metadata_provider="tmdb",
                external_id=external_id,
            )
            record = (
                Movie(runtime_minutes=max(1, details.get("runtime") or 1), **common)
                if kind == "movie"
                else Series(**common)
            )
            db.add(record)
        else:
            record.title = title
            record.original_title = original_title if original_title != title else None
            record.short_description = overview[:500]
            record.synopsis = overview
            record.release_date = parsed_date(
                details.get("release_date") if kind == "movie" else details.get("first_air_date")
            )
            record.maturity_rating = rating(details, kind)
            record.status = CatalogStatus.published
            record.original_language_code = language_code
            record.country_code = country_code
            if kind == "movie":
                record.runtime_minutes = max(1, details.get("runtime") or record.runtime_minutes)
        record.poster_url = (
            f"{IMAGE}{details['poster_path']}" if details.get("poster_path") else None
        )
        record.backdrop_url = (
            f"{IMAGE}{details['backdrop_path']}" if details.get("backdrop_path") else None
        )
        keyword_rows = details.get("keywords", {}).get(
            "keywords" if kind == "movie" else "results", []
        )
        keyword_names = {str(value.get("name", "")).casefold() for value in keyword_rows}
        is_ova = (
            any(
                value == "ova"
                or "original video animation" in value
                or "original video anime" in value
                for value in keyword_names
            )
            or " ova" in f" {title.casefold()}"
        )
        record.content_format = "ova" if is_ova else kind
        record.studios = [
            company["name"]
            for company in details.get("production_companies", [])
            if company.get("name")
        ][:12]
        if kind == "tv":
            record.is_ongoing = bool(details.get("in_production"))
        record.genres = upsert_genres(db, details.get("genres", []))
        db.flush()
        if kind == "tv":
            known = {season.number: season for season in record.seasons}
            season_values = [
                value for value in details.get("seasons", []) if value.get("season_number", 0) >= 1
            ][-3:]
            selected_season_numbers = {value["season_number"] for value in season_values}
            for stale_season in list(record.seasons):
                if stale_season.number not in selected_season_numbers:
                    db.delete(stale_season)
            for value in season_values:
                number = value.get("season_number", 0)
                if number < 1:
                    continue
                season = known.get(number)
                if season is None:
                    season = Season(series_id=record.id, number=number)
                    db.add(season)
                season.title = value.get("name")
                season.synopsis = value.get("overview") or None
                db.flush()
                season_details = tmdb_get(
                    client,
                    f"/tv/{external_id}/season/{number}",
                    language=os.getenv("TMDB_LANGUAGE", "en-CA"),
                )
                known_episodes = {episode.number: episode for episode in season.episodes}
                episode_values = season_details.get("episodes", [])[:30]
                selected_episode_numbers = {
                    episode_value.get("episode_number") for episode_value in episode_values
                }
                for stale_episode in list(season.episodes):
                    if stale_episode.number not in selected_episode_numbers:
                        db.delete(stale_episode)
                for episode_value in episode_values:
                    episode_number = episode_value.get("episode_number")
                    if not episode_number:
                        continue
                    episode = known_episodes.get(episode_number)
                    if episode is None:
                        episode = Episode(season_id=season.id, number=episode_number)
                        db.add(episode)
                    episode.title = episode_value.get("name") or f"Episode {episode_number}"
                    episode.synopsis = (
                        episode_value.get("overview")
                        or f"Episode {episode_number} of {record.title}."
                    )
                    episode.runtime_minutes = max(
                        1,
                        episode_value.get("runtime")
                        or (details.get("episode_run_time") or [24])[0]
                        or 24,
                    )
                    episode.release_date = parsed_date(episode_value.get("air_date"))
                    episode.still_url = (
                        f"{IMAGE}{episode_value['still_path']}"
                        if episode_value.get("still_path")
                        else None
                    )
                    episode.status = CatalogStatus.published
        imported.append(record)
    return imported


def publish_homepage(db, movies: list[Movie], series: list[Series]) -> None:
    config = db.scalar(select(HomepageConfiguration))
    if config is None:
        config = HomepageConfiguration()
        db.add(config)
        db.flush()
    hero = movies[0] if movies else series[0]
    rails = []
    for key, title, source in (
        ("tmdb-movies", "Movies from around the world", "latest_movies"),
        ("tmdb-series", "Series worth discovering", "latest_series"),
    ):
        rails.append(
            {
                "id": str(uuid.uuid5(uuid.NAMESPACE_URL, f"aperture:{key}")),
                "title": title,
                "eyebrow": "Metadata and artwork via TMDB",
                "source": source,
                "query": "provider:tmdb",
                "position": len(rails),
                "enabled": True,
                "starts_at": None,
                "ends_at": None,
                "items": [],
            }
        )
    config.published_snapshot = {
        "hero": {"kind": "movie" if isinstance(hero, Movie) else "series", "id": str(hero.id)},
        "rails": rails,
    }
    config.published_at = datetime.now(UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--movies", type=int, default=16)
    parser.add_argument("--series", type=int, default=16)
    parser.add_argument("--scope", choices=("anime", "global", "mixed"), default="mixed")
    args = parser.parse_args()
    load_root_env()
    if get_settings().app_env not in {"development", "test"}:
        raise RuntimeError("TMDB import is restricted to development and test environments")
    token = os.getenv("TMDB_API_READ_ACCESS_TOKEN")
    if not token:
        raise RuntimeError("TMDB_API_READ_ACCESS_TOKEN is missing from the root .env file")
    with (
        httpx.Client(
            headers={"Authorization": f"Bearer {token}", "accept": "application/json"}, timeout=30
        ) as client,
        SessionLocal() as db,
    ):
        movies = import_kind(db, client, "movie", max(0, args.movies), args.scope)
        series = import_kind(db, client, "tv", max(0, args.series), args.scope)
        publish_homepage(db, movies, series)
        db.commit()
        print(f"TMDB local {args.scope} catalog ready: {len(movies)} movies, {len(series)} series.")


if __name__ == "__main__":
    main()
