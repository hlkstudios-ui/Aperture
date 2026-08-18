import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.catalog_models import Credit, Genre, Movie, Person
from app.db import SessionLocal
from app.main import app


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
