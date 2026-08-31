import uuid

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.catalog_models import CatalogStatus, Character, Genre, Movie, Person
from app.curation_models import (
    Collection,
    CollectionItem,
    CollectionKind,
    CurationStatus,
    Journey,
    JourneyChapter,
    JourneyItem,
)
from app.db import SessionLocal
from app.main import app
from app.routes import customer_catalog
from app.search_schemas import UniversalTitleResult


def tmdb_playback_result(external_id: str) -> UniversalTitleResult:
    return UniversalTitleResult(
        id=f"tmdb:movie:{external_id}",
        kind="movie",
        title="Playback",
        original_title=None,
        slug=f"playback-tmdb-{external_id}",
        short_description="A legitimate TMDB discovery result.",
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


def test_public_routes_quarantine_fixture_titles_and_orphan_metadata(monkeypatch) -> None:
    token = uuid.uuid4().hex[:10]
    fixture_slug = f"club-film-{token}"
    person_slug = f"playback-actor-{token}"
    character_slug = f"playback-character-{token}"
    genre_slug = f"drama-{token}"
    collection_slug = f"movement-{token}"
    journey_slug = f"journey-{token}"
    with SessionLocal() as db:
        fixture = Movie(
            title=f"Club Film {token}",
            slug=fixture_slug,
            short_description="Club fixture.",
            synopsis="Synthetic data that must never cross the public boundary.",
            runtime_minutes=90,
            status=CatalogStatus.published,
        )
        legitimate = Movie(
            title=f"Legitimate release {token}",
            slug=f"visible-{token}",
            short_description="A public title used to prove mixed curation remains usable.",
            synopsis="Public catalog record.",
            runtime_minutes=95,
            status=CatalogStatus.published,
            metadata_provider="tmdb",
            external_id=f"boundary-{token}",
        )
        person = Person(name=f"Playback Actor {token}", slug=person_slug)
        character = Character(name=f"Playback Character {token}", slug=character_slug)
        genre = Genre(name=f"Drama {token}", slug=genre_slug)
        collection = Collection(
            slug=collection_slug,
            title="A film movement",
            description="An ordered collection",
            kind=CollectionKind.movement,
            status=CurationStatus.published,
        )
        journey = Journey(
            slug=journey_slug,
            title="A film journey",
            description="Learn in sequence",
            status=CurationStatus.published,
        )
        db.add_all((fixture, legitimate))
        db.flush()
        collection.items.append(CollectionItem(position=0, movie_id=fixture.id))
        hidden_chapter = JourneyChapter(position=0, title="Synthetic chapter")
        hidden_chapter.items.append(JourneyItem(position=0, movie_id=fixture.id))
        visible_chapter = JourneyChapter(position=1, title="Public chapter")
        visible_chapter.items.append(JourneyItem(position=0, movie_id=legitimate.id))
        journey.chapters.extend((hidden_chapter, visible_chapter))
        db.add_all((person, character, genre, collection, journey))
        db.commit()
        ids = {
            "movie": fixture.id,
            "legitimate_movie": legitimate.id,
            "person": person.id,
            "character": character.id,
            "genre": genre.id,
            "collection": collection.id,
            "journey": journey.id,
        }

    monkeypatch.setattr(
        customer_catalog,
        "search_tmdb",
        lambda _query, _page: ([tmdb_playback_result(token)], 1),
    )
    try:
        with TestClient(app) as client:
            search = client.get("/catalog/search", params={"q": "Playback"})
            assert search.status_code == 200, search.text
            assert {str(ids["person"]), str(ids["character"])}.isdisjoint(
                {entity["id"] for entity in search.json()["entities"]}
            )
            assert any(
                title["title"] == "Playback" and title["source"] == "tmdb"
                for title in search.json()["titles"]
            )

            assert client.get(f"/catalog/movies/{fixture_slug}").status_code == 404
            assert (
                client.get(f"/catalog/movies/{fixture_slug}/playback-availability").status_code
                == 404
            )
            assert client.get(f"/catalog/metadata/people/{person_slug}").status_code == 404
            assert client.get(f"/catalog/metadata/characters/{character_slug}").status_code == 404
            assert client.get(f"/catalog/metadata/genres/{genre_slug}").status_code == 404
            assert client.get(f"/catalog/people/{person_slug}/credits").status_code == 404

            assert all(
                item["slug"] != collection_slug
                for item in client.get("/curation/collections").json()
            )
            assert client.get(f"/curation/collections/{collection_slug}").status_code == 404
            public_journey = client.get(f"/curation/journeys/{journey_slug}")
            assert public_journey.status_code == 200, public_journey.text
            assert [chapter["title"] for chapter in public_journey.json()["chapters"]] == [
                "Public chapter"
            ]
            assert public_journey.json()["chapters"][0]["items"][0]["slug"] == (
                f"visible-{token}"
            )
    finally:
        with SessionLocal() as db:
            db.execute(delete(Collection).where(Collection.id == ids["collection"]))
            db.execute(delete(Journey).where(Journey.id == ids["journey"]))
            db.execute(delete(Movie).where(Movie.id == ids["movie"]))
            db.execute(delete(Movie).where(Movie.id == ids["legitimate_movie"]))
            db.execute(delete(Person).where(Person.id == ids["person"]))
            db.execute(delete(Character).where(Character.id == ids["character"]))
            db.execute(delete(Genre).where(Genre.id == ids["genre"]))
            db.commit()
