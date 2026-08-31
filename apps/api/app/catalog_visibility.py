"""Shared public-catalog eligibility rules.

The test runner is physically isolated from development data. These rules are
an additional public-boundary safeguard for legacy fixtures already present in
a developer database and for metadata records with no public title behind them.
"""

from sqlalchemy import or_, select
from sqlalchemy.sql.elements import ColumnElement

from app.catalog_models import (
    CatalogStatus,
    Character,
    Company,
    Credit,
    Episode,
    Franchise,
    Genre,
    Movie,
    Person,
    Season,
    Series,
    Tag,
    Theme,
    movie_genres,
    movie_tags,
    movie_themes,
    series_genres,
)
from app.scheduling import availability_clause

# Historical fixture namespaces are quarantined at one boundary instead of
# being copied into individual routes. Patterns are anchored and apply only to
# local records: a legitimate provider-backed import must never disappear just
# because its provider generated a similar slug. New tests must never reach a
# developer database; see tests/conftest.py.
LEGACY_TEST_FIXTURE_SLUG_PATTERNS = (
    r"^analytics-fixture-[0-9a-f]{10}$",
    r"^club-film-[0-9a-f]{10}$",
    r"^community-film-[0-9a-f]{10}$",
    r"^e2e-club-playback-[a-z0-9-]+$",
    r"^e2e-studio-draft-[a-z0-9-]+$",
    r"^expired-(relation-)?[0-9a-f-]{10,36}$",
    r"^playback-fixture-[0-9a-f-]{36}$",
    r"^rate-limit-film-[0-9a-f]{10}$",
    r"^recommendation-(popular|similar|watched)-[0-9a-f]{10}$",
    r"^scene-lease-[0-9a-f-]{36}$",
    r"^the-lantern-sea-[a-z0-9-]+$",
    r"^visible-[0-9a-f]{10}$",
)


def exclude_legacy_test_fixtures(model: type[Movie] | type[Series]):
    """Return SQL clauses that quarantine known historical fixture namespaces."""

    return tuple(
        or_(model.metadata_provider.is_not(None), model.slug.op("!~")(pattern))
        for pattern in LEGACY_TEST_FIXTURE_SLUG_PATTERNS
    )


def public_title_conditions(
    model: type[Movie] | type[Series], *, country: str | None
) -> tuple[ColumnElement[bool], ...]:
    return (
        availability_clause(model, country=country),
        *exclude_legacy_test_fixtures(model),
    )


def _credit_has_public_title(
    foreign_key,
    record_id,
    *,
    country: str | None,
) -> ColumnElement[bool]:
    movie_credit = (
        select(Credit.id)
        .join(Movie, Credit.movie_id == Movie.id)
        .where(foreign_key == record_id, *public_title_conditions(Movie, country=country))
        .exists()
    )
    series_credit = (
        select(Credit.id)
        .join(Series, Credit.series_id == Series.id)
        .where(foreign_key == record_id, *public_title_conditions(Series, country=country))
        .exists()
    )
    episode_credit = (
        select(Credit.id)
        .join(Episode, Credit.episode_id == Episode.id)
        .join(Season, Episode.season_id == Season.id)
        .join(Series, Season.series_id == Series.id)
        .where(
            foreign_key == record_id,
            Episode.status == CatalogStatus.published,
            *public_title_conditions(Series, country=country),
        )
        .exists()
    )
    return or_(movie_credit, series_credit, episode_credit)


def public_named_record_condition(model, *, country: str | None) -> ColumnElement[bool]:
    """Require a named metadata record to be backed by a currently public title."""

    if model is Person:
        return _credit_has_public_title(Credit.person_id, Person.id, country=country)
    if model is Character:
        return _credit_has_public_title(Credit.character_id, Character.id, country=country)
    if model is Company:
        return _credit_has_public_title(Credit.company_id, Company.id, country=country)
    if model is Genre:
        return or_(
            select(movie_genres.c.genre_id)
            .join(Movie, movie_genres.c.movie_id == Movie.id)
            .where(
                movie_genres.c.genre_id == Genre.id,
                *public_title_conditions(Movie, country=country),
            )
            .exists(),
            select(series_genres.c.genre_id)
            .join(Series, series_genres.c.series_id == Series.id)
            .where(
                series_genres.c.genre_id == Genre.id,
                *public_title_conditions(Series, country=country),
            )
            .exists(),
        )
    if model is Theme:
        return (
            select(movie_themes.c.theme_id)
            .join(Movie, movie_themes.c.movie_id == Movie.id)
            .where(
                movie_themes.c.theme_id == Theme.id,
                *public_title_conditions(Movie, country=country),
            )
            .exists()
        )
    if model is Tag:
        return (
            select(movie_tags.c.tag_id)
            .join(Movie, movie_tags.c.movie_id == Movie.id)
            .where(
                movie_tags.c.tag_id == Tag.id,
                *public_title_conditions(Movie, country=country),
            )
            .exists()
        )
    if model is Franchise:
        return or_(
            select(Movie.id)
            .where(
                Movie.franchise_id == Franchise.id,
                *public_title_conditions(Movie, country=country),
            )
            .exists(),
            select(Series.id)
            .where(
                Series.franchise_id == Franchise.id,
                *public_title_conditions(Series, country=country),
            )
            .exists(),
        )
    raise TypeError(f"Unsupported public metadata model: {model!r}")
