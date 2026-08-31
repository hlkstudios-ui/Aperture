from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import date, timedelta
from threading import BoundedSemaphore, Lock
from time import monotonic
from typing import Literal

import httpx

from app.browse_schemas import (
    TmdbAttribution,
    TmdbBrowseSection,
    TmdbBrowseSectionsResponse,
    TmdbBrowseTitle,
    TmdbTrendingTitlesResponse,
)
from app.config import get_settings
from app.movie_api_client import (
    MovieApiError,
    movie_api_discovery,
    movie_api_enabled,
    movie_api_feed,
)
from app.tmdb_discovery import TMDB_API, TMDB_BACKDROP_IMAGE, TMDB_CARD_IMAGE, _client

TMDB_BROWSE_CACHE_SECONDS = 30 * 60
TMDB_BROWSE_STALE_SECONDS = 6 * 60 * 60
TMDB_BROWSE_FAILURE_CACHE_SECONDS = 60
TMDB_BROWSE_MAX_CACHE_ENTRIES = 512
TMDB_BROWSE_MAX_CONCURRENCY = 6
TMDB_BROWSE_TIMEOUT = httpx.Timeout(4.5, connect=2.0)

TMDB_ATTRIBUTION_NOTICE = "This product uses the TMDB API but is not endorsed or certified by TMDB."


@dataclass(frozen=True, slots=True)
class TmdbSectionRecipe:
    slug: str
    eyebrow: str
    title: str
    description: str
    media_type: Literal["movie", "series", "mixed"]
    endpoint: str
    params: tuple[tuple[str, str], ...] = ()

    @property
    def fingerprint(self) -> tuple[str, tuple[tuple[str, str], ...]]:
        return self.endpoint, tuple(sorted(self.params))


def _recipe(
    slug: str,
    eyebrow: str,
    title: str,
    description: str,
    media_type: Literal["movie", "series", "mixed"],
    endpoint: str,
    **params: str,
) -> TmdbSectionRecipe:
    return TmdbSectionRecipe(
        slug=slug,
        eyebrow=eyebrow,
        title=title,
        description=description,
        media_type=media_type,
        endpoint=endpoint,
        params=tuple(sorted(params.items())),
    )


def _discover_movie(
    slug: str,
    eyebrow: str,
    title: str,
    description: str,
    **params: str,
) -> TmdbSectionRecipe:
    query = {
        "include_adult": "false",
        "include_video": "false",
        "sort_by": "popularity.desc",
        "vote_count.gte": "80",
        **params,
    }
    return _recipe(slug, eyebrow, title, description, "movie", "/discover/movie", **query)


def _discover_series(
    slug: str,
    eyebrow: str,
    title: str,
    description: str,
    **params: str,
) -> TmdbSectionRecipe:
    query = {
        "include_adult": "false",
        "sort_by": "popularity.desc",
        "vote_count.gte": "50",
        **params,
    }
    return _recipe(slug, eyebrow, title, description, "series", "/discover/tv", **query)


_PULSE_RECIPES = (
    _recipe(
        "trending-across-the-screen",
        "THE WORLD IS WATCHING",
        "Trending Across the Screen",
        "Films and series gathering momentum around the world this week.",
        "mixed",
        "/trending/all/week",
    ),
    _recipe(
        "movies-breaking-today",
        "TODAY'S MOVIE PULSE",
        "Movies Breaking Today",
        "The feature films moving fastest through today's conversation.",
        "movie",
        "/trending/movie/day",
    ),
    _recipe(
        "movies-owning-the-week",
        "SEVEN DAYS OF CINEMA",
        "Movies Owning the Week",
        "A wider view of the films audiences keep returning to this week.",
        "movie",
        "/trending/movie/week",
    ),
    _recipe(
        "series-breaking-today",
        "TODAY'S SERIES PULSE",
        "Series Breaking Today",
        "The shows becoming impossible to ignore before the day is over.",
        "series",
        "/trending/tv/day",
    ),
    _recipe(
        "series-owning-the-week",
        "SEVEN NIGHTS OF TELEVISION",
        "Series Owning the Week",
        "The stories dominating living rooms and group chats this week.",
        "series",
        "/trending/tv/week",
    ),
    _recipe(
        "now-in-theatres",
        "THE BIG SCREEN NOW",
        "Now in Theatres",
        "Current theatrical releases, from opening-night discoveries to crowd favourites.",
        "movie",
        "/movie/now_playing",
    ),
    _recipe(
        "coming-to-the-big-screen",
        "THE CURTAIN RISES SOON",
        "Coming to the Big Screen",
        "Upcoming releases worth placing on the calendar before everyone else does.",
        "movie",
        "/movie/upcoming",
    ),
    _recipe(
        "series-airing-today",
        "TONIGHT'S TRANSMISSIONS",
        "Series Airing Today",
        "Fresh episodes and broadcasts arriving across the television landscape today.",
        "series",
        "/tv/airing_today",
    ),
    _recipe(
        "series-on-the-air",
        "STORIES IN MOTION",
        "Series on the Air",
        "Currently running shows with new chapters still unfolding.",
        "series",
        "/tv/on_the_air",
    ),
    _recipe(
        "what-the-world-opened-today",
        "THE DAILY GLOBAL REEL",
        "What the World Opened Today",
        "A live cross-format snapshot of today's most watched screen stories.",
        "mixed",
        "/trending/all/day",
    ),
)

