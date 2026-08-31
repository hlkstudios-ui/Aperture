import uuid
from datetime import date, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.catalog_models import (
    Character,
    Credit,
    Episode,
    Genre,
    Movie,
    Person,
    Season,
    Series,
    Tag,
    Theme,
)
from app.db import SessionLocal
from app.main import app


def test_browse_pages_by_32_searches_characters_and_exposes_filter_facets() -> None:
    suffix = uuid.uuid4().hex[:10]
    query = f"Nebula {suffix}"
    character_name = f"Orchid{suffix}"
    genre_a_slug = f"velvet-mystery-{suffix}"
    genre_b_slug = f"solar-adventure-{suffix}"
    character_slug = f"orchid-{suffix}"
    genre_a = Genre(name=f"Velvet mystery {suffix}", slug=genre_a_slug)
    genre_b = Genre(name=f"Solar adventure {suffix}", slug=genre_b_slug)
    theme = Theme(name=f"Chosen paths {suffix}", slug=f"chosen-paths-{suffix}")
    tag = Tag(name=f"Rainlit {suffix}", slug=f"rainlit-{suffix}")
    character = Character(
        name=character_name,
        slug=character_slug,
        description="A character used to verify normalized browse search.",
    )
    person = Person(name=f"Browse performer {suffix}", slug=f"browse-performer-{suffix}")
    movies = [
        Movie(
            title=f"{query} movie {index:02d}",
            slug=f"browse-{suffix}-movie-{index:02d}",
            short_description="A deliberately searchable local catalog title.",
            synopsis="A browse pagination contract fixture.",
            release_date=date(1990, 1, 1) + timedelta(days=index * 365),
            runtime_minutes=25 if index == 0 else 60 if index == 1 else 100,
            maturity_rating="PG" if index == 0 else "R",
            status="published",
            content_format="movie",
            studios=[f"Aperture Unit {suffix}"],
        )
        for index in range(34)
    ]
    movies[0].genres = [genre_a]
    movies[0].themes = [theme]
    movies[0].tags = [tag]
    movies[1].genres = [genre_b]
    series = [
        Series(
            title=f"{query} series {index:02d}",
            slug=f"browse-{suffix}-series-{index:02d}",
            short_description="A deliberately searchable local catalog series.",
            synopsis="A browse pagination contract fixture.",
            release_date=date(2024 + index, 1, 1),
            maturity_rating="TV-PG",
            status="published",
            is_ongoing=index == 0,
            content_format="tv",
            studios=[f"Aperture Unit {suffix}"],
        )
        for index in range(2)
    ]
    series[0].genres = [genre_a]

    with SessionLocal() as db:
        db.add_all([genre_a, genre_b, theme, tag, character, person, *movies, *series])
        db.flush()
        season = Season(series_id=series[0].id, number=1, title="The first orbit")
        db.add(season)
        db.flush()
        episode = Episode(
            season_id=season.id,
            number=1,
            title="The masked signal",
            synopsis="The character appears in an episode-level normalized credit.",
            runtime_minutes=42,
            status="published",
        )
        db.add(episode)
        db.flush()
        credits = [
            Credit(
                movie_id=movies[0].id,
                person_id=person.id,
                character_id=character.id,
                role="Actor",
            ),
            Credit(
                episode_id=episode.id,
                person_id=person.id,
                character_id=character.id,
                role="Actor",
            ),
        ]
        db.add_all(credits)
        db.commit()
        movie_ids = [movie.id for movie in movies]
        series_ids = [record.id for record in series]
        credit_ids = [credit.id for credit in credits]
        episode_id = episode.id
        season_id = season.id
        character_id = character.id
        person_id = person.id
        genre_ids = [genre_a.id, genre_b.id]
        theme_id = theme.id
        tag_id = tag.id

    try:
        with TestClient(app) as client:
            first = client.get("/catalog/browse", params={"q": query})
            assert first.status_code == 200, first.text
            first_payload = first.json()
            assert first_payload["page"] == 1
            assert first_payload["page_size"] == 32
            assert first_payload["total"] == 36
            assert len(first_payload["items"]) == 32
            assert first_payload["has_more"] is True
            assert first_payload["next_page"] == 2
            assert first_payload["sort"] == "newest"
            assert first_payload["items"][0]["kind"] == "series"
            assert first_payload["items"][0]["is_ongoing"] is False

            second = client.get(
                "/catalog/browse",
                params={"q": query, "page": 2, "include_facets": "false"},
            )
            assert second.status_code == 200, second.text
            second_payload = second.json()
            assert len(second_payload["items"]) == 4
            assert second_payload["has_more"] is False
            assert second_payload["next_page"] is None
            assert second_payload["facet_groups"] == []
            assert {
                item["id"] for item in first_payload["items"]
            }.isdisjoint({item["id"] for item in second_payload["items"]})

            character_search = client.get("/catalog/browse", params={"q": character_name})
            assert character_search.status_code == 200, character_search.text
            character_payload = character_search.json()
            assert character_payload["total"] == 2
            assert {item["kind"] for item in character_payload["items"]} == {
                "movie",
                "series",
            }
            movie_item = next(
                item for item in character_payload["items"] if item["kind"] == "movie"
            )
            assert movie_item["duration_minutes"] == 25
            series_item = next(
                item for item in character_payload["items"] if item["kind"] == "series"
            )
            assert series_item["episode_count"] == 1
            assert series_item["is_ongoing"] is True

            character_filter = client.get(
                "/catalog/browse", params={"character": character_slug}
            )
            assert character_filter.status_code == 200, character_filter.text
            assert character_filter.json()["total"] == 2

            repeated_genres = client.get(
                "/catalog/browse",
                params=[
                    ("q", query),
                    ("genre", genre_a_slug),
                    ("genre", genre_b_slug),
                    ("kind", "movie"),
                ],
            )
            assert repeated_genres.status_code == 200, repeated_genres.text
            assert repeated_genres.json()["total"] == 2

            one_genre = client.get(
                "/catalog/browse", params={"q": query, "genre": genre_a_slug}
            )
            assert one_genre.status_code == 200, one_genre.text
            stable_taste = next(
                group for group in one_genre.json()["facet_groups"] if group["key"] == "taste"
            )
            stable_genres = next(
                facet for facet in stable_taste["facets"] if facet["key"] == "genre"
            )
            assert {option["value"] for option in stable_genres["options"]}.issuperset(
                {genre_a_slug, genre_b_slug}
            )

            cross_facet = client.get(
                "/catalog/browse",
                params=[
                    ("q", query),
                    ("genre", genre_a_slug),
                    ("genre", genre_b_slug),
                    ("maturity_rating", "PG"),
                ],
            )
            assert cross_facet.status_code == 200, cross_facet.text
            assert cross_facet.json()["total"] == 1

            facet_groups = {
                group["key"]: group for group in first_payload["facet_groups"]
            }
            assert set(facet_groups) == {"format", "taste", "origin", "time"}
            taste_facets = {
                facet["key"]: facet for facet in facet_groups["taste"]["facets"]
            }
            genre_counts = {
                option["value"]: option["count"]
                for option in taste_facets["genre"]["options"]
            }
            assert genre_counts[genre_a_slug] == 2
            assert genre_counts[genre_b_slug] == 1
            character_counts = {
                option["value"]: option["count"]
                for option in taste_facets["character"]["options"]
            }
            assert character_counts[character_slug] == 2
    finally:
        with SessionLocal() as db:
            db.execute(delete(Credit).where(Credit.id.in_(credit_ids)))
            db.execute(delete(Episode).where(Episode.id == episode_id))
            db.execute(delete(Season).where(Season.id == season_id))
            db.execute(delete(Series).where(Series.id.in_(series_ids)))
            db.execute(delete(Movie).where(Movie.id.in_(movie_ids)))
            db.execute(delete(Character).where(Character.id == character_id))
            db.execute(delete(Person).where(Person.id == person_id))
            db.execute(delete(Genre).where(Genre.id.in_(genre_ids)))
            db.execute(delete(Theme).where(Theme.id == theme_id))
            db.execute(delete(Tag).where(Tag.id == tag_id))
            db.commit()


def test_browse_query_validation_is_explicit() -> None:
    with TestClient(app) as client:
        for params in (
            {"page_size": 33},
            {"kind": "episode"},
            {"genre": "Not a slug"},
            {"release_decade": 2025},
            {"release_year_from": 2025, "release_year_to": 2020},
            {"runtime_minutes_min": 120, "runtime_minutes_max": 30},
            {"sort": "popular"},
        ):
            response = client.get("/catalog/browse", params=params)
            assert response.status_code == 422, (params, response.text)
