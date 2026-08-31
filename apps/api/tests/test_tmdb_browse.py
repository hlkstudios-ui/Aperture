from types import SimpleNamespace

import httpx
from fastapi.testclient import TestClient

from app import tmdb_browse_service, tmdb_discovery
from app.main import app
from app.tmdb_browse_service import TMDB_BROWSE_RECIPES


class _FakeResponse:
    def __init__(self, results: list[dict]):
        self._results = results

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return {"page": 1, "results": self._results, "total_pages": 12}


class _FakeClient:
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []
        self.fail = False

    def get(self, url: str, *, params: dict, timeout=None) -> _FakeResponse:
        self.calls.append((url, dict(params)))
        if self.fail:
            raise httpx.ConnectError("TMDB is temporarily unavailable")
        is_series = "/tv/" in url or url.endswith("/discover/tv")
        primary = {
            "id": 101 if not is_series else 202,
            "title": None if is_series else "A Real Movie",
            "name": "A Real Series" if is_series else None,
            "overview": "A genuine TMDB discovery result.",
            "poster_path": "/poster.jpg",
            "backdrop_path": "/backdrop.jpg",
            "release_date": "2025-04-12" if not is_series else None,
            "first_air_date": "2024-09-03" if is_series else None,
            "original_language": "en",
            "origin_country": ["CA"],
            "genre_ids": [18],
            "vote_average": 8.1,
            "vote_count": 812,
            "popularity": 92.5,
            "adult": False,
        }
        if "/trending/all/" in url:
            primary["media_type"] = "movie"
        duplicate = dict(primary)
        rejected_adult = {**primary, "id": 303, "adult": True}
        rejected_without_art = {**primary, "id": 404, "poster_path": None}
        return _FakeResponse([primary, duplicate, rejected_adult, rejected_without_art])


def test_tmdb_browse_registry_contains_100_distinct_movie_and_series_queries() -> None:
    assert len(TMDB_BROWSE_RECIPES) == 100
    assert len({recipe.slug for recipe in TMDB_BROWSE_RECIPES}) == 100
    assert len({recipe.fingerprint for recipe in TMDB_BROWSE_RECIPES}) == 100
    media_counts = {
        media_type: sum(recipe.media_type == media_type for recipe in TMDB_BROWSE_RECIPES)
        for media_type in ("movie", "series", "mixed")
    }
    assert media_counts == {"movie": 60, "series": 38, "mixed": 2}
    assert all(
        dict(recipe.params).get("include_adult") == "false"
        for recipe in TMDB_BROWSE_RECIPES
        if recipe.endpoint.startswith("/discover/")
    )


