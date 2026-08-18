import httpx

from app.config import get_settings
from app.search_schemas import UniversalTitleResult

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMAGE = "https://image.tmdb.org/t/p/original"


def _client() -> httpx.Client | None:
    settings = get_settings()
    if settings.tmdb_api_read_access_token:
        return httpx.Client(
            headers={"Authorization": f"Bearer {settings.tmdb_api_read_access_token}"}, timeout=8
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
        short_description=(item.get("overview") or "Additional details are available from TMDB.")[
            :500
        ],
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
        availability="Global discovery result",
    )


def search_tmdb(query: str, page: int) -> tuple[list[UniversalTitleResult], int]:
    client = _client()
    if client is None:
        return [], 0
    settings = get_settings()
    try:
        with client:
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
    results = [
        _result(item, "movie" if item["media_type"] == "movie" else "series")
        for item in payload.get("results", [])
        if item.get("media_type") in {"movie", "tv"}
    ]
    return results, int(payload.get("total_results") or len(results))


def tmdb_title(kind: str, external_id: int) -> UniversalTitleResult | None:
    if kind not in {"movie", "series"}:
        return None
    client = _client()
    if client is None:
        return None
    endpoint_kind = "movie" if kind == "movie" else "tv"
    try:
        with client:
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
