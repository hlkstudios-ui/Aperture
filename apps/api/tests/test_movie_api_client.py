import httpx

from app import movie_api_client


def test_gateway_client_keeps_credentials_server_side_and_maps_safe_feed(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer server-only-key"
        assert request.url.path == "/v1/discovery/movie"
        assert request.url.params["with_genres"] == "18"
        assert "include_adult" not in request.url.params
        return httpx.Response(
            200,
            json={"feed": "movie", "items": [], "page": 1, "total_results": 0},
        )

    client = httpx.Client(
        base_url="https://movies.internal.example",
        headers={"Authorization": "Bearer server-only-key"},
        transport=httpx.MockTransport(handler),
    )
    monkeypatch.setattr(movie_api_client, "_client", lambda: client)
    result = movie_api_client.movie_api_discovery(
        movie_api_client.movie_api_feed("/discover/movie"),
        {"with_genres": "18", "include_adult": "false"},
    )
    assert result["feed"] == "movie"


def test_gateway_client_returns_controlled_failure_for_revoked_key(monkeypatch) -> None:
    client = httpx.Client(
        base_url="https://movies.internal.example",
        transport=httpx.MockTransport(lambda _request: httpx.Response(401, json={})),
    )
    monkeypatch.setattr(movie_api_client, "_client", lambda: client)
    try:
        movie_api_client.movie_api_search("Interstellar", 1)
    except movie_api_client.MovieApiError as error:
        assert error.status_code == 401
    else:  # pragma: no cover
        raise AssertionError("A revoked client key must fail closed")
