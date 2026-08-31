import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.catalog_models import Credit, Genre, Movie, Person
from app.db import SessionLocal
from app.main import app
from app.routes import customer_catalog
from app.search_schemas import UniversalTitleResult


def tmdb_result(external_id: str) -> UniversalTitleResult:
    return UniversalTitleResult(
        id=f"tmdb:movie:{external_id}",
        kind="movie",
        title=f"External title {external_id}",
        original_title=None,
        slug=f"tmdb-{external_id}",
        short_description="A TMDB search result.",
        release_date=None,
        maturity_rating=None,
        poster_url=None,
        content_format="movie",
        country_code=None,
        original_language_code="en",
        studios=[],
        genres=[],
        href=f"/external/tmdb/movie/{external_id}",
        source="tmdb",
        availability="Global discovery result",
    )


def test_universal_search_finds_titles_through_metadata_and_supports_pagination() -> None:
    suffix = uuid.uuid4().hex[:10]
    with SessionLocal() as db:
        genre = Genre(name=f"Clockwork {suffix}", slug=f"clockwork-{suffix}")
        person = Person(name=f"Mira Searcher {suffix}", slug=f"mira-searcher-{suffix}")
        movie = Movie(
            title=f"Universal Horizon {suffix}",
            slug=f"universal-horizon-{suffix}",
            original_title=f"Horizonte {suffix}",
            short_description="A searchable catalog fixture.",
            synopsis=f"The hidden phrase nebula-{suffix} appears only in this synopsis.",
            runtime_minutes=94,
            status="published",
            studios=[f"Northstar {suffix}"],
            genres=[genre],
        )
        db.add_all((person, movie))
        db.flush()
        db.add(Credit(movie_id=movie.id, person_id=person.id, role="Director"))
        db.commit()
        ids = movie.id, person.id, genre.id

    with TestClient(app) as client:
        for query in (
            f"nebula-{suffix}",
            f"Mira Searcher {suffix}",
            f"Northstar {suffix}",
            f"Clockwork {suffix}",
            f"Horizonte {suffix}",
        ):
            response = client.get("/catalog/search", params={"q": query, "page_size": 1})
            assert response.status_code == 200, response.text
            assert response.json()["titles"][0]["slug"] == f"universal-horizon-{suffix}"
        page = client.get("/catalog/search", params={"q": suffix, "page": 1, "page_size": 1})
        assert page.json()["page"] == 1
        assert page.json()["page_size"] == 1

    with SessionLocal() as db:
        db.execute(delete(Credit).where(Credit.movie_id == ids[0]))
        db.execute(delete(Movie).where(Movie.id == ids[0]))
        db.execute(delete(Person).where(Person.id == ids[1]))
        db.execute(delete(Genre).where(Genre.id == ids[2]))
        db.commit()


def test_universal_search_counts_only_actual_tmdb_overlap(monkeypatch) -> None:
    suffix = uuid.uuid4().hex[:10]
    local_external_ids = (f"{suffix}-local-1", f"{suffix}-local-2")
    movies = [
        Movie(
            title=f"Overlap search {suffix} {number}",
            slug=f"overlap-search-{suffix}-{number}",
            original_title=None,
            short_description="A local TMDB-backed search fixture.",
            synopsis="A local TMDB-backed search fixture.",
            runtime_minutes=90,
            status="published",
            metadata_provider="tmdb",
            external_id=external_id,
        )
        for number, external_id in enumerate(local_external_ids, start=1)
    ]
    with SessionLocal() as db:
        db.add_all(movies)
        db.commit()
        movie_ids = [movie.id for movie in movies]

    external = [tmdb_result(f"{suffix}-external-{number}") for number in range(3)]
    monkeypatch.setattr(customer_catalog, "search_tmdb", lambda _query, _page: (external, 13))

    try:
        with TestClient(app) as client:
            response = client.get(
                "/catalog/search", params={"q": suffix, "page": 1, "page_size": 5}
            )
            assert response.status_code == 200, response.text
            without_overlap = response.json()

            external[0] = tmdb_result(local_external_ids[0])
            response = client.get(
                "/catalog/search", params={"q": suffix, "page": 1, "page_size": 5}
            )
            assert response.status_code == 200, response.text
            with_overlap = response.json()
    finally:
        with SessionLocal() as db:
            db.execute(delete(Movie).where(Movie.id.in_(movie_ids)))
            db.commit()

    assert len(without_overlap["titles"]) == 5
    assert without_overlap["total_titles"] == 15
    assert without_overlap["has_more"] is True
    assert len(with_overlap["titles"]) == 4
    assert with_overlap["total_titles"] == 14
    assert with_overlap["has_more"] is True