_MOVIE_GENRES = (
    (
        28,
        "action",
        "Action That Hits Back",
        "Momentum, impact, and heroes who refuse to stay down.",
    ),
    (
        12,
        "adventure",
        "Adventures Beyond the Map",
        "Journeys that begin where the known world ends.",
    ),
    (
        16,
        "animation",
        "Animation Without Boundaries",
        "Drawn, painted, and rendered worlds built for every age.",
    ),
    (
        35,
        "comedy",
        "Comedies With Perfect Timing",
        "Sharp wit, glorious chaos, and laughter that lands.",
    ),
    (
        80,
        "crime",
        "Crime Leaves a Shadow",
        "Heists, syndicates, detectives, and choices that leave fingerprints.",
    ),
    (
        99,
        "documentary",
        "True Stories, Unflinching Eyes",
        "Reality observed closely enough to become unforgettable.",
    ),
    (
        18,
        "drama",
        "Lives Under Pressure",
        "Human stories shaped by desire, consequence, and impossible choices.",
    ),
    (
        10751,
        "family",
        "The Whole Room Is Invited",
        "Generous adventures made to be shared across generations.",
    ),
    (
        14,
        "fantasy",
        "Kingdoms Beyond the Veil",
        "Magic, myth, and worlds governed by impossible rules.",
    ),
    (
        36,
        "history",
        "When History Was Present Tense",
        "The people and decisions that turned moments into eras.",
    ),
    (
        27,
        "horror",
        "Do Not Turn Out the Lights",
        "Dread that creeps, strikes, and follows you home.",
    ),
    (
        10402,
        "music",
        "Where the Music Takes Over",
        "Rhythm, performance, and lives transformed by sound.",
    ),
    (
        9648,
        "mystery",
        "Nothing Is What It Seems",
        "Clues, secrets, and elegant questions with dangerous answers.",
    ),
    (
        10749,
        "romance",
        "Love in Every Imperfect Form",
        "Connection, longing, and the courage to be known.",
    ),
    (
        878,
        "science-fiction",
        "Tomorrow Has Already Begun",
        "Science, speculation, and futures close enough to touch.",
    ),
    (53, "thriller", "No Safe Distance", "Tension wound tight until every second matters."),
    (
        10752,
        "war",
        "Lives Inside the Conflict",
        "Courage, survival, and the human cost behind the battle lines.",
    ),
    (
        37,
        "western",
        "Dust, Steel, and Open Sky",
        "Frontiers where justice travels on its own terms.",
    ),
    (
        10770,
        "television-movies",
        "Made for One Unmissable Night",
        "Feature-length stories created for the intimacy of television.",
    ),
)

_MOVIE_GENRE_RECIPES = tuple(
    _discover_movie(
        f"movie-{slug}",
        "A CINEMA OF ITS OWN",
        title,
        description,
        with_genres=str(genre_id),
    )
    for genre_id, slug, title, description in _MOVIE_GENRES
)

