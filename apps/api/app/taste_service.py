from collections import Counter
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select

from app.catalog_models import Episode, Movie, Season, Series
from app.catalog_service import movie_query, series_query
from app.models import PlaybackSource, Profile, WatchProgress
from app.recommendation_schemas import TasteAffinity, TasteDnaResponse


@dataclass
class WatchedTitle:
    title: Movie | Series
    weight: float
    completed: bool
    runtime_minutes: int | None


def watched_titles(db, profile_id) -> list[WatchedTitle]:
    progress_rows = list(
        db.execute(
            select(WatchProgress, PlaybackSource, Episode, Season)
            .join(PlaybackSource, WatchProgress.playback_source_id == PlaybackSource.id)
            .outerjoin(Episode, PlaybackSource.episode_id == Episode.id)
            .outerjoin(Season, Episode.season_id == Season.id)
            .where(WatchProgress.profile_id == profile_id)
            .order_by(WatchProgress.last_watched_at.desc())
        ).all()
    )
    movie_ids = {source.movie_id for _, source, _, _ in progress_rows if source.movie_id}
    series_ids = {season.series_id for _, _, episode, season in progress_rows if episode and season}
    movies = {
        item.id: item for item in db.scalars(movie_query().where(Movie.id.in_(movie_ids))).unique()
    }
    series = {
        item.id: item
        for item in db.scalars(series_query().where(Series.id.in_(series_ids))).unique()
    }
    result: dict[tuple[str, Any], WatchedTitle] = {}
    for progress, source, episode, season in progress_rows:
        kind = "movie" if source.movie_id else "series"
        title_id = source.movie_id or (season.series_id if episode and season else None)
        title = movies.get(title_id) if kind == "movie" else series.get(title_id)
        if title is None:
            continue
        key = (kind, title.id)
        weight = round(0.25 + min(progress.percentage, 100) / 100, 3)
        current = result.get(key)
        if current is None or weight > current.weight:
            result[key] = WatchedTitle(
                title=title,
                weight=weight,
                completed=progress.completed,
                runtime_minutes=(
                    title.runtime_minutes if kind == "movie" else episode.runtime_minutes
                ),
            )
        elif progress.completed:
            current.completed = True
    return list(result.values())


def _affinities(entries: list[tuple[str, str, float]], limit: int = 6) -> list[TasteAffinity]:
    weights: Counter[str] = Counter()
    counts: Counter[str] = Counter()
    labels: dict[str, str] = {}
    for key, label, weight in entries:
        weights[key] += weight
        counts[key] += 1
        labels[key] = label
    return [
        TasteAffinity(
            key=key,
            label=labels[key],
            weight=round(weight, 2),
            watched_titles=counts[key],
        )
        for key, weight in sorted(weights.items(), key=lambda item: (-item[1], item[0]))[:limit]
    ]


def taste_dna(db, profile: Profile) -> TasteDnaResponse:
    watched = watched_titles(db, profile.id)
    completed = sum(item.completed for item in watched)
    runtimes = [item.runtime_minutes for item in watched if item.runtime_minutes]
    genres = _affinities(
        [(value.slug, value.name, item.weight) for item in watched for value in item.title.genres]
    )
    movie_entries = [item for item in watched if isinstance(item.title, Movie)]
    themes = _affinities(
        [
            (value.slug, value.name, item.weight)
            for item in movie_entries
            for value in item.title.themes
        ]
    )
    tags = _affinities(
        [
            (value.slug, value.name, item.weight)
            for item in movie_entries
            for value in item.title.tags
        ]
    )
    decades = _affinities(
        [
            (
                str(item.title.release_date.year // 10 * 10),
                f"{item.title.release_date.year // 10 * 10}s",
                item.weight,
            )
            for item in watched
            if item.title.release_date
        ]
    )
    countries = _affinities(
        [
            (item.title.country_code, item.title.country_code, item.weight)
            for item in watched
            if item.title.country_code
        ]
    )
    languages = _affinities(
        [
            (item.title.original_language_code, item.title.original_language_code, item.weight)
            for item in watched
            if item.title.original_language_code
        ]
    )
    insights: list[str] = []
    if genres:
        insights.append(f"Your strongest observed genre is {genres[0].label}.")
    if decades:
        insights.append(f"You most often return to films from the {decades[0].label}.")
    average_runtime = round(sum(runtimes) / len(runtimes), 1) if runtimes else None
    if average_runtime:
        insights.append(f"Your watched titles average {average_runtime:g} minutes.")
    completion_rate = round(completed / len(watched) * 100, 1) if watched else None
    if completion_rate is not None:
        insights.append(f"You completed {completion_rate:g}% of observed titles.")
    return TasteDnaResponse(
        profile_id=profile.id,
        watched_titles=len(watched),
        completed_titles=completed,
        completion_rate=completion_rate,
        average_runtime_minutes=average_runtime,
        confidence="established" if len(watched) >= 5 else "emerging" if watched else "none",
        genres=genres,
        themes=themes,
        tags=tags,
        decades=decades,
        countries=countries,
        languages=languages,
        insights=insights,
    )
