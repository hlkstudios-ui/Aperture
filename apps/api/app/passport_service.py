from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import extract, or_, select

from app.catalog_models import Credit, Episode, Movie, Person, Season, Series
from app.catalog_service import movie_query, series_query
from app.catalog_visibility import exclude_legacy_test_fixtures
from app.models import PlaybackSource, Profile, ViewingActivity
from app.passport_schemas import (
    PassportCreator,
    PassportDistribution,
    PassportHistoryItem,
    PassportReport,
)


@dataclass
class ActivityTitle:
    activity: ViewingActivity
    kind: str
    title: Movie | Episode
    catalog_title: Movie | Series
    parent_title: str | None = None
    series_id: Any | None = None


def _distribution(values: list[tuple[str, str]]) -> list[PassportDistribution]:
    counts = Counter(key for key, _ in values)
    labels = {key: label for key, label in values}
    total = sum(counts.values())
    return [
        PassportDistribution(
            key=key,
            label=labels[key],
            count=count,
            percentage=round(count / total * 100, 1) if total else 0,
        )
        for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def _activity_titles(db, profile_id, year: int | None) -> tuple[list[ActivityTitle], list[int]]:
    all_years = sorted(
        {
            int(value)
            for value in db.scalars(
                select(extract("year", ViewingActivity.started_at)).where(
                    ViewingActivity.profile_id == profile_id
                )
            )
        },
        reverse=True,
    )
    statement = (
        select(ViewingActivity, PlaybackSource, Episode, Season)
        .join(PlaybackSource, ViewingActivity.playback_source_id == PlaybackSource.id)
        .outerjoin(Episode, PlaybackSource.episode_id == Episode.id)
        .outerjoin(Season, Episode.season_id == Season.id)
        .where(ViewingActivity.profile_id == profile_id)
        .order_by(ViewingActivity.started_at.desc())
    )
    if year is not None:
        statement = statement.where(extract("year", ViewingActivity.started_at) == year)
    rows = list(db.execute(statement).all())
    movie_ids = {source.movie_id for _, source, _, _ in rows if source.movie_id}
    series_ids = {season.series_id for _, _, episode, season in rows if episode and season}
    movies = {
        movie.id: movie
        for movie in db.scalars(
            movie_query().where(
                Movie.id.in_(movie_ids),
                *exclude_legacy_test_fixtures(Movie),
            )
        ).unique()
    }
    series = {
        series.id: series
        for series in db.scalars(
            series_query().where(
                Series.id.in_(series_ids),
                *exclude_legacy_test_fixtures(Series),
            )
        ).unique()
    }
    result: list[ActivityTitle] = []
    for activity, source, episode, season in rows:
        if source.movie_id and source.movie_id in movies:
            movie = movies[source.movie_id]
            result.append(ActivityTitle(activity, "movie", movie, movie))
        elif episode and season and season.series_id in series:
            result.append(
                ActivityTitle(
                    activity,
                    "episode",
                    episode,
                    series[season.series_id],
                    parent_title=series[season.series_id].title,
                    series_id=season.series_id,
                )
            )
    return result, all_years


def passport_report(db, profile: Profile, year: int | None = None) -> PassportReport:
    rows, available_years = _activity_titles(db, profile.id, year)
    completed = [item for item in rows if item.activity.completed]
    completed_movies = [item for item in completed if item.kind == "movie"]
    completed_episodes = [item for item in completed if item.kind == "episode"]
    genres: list[tuple[str, str]] = []
    countries: list[tuple[str, str]] = []
    decades: list[tuple[str, str]] = []
    runtimes: list[tuple[int, str]] = []
    for item in completed:
        catalog_title = item.catalog_title
        genres.extend((genre.slug, genre.name) for genre in catalog_title.genres)
        if catalog_title.country_code:
            countries.append((catalog_title.country_code, catalog_title.country_code))
        if catalog_title.release_date:
            decade = catalog_title.release_date.year // 10 * 10
            decades.append((str(decade), f"{decade}s"))
        runtime = (
            catalog_title.runtime_minutes if item.kind == "movie" else item.title.runtime_minutes
        )
        runtimes.append((runtime, item.title.title))

    title_activity_counts: Counter[tuple[str, Any]] = Counter(
        (item.kind, item.title.id if item.kind == "movie" else item.series_id) for item in completed
    )
    movie_ids = [title_id for (kind, title_id) in title_activity_counts if kind == "movie"]
    series_ids = [title_id for (kind, title_id) in title_activity_counts if kind == "episode"]
    title_filters = []
    if movie_ids:
        title_filters.append(Credit.movie_id.in_(movie_ids))
    if series_ids:
        title_filters.append(Credit.series_id.in_(series_ids))
    credits = (
        list(
            db.execute(
                select(Credit, Person)
                .join(Person, Credit.person_id == Person.id)
                .where(or_(*title_filters))
            ).all()
        )
        if title_filters
        else []
    )
    creator_counts: Counter[Any] = Counter()
    creator_roles: dict[Any, set[str]] = defaultdict(set)
    creator_names: dict[Any, str] = {}
    for credit, person in credits:
        key = ("movie", credit.movie_id) if credit.movie_id else ("episode", credit.series_id)
        creator_counts[person.id] += title_activity_counts[key]
        creator_roles[person.id].add(credit.role)
        creator_names[person.id] = person.name
    favorite_creators = [
        PassportCreator(
            person_id=person_id,
            name=creator_names[person_id],
            roles=sorted(creator_roles[person_id]),
            completed_views=count,
        )
        for person_id, count in creator_counts.most_common(8)
    ]
    milestones = []
    if completed:
        plural = "s" if len(completed) != 1 else ""
        milestones.append(f"Completed {len(completed)} viewing journey{plural}.")
    if countries:
        country_count = len(set(key for key, _ in countries))
        country_label = "countries" if country_count != 1 else "country"
        milestones.append(f"Explored {country_count} {country_label}.")
    return PassportReport(
        profile_id=profile.id,
        year=year,
        available_years=available_years,
        films_watched=len({item.title.id for item in completed_movies}),
        episodes_watched=len({item.title.id for item in completed_episodes}),
        completed_views=len(completed),
        first_watches=sum(not item.activity.is_rewatch for item in completed),
        rewatches=sum(item.activity.is_rewatch for item in completed),
        observed_watch_hours=round(sum(item.activity.watched_seconds for item in rows) / 3600, 2),
        countries_explored=len(set(key for key, _ in countries)),
        longest_title=max(runtimes)[1] if runtimes else None,
        shortest_title=min(runtimes)[1] if runtimes else None,
        favorite_genres=_distribution(genres),
        favorite_creators=favorite_creators,
        country_distribution=_distribution(countries),
        decade_distribution=_distribution(decades),
        history=[
            PassportHistoryItem(
                kind=item.kind,
                title=item.title.title,
                parent_title=item.parent_title,
                activity_number=item.activity.activity_number,
                is_rewatch=item.activity.is_rewatch,
                watched_seconds=item.activity.watched_seconds,
                completed=item.activity.completed,
                started_at=item.activity.started_at,
                completed_at=item.activity.completed_at,
            )
            for item in rows[:100]
        ],
        milestones=milestones,
    )