_SERIES_GENRES = (
    (
        10759,
        "action-adventure",
        "Series Built on Momentum",
        "Escapes, missions, and danger designed to keep the next episode calling.",
    ),
    (
        16,
        "animation",
        "Animated Worlds in Chapters",
        "Visual imagination with enough room to grow across seasons.",
    ),
    (
        35,
        "comedy",
        "Comedy Worth Another Episode",
        "Characters and chaos that become funnier the longer you know them.",
    ),
    (
        80,
        "crime",
        "Crime Stories That Keep a File Open",
        "Cases, empires, and consequences unfolding one chapter at a time.",
    ),
    (
        99,
        "documentary",
        "Reality in Episodes",
        "True stories examined with the patience only a series can offer.",
    ),
    (
        18,
        "drama",
        "Drama With Room to Breathe",
        "Lives, loyalties, and slow-burning decisions that reshape entire worlds.",
    ),
    (
        10751,
        "family",
        "Stories for the Shared Screen",
        "Series the whole household can make part of its week.",
    ),
    (
        10762,
        "kids",
        "Big Adventures for Young Viewers",
        "Bright, inventive stories made for curious minds.",
    ),
    (
        9648,
        "mystery",
        "One More Clue Before Bed",
        "Layered mysteries that reward attention across every episode.",
    ),
    (
        10763,
        "news",
        "The World as It Happens",
        "Current events and reporting from across the global screen.",
    ),
    (
        10764,
        "reality",
        "Unscripted and Unpredictable",
        "Real personalities, real stakes, and turns no writer planned.",
    ),
    (
        10765,
        "science-fiction-fantasy",
        "Impossible Worlds, Continuing Stories",
        "Speculative universes expansive enough for seasons of discovery.",
    ),
    (
        10766,
        "soap",
        "Every Secret Has Another Secret",
        "Entangled lives, grand emotions, and revelations without end.",
    ),
    (
        10767,
        "talk",
        "Conversations That Carry",
        "Ideas, interviews, and personalities worth staying up to hear.",
    ),
    (
        10768,
        "war-politics",
        "Power Is Never Off the Record",
        "Governments, conflicts, and the rooms where history is negotiated.",
    ),
    (
        37,
        "western",
        "The Frontier, Chapter by Chapter",
        "Open country, hard bargains, and legends built over time.",
    ),
)

_SERIES_GENRE_RECIPES = tuple(
    _discover_series(
        f"series-{slug}",
        "A SERIES FOR EVERY MOOD",
        title,
        description,
        with_genres=str(genre_id),
    )
    for genre_id, slug, title, description in _SERIES_GENRES
)

_MOVIE_ERAS = (
    (1920, "silent-twenties", "The Roaring Screen: 1920s"),
    (1930, "golden-thirties", "Stars Through the Storm: 1930s"),
    (1940, "forties", "Shadows and Resolve: 1940s"),
    (1950, "fifties", "Cinema Finds a Wider Canvas: 1950s"),
    (1960, "sixties", "The Rules Begin to Break: 1960s"),
    (1970, "seventies", "The Fearless New Hollywood: 1970s"),
    (1980, "eighties", "Neon, Wonder, and 1980s Cinema"),
    (1990, "nineties", "The Movies That Defined the 1990s"),
    (2000, "two-thousands", "A New Millennium on Film"),
    (2010, "twenty-tens", "The Expanding Screen: 2010s"),
    (2020, "twenty-twenties", "Cinema of the 2020s"),
)

_MOVIE_ERA_RECIPES = tuple(
    _discover_movie(
        f"movies-{slug}",
        "A DECADE IN MOTION",
        title,
        f"A living shelf of films released from {year} through {year + 9}.",
        **{
            "primary_release_date.gte": f"{year}-01-01",
            "primary_release_date.lte": "$today" if year == 2020 else f"{year + 9}-12-31",
            "sort_by": "vote_average.desc",
            "vote_count.gte": "120" if year >= 1970 else "30",
        },
    )
    for year, slug, title in _MOVIE_ERAS
)

_SERIES_ERAS = (
    (1980, "eighties", "Television Rewired: The 1980s"),
    (1990, "nineties", "Appointment Television: The 1990s"),
    (2000, "two-thousands", "The Box Set Era: The 2000s"),
    (2010, "twenty-tens", "Peak Television: The 2010s"),
    (2020, "twenty-twenties", "Series of the 2020s"),
)

_SERIES_ERA_RECIPES = tuple(
    _discover_series(
        f"series-{slug}-era",
        "TELEVISION THROUGH TIME",
        title,
        f"Series that first entered the world from {year} through {year + 9}.",
        **{
            "first_air_date.gte": f"{year}-01-01",
            "first_air_date.lte": "$today" if year == 2020 else f"{year + 9}-12-31",
            "sort_by": "vote_average.desc",
            "vote_count.gte": "80",
        },
    )
    for year, slug, title in _SERIES_ERAS
)

_WORLD_MOVIES = (
    ("fr", "french", "French Cinema, Restless and Romantic"),
    ("es", "spanish", "Spanish-Language Cinema With Fire"),
    ("ko", "korean", "Korean Cinema Without Limits"),
    ("ja", "japanese", "Japanese Cinema, Past and Future"),
    ("hi", "hindi", "Hindi Cinema in Full Colour"),
    ("zh", "chinese", "Chinese-Language Stories on a Grand Scale"),
    ("it", "italian", "Italian Cinema, Beautifully Human"),
    ("de", "german", "German Cinema With an Edge"),
    ("pt", "portuguese", "Portuguese-Language Worlds"),
    ("ar", "arabic", "Arabic Cinema, Many Lives and Landscapes"),
    ("tr", "turkish", "Turkish Cinema of Heart and Tension"),
    ("sv", "swedish", "Swedish Cinema Beneath the Surface"),
)

