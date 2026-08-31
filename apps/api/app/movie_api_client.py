from __future__ import annotations

from functools import lru_cache
from typing import Any
from urllib.parse import urlparse

import httpx

from app.config import get_settings


class MovieApiError(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 503, retry_after: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def movie_api_enabled() -> bool:
    settings = get_settings()
    return (
        settings.app_env != "test"
        and settings.movie_metadata_mode == "gateway"
        and settings.aperture_movie_api_origin is not None
        and bool(settings.aperture_movie_api_key)
    )


@lru_cache(maxsize=1)
def _client() -> httpx.Client | None:
    if not movie_api_enabled():
        return None
    settings = get_settings()
    origin = str(settings.aperture_movie_api_origin).rstrip("/")
    parsed = urlparse(origin)
    if settings.app_env in {"staging", "production"} and parsed.scheme != "https":
        raise RuntimeError("Aperture Movie API must use HTTPS outside local development")
    return httpx.Client(
        base_url=origin,
        headers={
            "Authorization": f"Bearer {settings.aperture_movie_api_key}",
            "Accept": "application/json",
            "User-Agent": "ApertureStorefront/1.0",
        },
        timeout=httpx.Timeout(9, connect=3),
        limits=httpx.Limits(max_connections=30, max_keepalive_connections=15),
    )


def _get(path: str, *, params: dict[str, Any] | None = None) -> dict:
    client = _client()
    if client is None:
        raise MovieApiError("Aperture Movie API is not configured")
    try:
        response = client.get(path, params=params)
    except httpx.HTTPError as error:
        raise MovieApiError("Aperture Movie API is unavailable") from error
    if response.status_code == 404:
        raise MovieApiError("Movie metadata was not found", status_code=404)
    if not response.is_success:
        raw_retry = response.headers.get("Retry-After")
        retry_after = int(raw_retry) if raw_retry and raw_retry.isdigit() else None
        raise MovieApiError(
            "Aperture Movie API request failed",
            status_code=response.status_code,
            retry_after=retry_after,
        )
    try:
        payload = response.json()
    except ValueError as error:
        raise MovieApiError("Aperture Movie API returned invalid JSON") from error
    if not isinstance(payload, dict):
        raise MovieApiError("Aperture Movie API returned an invalid response")
    return payload


def movie_api_search(query: str, page: int) -> dict:
    settings = get_settings()
    return _get(
        "/v1/search",
        params={
            "q": query,
            "page": page,
            "language": settings.tmdb_language,
            "region": settings.tmdb_region,
        },
    )


def movie_api_title(aperture_id: str) -> dict:
    settings = get_settings()
    return _get(
        f"/v1/titles/{aperture_id}",
        params={"language": settings.tmdb_language},
    )


def movie_api_discovery(feed: str, params: dict[str, str | int]) -> dict:
    safe_params = {
        name: value
        for name, value in params.items()
        if name not in {"include_adult", "include_video"}
    }
    return _get(f"/v1/discovery/{feed}", params=safe_params)


MOVIE_API_FEEDS = {
    "/discover/movie": "movie",
    "/discover/tv": "series",
    "/trending/all/day": "trending-all-day",
    "/trending/all/week": "trending-all-week",
    "/trending/movie/day": "trending-movie-day",
    "/trending/movie/week": "trending-movie-week",
    "/trending/tv/day": "trending-series-day",
    "/trending/tv/week": "trending-series-week",
    "/movie/now_playing": "movie-now-playing",
    "/movie/upcoming": "movie-upcoming",
    "/movie/popular": "movie-popular",
    "/movie/top_rated": "movie-top-rated",
    "/tv/airing_today": "series-airing-today",
    "/tv/on_the_air": "series-on-the-air",
    "/tv/popular": "series-popular",
    "/tv/top_rated": "series-top-rated",
}


def movie_api_feed(endpoint: str) -> str:
    try:
        return MOVIE_API_FEEDS[endpoint]
    except KeyError as error:
        raise MovieApiError("The discovery feed is not supported", status_code=422) from error


def movie_api_trending() -> dict:
    settings = get_settings()
    return _get(
        "/v1/trending",
        params={"language": settings.tmdb_language, "region": settings.tmdb_region},
    )
