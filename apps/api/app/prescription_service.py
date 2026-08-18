import re
from dataclasses import dataclass, field

from fastapi import HTTPException, status
from sqlalchemy import select

from app.catalog_models import Genre, Movie
from app.catalog_service import movie_query
from app.models import Profile
from app.recommendation_schemas import (
    PrescriptionDimension,
    PrescriptionRequest,
    PrescriptionResponse,
)
from app.scheduling import availability_clause, synchronize_due_schedules
from app.taste_service import taste_dna, watched_titles

MOOD_TERMS = {
    "uplifting": {"uplifting", "hopeful", "joyful", "feel-good"},
    "dark": {"dark", "bleak", "noir", "gothic"},
    "comforting": {"comforting", "cozy", "gentle", "warm"},
    "tense": {"tense", "suspense", "thriller", "anxious"},
    "reflective": {"reflective", "meditative", "philosophical", "introspective"},
    "adventurous": {"adventure", "adventurous", "quest", "journey"},
}
PACING_TERMS = {
    "slow": {"slow", "slow-burn", "meditative"},
    "balanced": {"balanced", "steady"},
    "fast": {"fast", "fast-paced", "kinetic"},
}
INTENSITY_TERMS = {
    "gentle": {"gentle", "comforting", "quiet"},
    "moderate": {"moderate", "balanced"},
    "intense": {"intense", "visceral", "extreme", "tense"},
}


@dataclass
class Match:
    movie: Movie
    score: float = 35
    dimensions: list[PrescriptionDimension] = field(default_factory=list)
    evidence: list[str] = field(default_factory=list)


def _terms(movie: Movie) -> set[str]:
    values = [
        *(item.slug for item in movie.genres),
        *(item.slug for item in movie.themes),
        *(item.slug for item in movie.tags),
    ]
    return {
        token
        for value in values
        for token in {value.casefold(), *re.split(r"[-_ ]+", value.casefold())}
    }


def _dimension(
    match: Match, name: str, matched: bool | None, explanation: str, points: int
) -> None:
    state = "matched" if matched else "neutral" if matched is None else "unavailable"
    match.dimensions.append(
        PrescriptionDimension(dimension=name, status=state, explanation=explanation)
    )
    if matched:
        match.score += points
        match.evidence.append(explanation)


def _validate_genres(db, request: PrescriptionRequest) -> None:
    requested = set(request.preferred_genre_slugs + request.unwanted_genre_slugs)
    existing = set(db.scalars(select(Genre.slug).where(Genre.slug.in_(requested))))
    if existing != requested:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unknown genre constraint")


def prescribe(
    db,
    profile: Profile,
    request: PrescriptionRequest,
    country: str | None = None,
) -> PrescriptionResponse:
    _validate_genres(db, request)
    synchronize_due_schedules(db)
    watched = watched_titles(db, profile.id)
    watched_ids = {item.title.id for item in watched if isinstance(item.title, Movie)}
    candidates = list(
        db.scalars(
            movie_query().where(
                availability_clause(Movie, country=country),
                Movie.id.not_in(request.exclude_movie_ids),
            )
        ).unique()
    )
    if request.watch_state == "unwatched":
        candidates = [movie for movie in candidates if movie.id not in watched_ids]
    elif request.watch_state == "watched":
        candidates = [movie for movie in candidates if movie.id in watched_ids]
    if request.time_available_minutes is not None:
        candidates = [
            movie for movie in candidates if movie.runtime_minutes <= request.time_available_minutes
        ]
    unwanted = set(request.unwanted_genre_slugs)
    candidates = [movie for movie in candidates if not unwanted & {g.slug for g in movie.genres}]
    if request.language:
        candidates = [
            movie for movie in candidates if movie.original_language_code == request.language
        ]
    if request.release_era_start is not None:
        candidates = [
            movie
            for movie in candidates
            if movie.release_date and movie.release_date.year >= request.release_era_start
        ]
    if request.release_era_end is not None:
        candidates = [
            movie
            for movie in candidates
            if movie.release_date and movie.release_date.year <= request.release_era_end
        ]
    blocked_terms = {value.strip().casefold() for value in request.unwanted_characteristics}
    candidates = [movie for movie in candidates if not blocked_terms & _terms(movie)]
    if not candidates:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No available movie satisfies every requested constraint",
        )

    dna = taste_dna(db, profile)
    affinity = {item.key: item.weight for item in dna.genres}
    max_affinity = max(affinity.values(), default=0)
    matches: list[Match] = []
    for movie in candidates:
        match = Match(movie)
        movie_genres = {genre.slug: genre.name for genre in movie.genres}
        preferred = set(request.preferred_genre_slugs) & set(movie_genres)
        _dimension(
            match,
            "genre",
            bool(preferred) if request.preferred_genre_slugs else None,
            (
                f"Matches requested genre: {movie_genres[sorted(preferred)[0]]}."
                if preferred
                else "No preferred genre was supplied."
                if not request.preferred_genre_slugs
                else "Does not match a requested genre."
            ),
            18,
        )
        taste_weight = sum(affinity.get(slug, 0) for slug in movie_genres)
        taste_matched = taste_weight > 0
        taste_label = next(
            (movie_genres[slug] for slug in movie_genres if affinity.get(slug)), None
        )
        _dimension(
            match,
            "taste_dna",
            taste_matched if dna.watched_titles else None,
            (
                f"Your persisted viewing shows affinity for {taste_label}."
                if taste_label
                else "Taste DNA has no viewing evidence for this title yet."
            ),
            round(20 * taste_weight / max_affinity) if max_affinity else 0,
        )
        movie_terms = _terms(movie)
        for dimension, requested, mapping, points in (
            ("mood", request.mood, MOOD_TERMS, 12),
            ("pacing", request.pacing, PACING_TERMS, 10),
            ("intensity", request.intensity, INTENSITY_TERMS, 10),
        ):
            observed = bool(requested and movie_terms & mapping[requested])
            _dimension(
                match,
                dimension,
                observed if requested else None,
                (
                    f"Catalog themes/tags support {requested} {dimension}."
                    if observed
                    else f"Catalog metadata does not establish {requested} {dimension}."
                    if requested
                    else f"No {dimension} preference was supplied."
                ),
                points,
            )
        _dimension(
            match,
            "runtime",
            True if request.time_available_minutes is not None else None,
            (
                f"Runs {movie.runtime_minutes} minutes within your "
                f"{request.time_available_minutes}-minute limit."
                if request.time_available_minutes is not None
                else f"Runtime is {movie.runtime_minutes} minutes; no limit was supplied."
            ),
            5,
        )
        matches.append(match)
    matches.sort(
        key=lambda item: (
            -item.score,
            -(item.movie.release_date.toordinal() if item.movie.release_date else 0),
            item.movie.title.casefold(),
            str(item.movie.id),
        )
    )
    best = matches[0]
    reason = " ".join(best.evidence[:2]) or "Best deterministic fit among eligible movies."
    return PrescriptionResponse(
        profile_id=profile.id,
        movie=best.movie,
        taste_match_score=min(round(best.score), 100),
        reason=reason,
        constraints_satisfied=True,
        match_dimensions=best.dimensions,
    )