_WORLD_MOVIE_RECIPES = tuple(
    _discover_movie(
        f"world-movies-{slug}",
        "PASSPORT TO CINEMA",
        title,
        "A globally sourced selection led by its original language and strongest audience signals.",
        with_original_language=language,
        **{"sort_by": "vote_average.desc", "vote_count.gte": "60"},
    )
    for language, slug, title in _WORLD_MOVIES
)

_WORLD_SERIES = (
    ("ko", "korean", "Korean Series Everyone Talks About"),
    ("ja", "japanese", "Japanese Series Beyond the Familiar"),
    ("es", "spanish", "Spanish-Language Series With Momentum"),
    ("tr", "turkish", "Turkish Series Made for Long Evenings"),
    ("hi", "hindi", "Hindi Series Finding New Audiences"),
    ("de", "german", "German Series, Precise and Unsettling"),
    ("fr", "french", "French Series With a Point of View"),
)

_WORLD_SERIES_RECIPES = tuple(
    _discover_series(
        f"world-series-{slug}",
        "TELEVISION WITHOUT BORDERS",
        title,
        "Acclaimed and widely watched series discovered through their original language.",
        with_original_language=language,
        **{"sort_by": "vote_average.desc", "vote_count.gte": "40"},
    )
    for language, slug, title in _WORLD_SERIES
)

_CRAFTED_RECIPES = (
    _discover_movie(
        "velocity-and-danger",
        "DOUBLE-CHARGED CINEMA",
        "Velocity and Danger",
        "Action and thriller cinema engineered for a rising pulse.",
        with_genres="28,53",
        **{"vote_count.gte": "180"},
    ),
    _discover_movie(
        "crimes-with-no-clean-answer",
        "THE PERFECT CRIME IS A QUESTION",
        "Crimes With No Clean Answer",
        "Crime and mystery stories where every solution opens another door.",
        with_genres="80,9648",
        **{"vote_count.gte": "140"},
    ),
    _discover_movie(
        "voyages-beyond-earth",
        "THE MAP ENDS AT THE STARS",
        "Voyages Beyond Earth",
        "Science fiction adventures built on discovery rather than gravity.",
        with_genres="878,12",
        **{"vote_count.gte": "180"},
    ),
    _discover_movie(
        "family-fantasy-portals",
        "WONDER OPENS THE DOOR",
        "Portals for the Whole Family",
        "Fantasy journeys with enough imagination for every generation.",
        with_genres="14,10751",
        **{"vote_count.gte": "100"},
    ),
    _discover_movie(
        "romance-with-a-punchline",
        "HEARTS WITH PERFECT TIMING",
        "Romance With a Punchline",
        "Love stories that understand laughter is part of the risk.",
        with_genres="10749,35",
        **{"vote_count.gte": "120"},
    ),
    _discover_movie(
        "history-under-fire",
        "THE PAST AT THE BREAKING POINT",
        "History Under Fire",
        "War and history films that find human lives inside enormous events.",
        with_genres="36,10752",
        **{"vote_count.gte": "100"},
    ),
    _discover_movie(
        "music-changes-everything",
        "WHEN SOUND BECOMES STORY",
        "Music Changes Everything",
        "Dramas where performance, rhythm, and identity share the stage.",
        with_genres="10402,18",
        **{"vote_count.gte": "100"},
    ),
    _discover_movie(
        "animated-family-odysseys",
        "HAND-DRAWN HEART, EPIC SCALE",
        "Animated Family Odysseys",
        "Animation and family adventure with worlds worth revisiting.",
        with_genres="16,10751",
        **{"vote_count.gte": "140"},
    ),
    _discover_movie(
        "music-behind-the-music",
        "TRUE STORIES IN RHYTHM",
        "The Music Behind the Music",
        "Documentaries that listen beyond the performance.",
        with_genres="99,10402",
        **{"vote_count.gte": "40"},
    ),
    _discover_movie(
        "horror-with-a-secret",
        "FEAR LOVES A MYSTERY",
        "Horror With a Secret",
        "Dark rooms, buried truths, and dread that arrives with the answer.",
        with_genres="27,9648",
        **{"vote_count.gte": "120"},
    ),
    _discover_series(
        "crime-dramas-that-tighten",
        "THE NET CLOSES SLOWLY",
        "Crime Dramas That Tighten",
        "Long-form investigations where loyalty and evidence collide.",
        with_genres="80,18",
        **{"vote_count.gte": "90"},
    ),
    _discover_series(
        "fantastic-futures-in-episodes",
        "NO LIMIT TO THE NEXT CHAPTER",
        "Fantastic Futures in Episodes",
        "Science-fiction and fantasy series built for deep immersion.",
        with_genres="10765",
        without_genres="16",
        **{"vote_count.gte": "100", "sort_by": "vote_average.desc"},
    ),
    _discover_series(
        "adventure-with-consequences",
        "THE JOURNEY CHANGES EVERYONE",
        "Adventure With Consequences",
        "Action, adventure, and drama with character at the centre.",
        with_genres="10759,18",
        **{"vote_count.gte": "80"},
    ),
    _discover_series(
        "family-comedy-rituals",
        "MAKE ROOM ON THE SOFA",
        "Family Comedy Rituals",
        "Warm, funny series made to become part of the household.",
        with_genres="10751,35",
        **{"vote_count.gte": "60"},
    ),
    _discover_series(
        "slow-burn-series-mysteries",
        "EVERY EPISODE KNOWS SOMETHING",
        "Slow-Burn Series Mysteries",
        "Drama and mystery that trusts the truth to take its time.",
        with_genres="9648,18",
        **{"vote_count.gte": "90", "sort_by": "vote_average.desc"},
    ),
    _discover_movie(
        "ninety-nine-minutes-or-less",
        "A COMPLETE STORY BEFORE MIDNIGHT",
        "99 Minutes or Less",
        "Lean feature films that waste neither a frame nor your evening.",
        **{"with_runtime.lte": "99", "vote_count.gte": "180", "sort_by": "vote_average.desc"},
    ),
    _discover_movie(
        "epics-over-two-and-a-half-hours",
        "CLEAR THE EVENING",
        "Epics Over Two and a Half Hours",
        "Large-canvas cinema that earns every minute of its running time.",
        **{"with_runtime.gte": "150", "vote_count.gte": "220", "sort_by": "vote_average.desc"},
    ),
    _discover_series(
        "one-season-complete-stories",
        "ONE SEASON, ONE COMPLETE ARC",
        "Limited Series, Lasting Impact",
        "Finite television stories designed with the ending already in sight.",
        with_type="2",
        **{"vote_count.gte": "50", "sort_by": "vote_average.desc"},
    ),
    _discover_movie(
        "box-office-titans",
        "CINEMA AT MAXIMUM SCALE",
        "Box-Office Titans",
        "Films whose theatrical reach became part of their story.",
        **{"sort_by": "revenue.desc", "vote_count.gte": "400"},
    ),
    _discover_movie(
        "acclaimed-underseen",
        "THE QUIETER MASTERPIECES",
        "Acclaimed, Not Obvious",
        "Highly rated films beyond the most saturated corner of the spotlight.",
        **{
            "sort_by": "vote_average.desc",
            "vote_average.gte": "7.2",
            "vote_count.gte": "100",
            "vote_count.lte": "1200",
        },
    ),
)