def test_tmdb_browse_endpoint_pages_sections_dedupes_and_caches(monkeypatch) -> None:
    fake = _FakeClient()
    tmdb_browse_service.clear_tmdb_browse_cache()
    monkeypatch.setattr(tmdb_browse_service, "_client", lambda: fake)

    with TestClient(app) as client:
        response = client.get(
            "/catalog/browse/sections",
            params={"page": 1, "page_size": 2, "items_per_section": 8},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["page"] == 1
        assert payload["page_size"] == 2
        assert payload["items_per_section"] == 8
        assert payload["total_sections"] == 100
        assert payload["has_more"] is True
        assert payload["next_page"] == 2
        assert payload["partial"] is False
        assert len(payload["sections"]) == 2
        assert [section["slug"] for section in payload["sections"]] == [
            recipe.slug for recipe in TMDB_BROWSE_RECIPES[:2]
        ]
        for section in payload["sections"]:
            assert section["source"] == "tmdb"
            assert section["status"] == "ready"
            assert len(section["items"]) == 1
            item = section["items"][0]
            assert item["source"] == "tmdb"
            assert item["poster_url"].endswith("/poster.jpg")
            assert item["backdrop_url"].endswith("/backdrop.jpg")
            assert item["genres"] == ["Drama"]
            assert item["availability"] == "Explore this title"
            assert item["href"].startswith("/external/tmdb/")
        assert payload["attribution"] == {
            "provider": "TMDB",
            "notice": "This product uses the TMDB API but is not endorsed or certified by TMDB.",
            "url": "https://www.themoviedb.org/",
        }
        assert len(fake.calls) == 2
        assert all(call[1]["include_adult"] == "false" for call in fake.calls)
        assert all("language" in call[1] and "region" in call[1] for call in fake.calls)

        cached = client.get(
            "/catalog/browse/sections",
            params={"page": 1, "page_size": 2, "items_per_section": 8},
        )
        assert cached.status_code == 200
        assert len(fake.calls) == 2


def test_tmdb_browse_returns_stable_partial_sections_without_credentials(monkeypatch) -> None:
    tmdb_browse_service.clear_tmdb_browse_cache()
    monkeypatch.setattr(tmdb_browse_service, "_client", lambda: None)

    with TestClient(app) as client:
        response = client.get(
            "/catalog/browse/sections",
            params={"page": 17, "page_size": 6, "items_per_section": 18},
        )
        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["total_sections"] == 100
        assert payload["has_more"] is False
        assert payload["next_page"] is None
        assert payload["partial"] is True
        assert len(payload["sections"]) == 4
        assert all(section["status"] == "unavailable" for section in payload["sections"])
        assert all(section["items"] == [] for section in payload["sections"])

        hundredth = client.get(
            "/catalog/browse/sections",
            params={"page": 100, "page_size": 1, "items_per_section": 18},
        )
        assert hundredth.status_code == 200
        assert len(hundredth.json()["sections"]) == 1
        assert hundredth.json()["has_more"] is False
        assert client.get("/catalog/browse/sections", params={"page": 101}).status_code == 422


def test_tmdb_trending_pages_the_gateway_mixed_weekly_feed(monkeypatch) -> None:
    calls: list[tuple[str, dict]] = []

    def gateway_discovery(feed: str, params: dict) -> dict:
        calls.append((feed, dict(params)))
        return {
            "page": 3,
            "total_results": 160,
            "total_pages": 8,
            "items": [
                {
                    "aperture_id": "amt_movie_trending",
                    "media_type": "movie",
                    "title": "The Moving Light",
                    "synopsis": "A weekly global favorite.",
                    "release_date": "2026-08-20",
                    "original_language": "en",
                    "origin_country": "CA",
                    "genres": ["Drama"],
                    "images": {"poster": "https://image.tmdb.org/t/p/w500/light.jpg"},
                    "rating": 8.4,
                    "rating_count": 1400,
                    "popularity": 94.2,
                },
                {
                    "aperture_id": "amt_series_trending",
                    "media_type": "series",
                    "title": "Night Signal",
                    "synopsis": "A series climbing the weekly chart.",
                    "release_date": "2026-08-18",
                    "original_language": "ja",
                    "origin_country": "JP",
                    "genres": ["Animation", "Mystery"],
                    "images": {"poster": "https://image.tmdb.org/t/p/w500/signal.jpg"},
                    "rating": 8.9,
                    "rating_count": 2100,
                    "popularity": 99.1,
                },
            ],
        }

    monkeypatch.setattr(tmdb_browse_service, "movie_api_enabled", lambda: True)
    monkeypatch.setattr(tmdb_browse_service, "movie_api_discovery", gateway_discovery)

    with TestClient(app) as client:
        response = client.get("/catalog/trending", params={"page": 3})

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["status"] == "ready"
    assert payload["source"] == "aperture"
    assert payload["page"] == 3
    assert payload["total_results"] == 160
    assert payload["has_more"] is True
    assert payload["next_page"] == 4
    assert [item["kind"] for item in payload["items"]] == ["movie", "series"]
    assert payload["items"][0]["href"] == "/titles/movie/amt_movie_trending"
    assert payload["items"][1]["vote_average"] == 8.9
    assert calls == [
        (
            "trending-all-week",
            {
                "language": "en-CA",
                "region": "CA",
                "page": 3,
                "include_adult": "false",
            },
        )
    ]
    assert client.get("/catalog/trending", params={"page": 501}).status_code == 422


def test_tmdb_browse_uses_stale_rail_when_upstream_fails(monkeypatch) -> None:
    fake = _FakeClient()
    clock = [100.0]
    tmdb_browse_service.clear_tmdb_browse_cache()
    monkeypatch.setattr(tmdb_browse_service, "_client", lambda: fake)
    monkeypatch.setattr(tmdb_browse_service, "monotonic", lambda: clock[0])

    first = tmdb_browse_service.tmdb_browse_sections(page=1, page_size=1, items_per_section=8)
    assert first.sections[0].status == "ready"
    assert first.sections[0].items

    clock[0] += tmdb_browse_service.TMDB_BROWSE_CACHE_SECONDS + 1
    fake.fail = True
    fallback = tmdb_browse_service.tmdb_browse_sections(page=1, page_size=1, items_per_section=8)
    assert fallback.partial is True
    assert fallback.sections[0].status == "stale"
    assert fallback.sections[0].items == first.sections[0].items


def test_tmdb_browse_respects_upstream_retry_after(monkeypatch) -> None:
    class RateLimitedClient:
        calls = 0

        def get(self, url: str, *, params: dict, timeout=None) -> httpx.Response:
            self.calls += 1
            return httpx.Response(
                429,
                headers={"Retry-After": "120"},
                request=httpx.Request("GET", url, params=params),
            )

    limited = RateLimitedClient()
    clock = [100.0]
    tmdb_browse_service.clear_tmdb_browse_cache()
    monkeypatch.setattr(tmdb_browse_service, "_client", lambda: limited)
    monkeypatch.setattr(tmdb_browse_service, "monotonic", lambda: clock[0])

    first = tmdb_browse_service.tmdb_browse_sections(page=1, page_size=1, items_per_section=8)
    assert first.sections[0].status == "unavailable"
    assert limited.calls == 1

    clock[0] += 90
    cached_failure = tmdb_browse_service.tmdb_browse_sections(
        page=1, page_size=1, items_per_section=8
    )
    assert cached_failure.sections[0].status == "unavailable"
    assert limited.calls == 1

    clock[0] += 31
    tmdb_browse_service.tmdb_browse_sections(page=1, page_size=1, items_per_section=8)
    assert limited.calls == 2


def test_tmdb_client_accepts_v3_api_key_when_bearer_token_is_absent(monkeypatch) -> None:
    tmdb_discovery._client.cache_clear()
    monkeypatch.setattr(
        tmdb_discovery,
        "get_settings",
        lambda: SimpleNamespace(
            tmdb_api_read_access_token=None,
            tmdb_api_key="tmdb-v3-key",
        ),
    )
    try:
        client = tmdb_discovery._client()
        assert client is not None
        assert client.params["api_key"] == "tmdb-v3-key"
        client.close()
    finally:
        tmdb_discovery._client.cache_clear()


def test_tmdb_cast_search_expands_known_for_titles_without_extra_requests(monkeypatch) -> None:
    fake = _FakeClient()
    known_title = {
        "id": 348,
        "media_type": "movie",
        "title": "Alien",
        "overview": "A crew encounters a lethal organism.",
        "poster_path": "/alien.jpg",
        "release_date": "1979-05-25",
        "original_language": "en",
        "adult": False,
    }
    duplicate = dict(known_title)
    adult_title = {**known_title, "id": 999, "title": "Hidden", "adult": True}

    def person_search(_url: str, *, params: dict, timeout=None) -> _FakeResponse:
        fake.calls.append((_url, dict(params)))
        return _FakeResponse(
            [
                {
                    "id": 10205,
                    "media_type": "person",
                    "name": "Sigourney Weaver",
                    "known_for": [known_title, duplicate, adult_title],
                }
            ]
        )

    fake.get = person_search  # type: ignore[method-assign]
    monkeypatch.setattr(tmdb_discovery, "_client", lambda: fake)
    monkeypatch.setattr(
        tmdb_discovery,
        "get_settings",
        lambda: SimpleNamespace(tmdb_language="en-US", tmdb_region="CA"),
    )

    results, total = tmdb_discovery.search_tmdb("Sigourney Weaver", 1)

    assert [item.title for item in results] == ["Alien"]
    assert results[0].href == "/external/tmdb/movie/348"
    assert total >= len(results)
    assert len(fake.calls) == 1
