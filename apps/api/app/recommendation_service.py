import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Literal

from sqlalchemy import select

from app.catalog_models import Episode, Movie, Season, Series
from app.catalog_service import movie_query, series_query
from app.models import (
    AggregatedMetric,
    AnalyticsEventType,
    HomepageConfiguration,
    PlaybackSource,
    Profile,
    WatchProgress,
)
from app.recommendation_schemas import (
    RecommendationItem,
    RecommendationReason,
    RecommendationResponse,
)
from app.scheduling import availability_clause, synchronize_due_schedules


@dataclass
class Candidate:
    kind: Literal["movie", "series"]
    title: Movie | Series
    score: float = 0
    reasons: set[RecommendationReason] = field(default_factory=set)


def _editorial_ids(snapshot: dict | None) -> set[uuid.UUID]:
    result: set[uuid.UUID] = set()
    if not snapshot:
        return result
    nodes = [
        snapshot.get("hero"),
        *[item for rail in snapshot.get("rails", []) for item in rail.get("items", [])],
    ]
    for node in nodes:
        if node and node.get("id"):
            try:
                result.add(uuid.UUID(node["id"]))
            except (ValueError, TypeError):
                continue
    return result


def recommend(
    db,
    profile: Profile,
    limit: int = 20,
    *,
    personalized: bool = True,
    country: str | None = None,
) -> RecommendationResponse:
    synchronize_due_schedules(db)
    movies = list(
        db.scalars(
            movie_query().where(
                availability_clause(Movie, country=country),
                Movie.metadata_provider.is_(None),
            )
        ).unique()
    )
    series = list(
        db.scalars(
            series_query().where(
                availability_clause(Series, country=country),
                Series.metadata_provider.is_(None),
            )
        ).unique()
    )
    progress = (
        list(
            db.execute(
                select(WatchProgress, PlaybackSource, Episode, Season)
                .join(PlaybackSource, WatchProgress.playback_source_id == PlaybackSource.id)
                .outerjoin(Episode, PlaybackSource.episode_id == Episode.id)
                .outerjoin(Season, Episode.season_id == Season.id)
                .where(WatchProgress.profile_id == profile.id)
            ).all()
        )
        if personalized
        else []
    )
    watched_movie_ids = {source.movie_id for _, source, _, _ in progress if source.movie_id}
    watched_series_ids = {
        season.series_id for _, _, episode, season in progress if episode and season
    }
    watched_count = len(watched_movie_ids) + len(watched_series_ids)

    watched_movies = [item for item in movies if item.id in watched_movie_ids]
    watched_series = [item for item in series if item.id in watched_series_ids]
    genre_affinity = Counter(
        g.slug for title in [*watched_movies, *watched_series] for g in title.genres
    )
    theme_affinity = Counter(t.slug for title in watched_movies for t in title.themes)
    tag_affinity = Counter(t.slug for title in watched_movies for t in title.tags)
    explicit_genres = (
        set((profile.preference.extra or {}).get("preferred_genre_slugs", []))
        if personalized
        else set()
    )

    config = db.scalar(select(HomepageConfiguration).limit(1))
    editorial = _editorial_ids(config.published_snapshot if config else None)
    since = datetime.now(UTC).date() - timedelta(days=30)
    popularity = Counter()
    for row in db.scalars(
        select(AggregatedMetric).where(
            AggregatedMetric.day >= since,
            AggregatedMetric.event_type == AnalyticsEventType.play_start,
            AggregatedMetric.movie_id.is_not(None),
        )
    ):
        if row.movie_id:
            popularity[row.movie_id] += row.event_count
    max_popularity = max(popularity.values(), default=0)
    cold_start = watched_count == 0 and not explicit_genres

    candidates = [Candidate("movie", item) for item in movies if item.id not in watched_movie_ids]
    candidates += [
        Candidate("series", item) for item in series if item.id not in watched_series_ids
    ]
    for candidate in candidates:
        title = candidate.title
        if title.id in editorial:
            candidate.score += 40
            candidate.reasons.add(RecommendationReason.editorial)
        genre_score = sum(genre_affinity[g.slug] for g in title.genres)
        if genre_score:
            candidate.score += min(genre_score * 12, 30)
            candidate.reasons.add(RecommendationReason.similar_genres)
        preferred_matches = sum(g.slug in explicit_genres for g in title.genres)
        if preferred_matches:
            candidate.score += preferred_matches * 18
            candidate.reasons.add(RecommendationReason.profile_genre_preference)
        if candidate.kind == "movie":
            theme_score = sum(theme_affinity[t.slug] for t in title.themes)
            tag_score = sum(tag_affinity[t.slug] for t in title.tags)
            if theme_score:
                candidate.score += min(theme_score * 8, 16)
                candidate.reasons.add(RecommendationReason.similar_themes)
            if tag_score:
                candidate.score += min(tag_score * 5, 10)
                candidate.reasons.add(RecommendationReason.similar_tags)
            plays = popularity.get(title.id, 0)
            if plays:
                candidate.score += 20 * plays / max_popularity
                candidate.reasons.add(RecommendationReason.popular_now)
        if cold_start:
            candidate.score += 5
            candidate.reasons.add(RecommendationReason.cold_start)
        if not candidate.reasons:
            candidate.score += 1
            candidate.reasons.add(RecommendationReason.cold_start)

    candidates.sort(
        key=lambda item: (
            -item.score,
            -(item.title.release_date.toordinal() if item.title.release_date else 0),
            item.title.title.casefold(),
            str(item.title.id),
        )
    )
    items = [
        RecommendationItem(
            kind=item.kind,
            score=round(item.score, 2),
            reasons=sorted(item.reasons, key=lambda reason: reason.value),
            movie=item.title if item.kind == "movie" else None,
            series=item.title if item.kind == "series" else None,
        )
        for item in candidates[:limit]
    ]
    return RecommendationResponse(
        profile_id=profile.id,
        strategy="rules_v1" if personalized else "editorial_popularity_v1",
        personalized=personalized,
        cold_start=cold_start,
        watched_titles_excluded=watched_count,
        items=items,
    )
