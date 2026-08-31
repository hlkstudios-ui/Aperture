from difflib import get_close_matches
from functools import lru_cache
from threading import Lock
from time import monotonic

import httpx

from app.config import get_settings
from app.movie_api_client import (
    MovieApiError,
    movie_api_enabled,
    movie_api_search,
    movie_api_title,
    movie_api_trending,
)
from app.search_schemas import UniversalTitleResult

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/original"
TMDB_CARD_IMAGE = "https://image.tmdb.org/t/p/w500"
TMDB_BACKDROP_IMAGE = "https://image.tmdb.org/t/p/w780"
TMDB_TRENDING_TTL_SECONDS = 600
_trending_lock = Lock()
_trending_cache: tuple[float, dict] | None = None


@lru_cache(maxsize=1)
def _popular_movie_titles() -> tuple[str, ...]:
    """Small typo-recovery corpus; cached so normal searches remain one request."""
    client = _client()
    if client is None:
        return ()
    titles: list[str] = []
    try:
        for page in range(1, 6):
            response = client.get(
                f"{TMDB_API}/movie/popular",
                params={"page": page, "language": get_settings().tmdb_language},
            )
            response.raise_for_status()
            titles.extend(
                item["title"] for item in response.json().get("results", []) if item.get("title")
            )
    except (httpx.HTTPError, ValueError):
        return ()
    return tuple(dict.fromkeys(titles))