TMDB_BROWSE_RECIPES: tuple[TmdbSectionRecipe, ...] = (
    _PULSE_RECIPES
    + _MOVIE_GENRE_RECIPES
    + _SERIES_GENRE_RECIPES
    + _MOVIE_ERA_RECIPES
    + _SERIES_ERA_RECIPES
    + _WORLD_MOVIE_RECIPES
    + _WORLD_SERIES_RECIPES
    + _CRAFTED_RECIPES
)

if len(TMDB_BROWSE_RECIPES) != 100:  # pragma: no cover - import-time invariant
    raise RuntimeError(
        f"TMDB browse taxonomy must contain 100 sections, found {len(TMDB_BROWSE_RECIPES)}"
    )
if len({recipe.slug for recipe in TMDB_BROWSE_RECIPES}) != 100:  # pragma: no cover
    raise RuntimeError("TMDB browse section slugs must be unique")
if len({recipe.fingerprint for recipe in TMDB_BROWSE_RECIPES}) != 100:  # pragma: no cover
    raise RuntimeError("TMDB browse section queries must be genuinely distinct")


MOVIE_GENRES = {
    28: "Action",
    12: "Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    14: "Fantasy",
    36: "History",
    27: "Horror",
    10402: "Music",
    9648: "Mystery",
    10749: "Romance",
    878: "Science Fiction",
    10770: "TV Movie",
    53: "Thriller",
    10752: "War",
    37: "Western",
}

SERIES_GENRES = {
    10759: "Action & Adventure",
    16: "Animation",
    35: "Comedy",
    80: "Crime",
    99: "Documentary",
    18: "Drama",
    10751: "Family",
    10762: "Kids",
    9648: "Mystery",
    10763: "News",
    10764: "Reality",
    10765: "Sci-Fi & Fantasy",
    10766: "Soap",
    10767: "Talk",
    10768: "War & Politics",
    37: "Western",
}


@dataclass(frozen=True, slots=True)
class _CachedItems:
    fresh_until: float
    stale_until: float
    items: tuple[TmdbBrowseTitle, ...]
    status: Literal["ready", "stale", "unavailable"]


_cache_lock = Lock()
_cache: dict[tuple[str, str, tuple[str, tuple[tuple[str, str], ...]], int], _CachedItems] = {}
_key_locks: dict[tuple[str, str, tuple[str, tuple[tuple[str, str], ...]], int], Lock] = {}
_request_slots = BoundedSemaphore(TMDB_BROWSE_MAX_CONCURRENCY)


def clear_tmdb_browse_cache() -> None:
    """Clear process-local discovery data; primarily useful for tests and credential rotation."""
    with _cache_lock:
        _cache.clear()
        _key_locks.clear()


def _resolve_value(value: str) -> str:
    today = date.today()
    if value == "$today":
        return today.isoformat()
    if value == "$past_30_days":
        return (today - timedelta(days=30)).isoformat()
    return value


def _query_params(recipe: TmdbSectionRecipe) -> dict[str, str | int]:
    settings = get_settings()
    params: dict[str, str | int] = {
        "language": settings.tmdb_language,
        "region": settings.tmdb_region,
        "page": 1,
    }
    params.update({key: _resolve_value(value) for key, value in recipe.params})
    if recipe.endpoint.startswith("/trending/"):
        params["include_adult"] = "false"
    return params


def _cache_key(
    recipe: TmdbSectionRecipe, items_per_section: int
) -> tuple[str, str, tuple[str, tuple[tuple[str, str], ...]], int]:
    settings = get_settings()
    resolved_query = tuple(sorted((key, _resolve_value(value)) for key, value in recipe.params))
    return (
        settings.tmdb_language,
        settings.tmdb_region,
        (recipe.endpoint, resolved_query),
        items_per_section,
    )


def _section_item(item: dict, recipe: TmdbSectionRecipe) -> TmdbBrowseTitle | None:
    if item.get("adult") is True or not item.get("id") or not item.get("poster_path"):
        return None
    media_type = item.get("media_type")
    if media_type == "person":
        return None
    kind = (
        "series"
        if media_type == "tv" or (media_type is None and recipe.media_type == "series")
        else "movie"
    )
    if recipe.media_type == "mixed" and media_type not in {"movie", "tv"}:
        return None
    title = item.get("name") if kind == "series" else item.get("title")
    if not title:
        return None
    original_title = item.get("original_name") if kind == "series" else item.get("original_title")
    release = item.get("first_air_date") if kind == "series" else item.get("release_date")
    origin = item.get("origin_country") or []
    genre_lookup = SERIES_GENRES if kind == "series" else MOVIE_GENRES
    genres = [
        genre_lookup[genre_id] for genre_id in item.get("genre_ids", []) if genre_id in genre_lookup
    ]
    external_id = int(item["id"])
    return TmdbBrowseTitle(
        id=f"tmdb:{kind}:{external_id}",
        kind=kind,
        title=str(title),
        original_title=str(original_title) if original_title and original_title != title else None,
        slug=f"tmdb-{kind}-{external_id}",
        short_description=(item.get("overview") or "Synopsis is not available yet.")[:500],
        release_date=release or None,
        maturity_rating=None,
        poster_url=f"{TMDB_CARD_IMAGE}{item['poster_path']}",
        backdrop_url=(
            f"{TMDB_BACKDROP_IMAGE}{item['backdrop_path']}" if item.get("backdrop_path") else None
        ),
        content_format="tv" if kind == "series" else "movie",
        country_code=str(origin[0]) if origin else None,
        original_language_code=item.get("original_language"),
        studios=[],
        genres=genres,
        href=f"/external/tmdb/{kind}/{external_id}",
        source="tmdb",
        availability="Explore this title",
        vote_average=float(item.get("vote_average") or 0),
        vote_count=max(0, int(item.get("vote_count") or 0)),
        popularity=float(item.get("popularity") or 0),
    )


def _gateway_section_item(item: dict) -> TmdbBrowseTitle | None:
    aperture_id = str(item.get("aperture_id") or "")
    kind = str(item.get("media_type") or "")
    images = item.get("images") if isinstance(item.get("images"), dict) else {}
    if kind not in {"movie", "series"} or not aperture_id or not images.get("poster"):
        return None
    title = str(item.get("title") or "")
    if not title:
        return None
    return TmdbBrowseTitle(
        id=aperture_id,
        kind=kind,
        title=title,
        original_title=(
            str(item["original_title"])
            if item.get("original_title") and item.get("original_title") != title
            else None
        ),
        slug=aperture_id,
        short_description=str(item.get("synopsis") or "Synopsis is not available yet.")[:500],
        release_date=item.get("release_date") or None,
        maturity_rating=None,
        poster_url=images.get("poster"),
        backdrop_url=images.get("backdrop"),
        content_format="movie" if kind == "movie" else "tv",
        country_code=item.get("origin_country"),
        original_language_code=item.get("original_language"),
        studios=[str(value) for value in item.get("studios", [])],
        genres=[str(value) for value in item.get("genres", [])],
        duration_minutes=item.get("runtime_minutes"),
        season_count=max(0, int(item.get("season_count") or 0)),
        episode_count=max(0, int(item.get("episode_count") or 0)),
        href=f"/titles/{kind}/{aperture_id}",
        source="aperture",
        availability="Explore this title",
        vote_average=float(item.get("rating") or 0),
        vote_count=max(0, int(item.get("rating_count") or 0)),
        popularity=float(item.get("popularity") or 0),
    )