@lru_cache(maxsize=1)
def _client() -> httpx.Client | None:
    settings = get_settings()
    if settings.tmdb_api_read_access_token:
        return httpx.Client(
            headers={"Authorization": f"Bearer {settings.tmdb_api_read_access_token}"},
            timeout=httpx.Timeout(8, connect=3),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    if settings.tmdb_api_key:
        return httpx.Client(
            params={"api_key": settings.tmdb_api_key},
            timeout=httpx.Timeout(8, connect=3),
            limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
        )
    return None


def _result(item: dict, kind: str) -> UniversalTitleResult:
    external_id = str(item["id"])
    title = item.get("title") or item.get("name") or "Untitled"
    original = item.get("original_title") or item.get("original_name")
    release = item.get("release_date") or item.get("first_air_date") or None
    return UniversalTitleResult(
        id=f"tmdb:{kind}:{external_id}",
        kind=kind,
        title=title,
        original_title=original if original != title else None,
        slug=f"tmdb-{external_id}",
        short_description=(item.get("overview") or "Synopsis is not available yet.")[:500],
        release_date=release or None,
        maturity_rating=None,
        poster_url=f"{TMDB_IMAGE}{item['poster_path']}" if item.get("poster_path") else None,
        content_format="movie" if kind == "movie" else "tv",
        country_code=None,
        original_language_code=item.get("original_language"),
        studios=[],
        genres=[],
        season_count=int(item.get("number_of_seasons") or 0),
        episode_count=int(item.get("number_of_episodes") or 0),
        href=f"/external/tmdb/{kind}/{external_id}",
        source="tmdb",
        availability="Explore this title",
    )


def _gateway_result(item: dict) -> UniversalTitleResult:
    kind = str(item.get("media_type"))
    aperture_id = str(item.get("aperture_id") or "")
    if kind not in {"movie", "series"} or not aperture_id:
        raise ValueError("Aperture Movie API title identity is invalid")
    images = item.get("images") if isinstance(item.get("images"), dict) else {}
    title = str(item.get("title") or "Untitled")
    return UniversalTitleResult(
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
    )


def search_tmdb(query: str, page: int) -> tuple[list[UniversalTitleResult], int]:
    if movie_api_enabled():
        try:
            payload = movie_api_search(query, page)
            items = payload.get("items", [])
            results = [_gateway_result(item) for item in items if isinstance(item, dict)]
            return results, max(len(results), int(payload.get("total_results") or 0))
        except (MovieApiError, ValueError, TypeError, KeyError):
            return [], 0
    client = _client()
    if client is None:
        return [], 0
    settings = get_settings()
    try:
        response = client.get(
            f"{TMDB_API}/search/multi",
            params={
                "query": query,
                "page": page,
                "include_adult": "false",
                "language": settings.tmdb_language,
                "region": settings.tmdb_region,
            },
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return [], 0
    candidates: list[dict] = []
    for item in payload.get("results", []):
        if item.get("media_type") in {"movie", "tv"}:
            candidates.append(item)
        elif item.get("media_type") == "person":
            # TMDB multi-search embeds a person's best-known credits. Expanding
            # those records makes cast searches lead to the films and series
            # viewers are actually trying to find, without an N+1 API fan-out.
            candidates.extend(
                credit
                for credit in item.get("known_for", [])
                if isinstance(credit, dict) and credit.get("media_type") in {"movie", "tv"}
            )
    results: list[UniversalTitleResult] = []
    seen: set[str] = set()
    for item in candidates:
        if item.get("adult") is True:
            continue
        result = _result(item, "movie" if item["media_type"] == "movie" else "series")
        if result.id in seen:
            continue
        seen.add(result.id)
        results.append(result)
    total = max(len(results), int(payload.get("total_results") or 0))
    if not results and page == 1:
        correction = get_close_matches(query, _popular_movie_titles(), n=1, cutoff=0.72)
        if correction and correction[0].casefold() != query.casefold():
            return search_tmdb(correction[0], page)
    return results, total


def tmdb_trending() -> dict:
    """Return a short, cached global pulse without blocking the dashboard on failure."""
    if movie_api_enabled():
        try:
            payload = movie_api_trending()

            def normalize(item: dict) -> dict:
                images = item.get("images") if isinstance(item.get("images"), dict) else {}
                return {
                    "external_id": str(item["aperture_id"]),
                    "title": str(item.get("title") or "Untitled"),
                    "overview": str(item.get("synopsis") or "")[:280],
                    "release_date": item.get("release_date") or None,
                    "poster_url": images.get("poster"),
                    "backdrop_url": images.get("backdrop"),
                    "popularity": float(item.get("popularity") or 0),
                    "vote_average": float(item.get("rating") or 0),
                }

            return {
                "available": True,
                "movies": [normalize(item) for item in payload.get("movies", [])[:6]],
                "series": [normalize(item) for item in payload.get("series", [])[:6]],
            }
        except (MovieApiError, ValueError, TypeError, KeyError):
            return {"available": False, "movies": [], "series": []}
    global _trending_cache
    now = monotonic()
    with _trending_lock:
        if _trending_cache and _trending_cache[0] > now:
            return _trending_cache[1]
    client = _client()
    if client is None:
        return {"available": False, "movies": [], "series": []}
    settings = get_settings()

    def load(media_type: str) -> list[dict]:
        response = client.get(
            f"{TMDB_API}/trending/{media_type}/day",
            params={"language": settings.tmdb_language},
        )
        response.raise_for_status()
        items = response.json().get("results", [])
        return [
            {
                "external_id": int(item["id"]),
                "title": item.get("title") or item.get("name") or "Untitled",
                "overview": (item.get("overview") or "")[:280],
                "release_date": item.get("release_date") or item.get("first_air_date") or None,
                "poster_url": (
                    f"{TMDB_CARD_IMAGE}{item['poster_path']}" if item.get("poster_path") else None
                ),
                "backdrop_url": (
                    f"{TMDB_BACKDROP_IMAGE}{item['backdrop_path']}"
                    if item.get("backdrop_path")
                    else None
                ),
                "popularity": float(item.get("popularity") or 0),
                "vote_average": float(item.get("vote_average") or 0),
            }
            for item in items[:6]
        ]

    try:
        payload = {"available": True, "movies": load("movie"), "series": load("tv")}
    except (httpx.HTTPError, ValueError, TypeError, KeyError):
        return {"available": False, "movies": [], "series": []}
    with _trending_lock:
        _trending_cache = (now + TMDB_TRENDING_TTL_SECONDS, payload)
    return payload


def tmdb_title(kind: str, external_id: int | str) -> UniversalTitleResult | None:
    if kind not in {"movie", "series"}:
        return None
    if movie_api_enabled():
        try:
            result = _gateway_result(movie_api_title(str(external_id)))
            return result if result.kind == kind else None
        except (MovieApiError, ValueError, TypeError, KeyError):
            return None
    client = _client()
    if client is None:
        return None
    endpoint_kind = "movie" if kind == "movie" else "tv"
    try:
        response = client.get(
            f"{TMDB_API}/{endpoint_kind}/{external_id}",
            params={"language": get_settings().tmdb_language},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    result = _result(item, kind)
    result.genres = [genre["name"] for genre in item.get("genres", [])]
    result.studios = [company["name"] for company in item.get("production_companies", [])][:12]
    result.country_code = next(iter(item.get("origin_country", [])), None)
    return result


def aperture_title(aperture_id: str) -> UniversalTitleResult | None:
    if not movie_api_enabled():
        return None
    try:
        return _gateway_result(movie_api_title(aperture_id))
    except (MovieApiError, ValueError, TypeError, KeyError):
        return None


def tmdb_movie_import_data(external_id: int | str) -> dict | None:
    """Return the small, provider-owned metadata subset needed for a draft import."""
    if movie_api_enabled():
        try:
            item = movie_api_title(str(external_id))
        except MovieApiError:
            return None
        if item.get("media_type") != "movie":
            return None
        images = item.get("images") if isinstance(item.get("images"), dict) else {}
        return {
            "external_id": str(item["aperture_id"]),
            "title": str(item.get("title") or "Untitled"),
            "original_title": item.get("original_title"),
            "overview": item.get("synopsis") or "Synopsis is not available yet.",
            "release_date": item.get("release_date") or None,
            "runtime_minutes": max(1, int(item.get("runtime_minutes") or 90)),
            "original_language_code": item.get("original_language"),
            "country_code": item.get("origin_country"),
            "poster_url": images.get("poster"),
            "backdrop_url": images.get("backdrop"),
            "genres": [str(value) for value in item.get("genres", [])],
            "studios": [str(value) for value in item.get("studios", [])][:12],
        }
    client = _client()
    if client is None:
        return None
    try:
        response = client.get(
            f"{TMDB_API}/movie/{external_id}",
            params={"language": get_settings().tmdb_language},
        )
        if response.status_code == 404:
            return None
        response.raise_for_status()
        item = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    return {
        "external_id": str(item["id"]),
        "title": item.get("title") or "Untitled",
        "original_title": item.get("original_title"),
        "overview": item.get("overview") or "Synopsis is not available yet.",
        "release_date": item.get("release_date") or None,
        "runtime_minutes": max(1, int(item.get("runtime") or 90)),
        "original_language_code": item.get("original_language") or None,
        "country_code": next(iter(item.get("origin_country", [])), None),
        "poster_url": f"{TMDB_IMAGE}{item['poster_path']}" if item.get("poster_path") else None,
        "backdrop_url": (
            f"{TMDB_IMAGE}{item['backdrop_path']}" if item.get("backdrop_path") else None
        ),
        "genres": [genre["name"] for genre in item.get("genres", [])],
        "studios": [company["name"] for company in item.get("production_companies", [])][:12],
    }