def _fresh_cached(key, now: float) -> _CachedItems | None:
    with _cache_lock:
        cached = _cache.get(key)
        if cached and cached.fresh_until > now:
            return cached
    return None


def _key_lock(key) -> Lock:
    with _cache_lock:
        return _key_locks.setdefault(key, Lock())


def _remember(key, cached: _CachedItems) -> None:
    with _cache_lock:
        if len(_cache) >= TMDB_BROWSE_MAX_CACHE_ENTRIES and key not in _cache:
            oldest_key = min(_cache, key=lambda candidate: _cache[candidate].fresh_until)
            _cache.pop(oldest_key, None)
            _key_locks.pop(oldest_key, None)
        _cache[key] = cached


def _failure_delay(error: Exception | None = None) -> int:
    if isinstance(error, MovieApiError) and error.status_code == 429:
        return max(30, min(error.retry_after or TMDB_BROWSE_FAILURE_CACHE_SECONDS, 10 * 60))
    if isinstance(error, httpx.HTTPStatusError) and error.response.status_code == 429:
        try:
            retry_after = int(error.response.headers.get("Retry-After", ""))
        except ValueError:
            retry_after = TMDB_BROWSE_FAILURE_CACHE_SECONDS
        return max(30, min(retry_after, 10 * 60))
    return TMDB_BROWSE_FAILURE_CACHE_SECONDS


def _failure_result(key, stale: _CachedItems | None, now: float, delay: int):
    if stale and stale.items and stale.stale_until > now:
        fallback = _CachedItems(
            fresh_until=now + delay,
            stale_until=stale.stale_until,
            items=stale.items,
            status="stale",
        )
        _remember(key, fallback)
        return list(fallback.items), "stale"
    unavailable = _CachedItems(
        fresh_until=now + delay,
        stale_until=now + delay,
        items=(),
        status="unavailable",
    )
    _remember(key, unavailable)
    return [], "unavailable"


def _load_items(
    recipe: TmdbSectionRecipe, items_per_section: int
) -> tuple[list[TmdbBrowseTitle], Literal["ready", "stale", "unavailable"]]:
    key = _cache_key(recipe, items_per_section)
    now = monotonic()
    cached = _fresh_cached(key, now)
    if cached:
        return list(cached.items), cached.status

    with _key_lock(key):
        now = monotonic()
        cached = _fresh_cached(key, now)
        if cached:
            return list(cached.items), cached.status
        with _cache_lock:
            stale = _cache.get(key)

        gateway = movie_api_enabled()
        client = None if gateway else _client()
        if not gateway and client is None:
            return _failure_result(
                key,
                stale,
                now,
                TMDB_BROWSE_FAILURE_CACHE_SECONDS,
            )

        try:
            if gateway:
                with _request_slots:
                    payload = movie_api_discovery(
                        movie_api_feed(recipe.endpoint),
                        _query_params(recipe),
                    )
                raw_items = payload.get("items", [])
            else:
                with _request_slots:
                    response = client.get(
                        f"{TMDB_API}{recipe.endpoint}",
                        params=_query_params(recipe),
                        timeout=TMDB_BROWSE_TIMEOUT,
                    )
                response.raise_for_status()
                payload = response.json()
                raw_items = payload.get("results", [])
            if not isinstance(raw_items, list):
                raise ValueError("TMDB results must be a list")
            items: list[TmdbBrowseTitle] = []
            seen: set[str] = set()
            for raw_item in raw_items:
                if not isinstance(raw_item, dict):
                    continue
                result = (
                    _gateway_section_item(raw_item) if gateway else _section_item(raw_item, recipe)
                )
                if result is None or result.id in seen:
                    continue
                seen.add(result.id)
                items.append(result)
                if len(items) == items_per_section:
                    break
            fresh = _CachedItems(
                fresh_until=now + TMDB_BROWSE_CACHE_SECONDS,
                stale_until=now + TMDB_BROWSE_STALE_SECONDS,
                items=tuple(items),
                status="ready",
            )
            _remember(key, fresh)
            return items, "ready"
        except (
            MovieApiError,
            httpx.HTTPError,
            ValueError,
            TypeError,
            KeyError,
            OverflowError,
        ) as error:
            return _failure_result(key, stale, now, _failure_delay(error))


def _render_section(recipe: TmdbSectionRecipe, items_per_section: int) -> TmdbBrowseSection:
    items, status = _load_items(recipe, items_per_section)
    return TmdbBrowseSection(
        id=f"aperture-section:{recipe.slug}",
        slug=recipe.slug,
        eyebrow=recipe.eyebrow,
        title=recipe.title,
        description=recipe.description,
        media_type=recipe.media_type,
        source="aperture" if movie_api_enabled() else "tmdb",
        status=status,
        items=items,
    )


def tmdb_browse_sections(
    *, page: int = 1, page_size: int = 6, items_per_section: int = 18
) -> TmdbBrowseSectionsResponse:
    """Load one deterministic page of curated TMDB rails with bounded parallelism."""
    offset = (page - 1) * page_size
    recipes = TMDB_BROWSE_RECIPES[offset : offset + page_size]
    if recipes:
        with ThreadPoolExecutor(max_workers=min(TMDB_BROWSE_MAX_CONCURRENCY, len(recipes))) as pool:
            sections = list(
                pool.map(lambda recipe: _render_section(recipe, items_per_section), recipes)
            )
    else:
        sections = []
    total = len(TMDB_BROWSE_RECIPES)
    has_more = offset + len(recipes) < total
    return TmdbBrowseSectionsResponse(
        page=page,
        page_size=page_size,
        total_sections=total,
        has_more=has_more,
        next_page=page + 1 if has_more else None,
        items_per_section=items_per_section,
        sections=sections,
        attribution=TmdbAttribution(
            notice=TMDB_ATTRIBUTION_NOTICE,
            url="https://www.themoviedb.org/",
        ),
        partial=any(section.status != "ready" for section in sections),
    )


def tmdb_trending_titles(*, page: int = 1) -> TmdbTrendingTitlesResponse:
    """Return a provider-ranked page from the mixed weekly trend feed.

    The provider gateway owns caching and credentials. The storefront keeps this
    response page-shaped so clients can progressively load well beyond 100 titles
    without downloading the complete discovery universe up front.
    """
    recipe = _PULSE_RECIPES[0]
    gateway = movie_api_enabled()
    source: Literal["aperture", "tmdb"] = "aperture" if gateway else "tmdb"
    try:
        if gateway:
            with _request_slots:
                payload = movie_api_discovery(
                    movie_api_feed(recipe.endpoint),
                    {**_query_params(recipe), "page": page},
                )
            raw_items = payload.get("items", [])
        else:
            client = _client()
            if client is None:
                raise MovieApiError("Trending metadata is not configured")
            with _request_slots:
                response = client.get(
                    f"{TMDB_API}{recipe.endpoint}",
                    params={**_query_params(recipe), "page": page},
                    timeout=TMDB_BROWSE_TIMEOUT,
                )
            response.raise_for_status()
            payload = response.json()
            raw_items = payload.get("results", [])
        if not isinstance(raw_items, list):
            raise ValueError("Trending results must be a list")

        items: list[TmdbBrowseTitle] = []
        seen: set[str] = set()
        for raw_item in raw_items:
            if not isinstance(raw_item, dict):
                continue
            item = _gateway_section_item(raw_item) if gateway else _section_item(raw_item, recipe)
            if item is None or item.id in seen:
                continue
            seen.add(item.id)
            items.append(item)

        total_pages = min(500, max(0, int(payload.get("total_pages") or 0)))
        total_results = max(len(items), int(payload.get("total_results") or 0))
        has_more = page < total_pages
        return TmdbTrendingTitlesResponse(
            page=page,
            page_size=min(20, len(raw_items)),
            total_results=total_results,
            total_pages=total_pages,
            has_more=has_more,
            next_page=page + 1 if has_more else None,
            source=source,
            status="ready",
            items=items,
            attribution=TmdbAttribution(notice=TMDB_ATTRIBUTION_NOTICE, url="https://www.themoviedb.org/"),
        )
    except (
        MovieApiError,
        httpx.HTTPError,
        ValueError,
        TypeError,
        KeyError,
        OverflowError,
    ):
        return TmdbTrendingTitlesResponse(
            page=page,
            page_size=0,
            total_results=0,
            total_pages=0,
            has_more=False,
            next_page=None,
            source=source,
            status="unavailable",
            items=[],
            attribution=TmdbAttribution(notice=TMDB_ATTRIBUTION_NOTICE, url="https://www.themoviedb.org/"),
        )
