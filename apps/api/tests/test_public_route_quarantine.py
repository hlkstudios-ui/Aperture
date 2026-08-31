import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.after_credits_service import after_credits_room
from app.catalog_models import (
    CatalogStatus,
    Credit,
    Episode,
    Franchise,
    Genre,
    Movie,
    Person,
    Season,
    Series,
)
from app.club_models import ClubScheduledWatch, ClubWatchHistory
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
from app.knowledge_service import credit_destination, film_graph
from app.main import app
from app.models import PlaybackSource, Profile, User, ViewingActivity, WatchProgress
from app.passport_service import passport_report
from app.prescription_service import prescribe
from app.recommendation_schemas import PrescriptionRequest
from app.recommendation_service import recommend
from app.routes.playback import playable_source
from app.taste_service import taste_dna


def test_quarantined_title_cannot_reenter_through_customer_features() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"public-boundary-{token}@example.com"
    password = "PublicBoundaryPassword123"
    hidden_slug = f"club-film-{token}"
    public_slug = f"boundary-release-{token}"
    person_slug = f"boundary-artist-{token}"
    genre_slug = f"boundary-genre-{token}"
    franchise_slug = f"boundary-franchise-{token}"
    series_slug = f"boundary-series-{token}"
    list_slug = f"boundary-list-{token}"
    journey_slug = f"boundary-journey-{token}"

    try:
        with TestClient(app) as client:
            registration = client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": password,
                    "profile_name": "Boundary Viewer",
                },
            )
            assert registration.status_code == 201, registration.text
            profile_id = uuid.UUID(registration.json()["active_profile_id"])

            with SessionLocal() as db:
                franchise = Franchise(
                    name=f"Boundary Franchise {token}",
                    slug=franchise_slug,
                    description="Shared by one public title and one quarantined fixture.",
                )
                genre = Genre(name=f"Boundary Genre {token}", slug=genre_slug)
                person = Person(name=f"Boundary Artist {token}", slug=person_slug)
                db.add_all((franchise, genre, person))
                db.flush()
                public_movie = Movie(
                    title=f"Boundary Release {token}",
                    slug=public_slug,
                    short_description="A legitimate public catalog title.",
                    synopsis="The control title for the public-boundary test.",
                    runtime_minutes=96,
                    status=CatalogStatus.published,
                    franchise_id=franchise.id,
                )
                hidden_movie = Movie(
                    title=f"Club Film {token}",
                    slug=hidden_slug,
                    short_description="A historical integration fixture.",
                    synopsis="This title must remain behind every customer boundary.",
                    runtime_minutes=91,
                    status=CatalogStatus.published,
                    franchise_id=franchise.id,
                )
                series = Series(
                    title=f"Boundary Series {token}",
                    slug=series_slug,
                    short_description="A public series with mixed episode publication states.",
                    synopsis="Only published episode credits may be exposed.",
                    status=CatalogStatus.published,
                )
                season = Season(number=1, title="Boundary Season")
                published_episode = Episode(
                    number=1,
                    title=f"Published Episode {token}",
                    synopsis="A published episode credit.",
                    runtime_minutes=44,
                    status=CatalogStatus.published,
                )
                draft_episode = Episode(
                    number=2,
                    title=f"Draft Episode {token}",
                    synopsis="A draft episode credit that must not be exposed.",
                    runtime_minutes=45,
                    status=CatalogStatus.draft,
                )
                season.episodes.extend((published_episode, draft_episode))
                series.seasons.append(season)
                public_movie.genres = [genre]
                hidden_movie.genres = [genre]
                db.add_all((public_movie, hidden_movie, series))
                db.flush()

                db.add_all(
                    (
                        Credit(
                            movie_id=public_movie.id,
                            person_id=person.id,
                            role="Director",
                            billing_order=0,
                        ),
                        Credit(
                            movie_id=hidden_movie.id,
                            person_id=person.id,
                            role="Director",
                            billing_order=0,
                        ),
                        Credit(
                            episode_id=published_episode.id,
                            person_id=person.id,
                            role="Guest",
                            billing_order=1,
                        ),
                        Credit(
                            episode_id=draft_episode.id,
                            person_id=person.id,
                            role="Guest",
                            billing_order=2,
                        ),
                    )
                )
                public_source = PlaybackSource(
                    movie_id=public_movie.id,
                    external_manifest_url="https://cdn.example.test/public/master.m3u8",
                    external_format="hls",
                    duration_seconds=5_760,
                    rights_basis="Regression-test fixture",
                    rights_reference=f"public-boundary:{token}:public",
                    is_active=True,
                )
                hidden_source = PlaybackSource(
                    movie_id=hidden_movie.id,
                    external_manifest_url="https://cdn.example.test/hidden/master.m3u8",
                    external_format="hls",
                    duration_seconds=5_460,
                    rights_basis="Regression-test fixture",
                    rights_reference=f"public-boundary:{token}:hidden",
                    is_active=True,
                )
                hidden_list = Collection(
                    slug=list_slug,
                    title=f"Boundary List {token}",
                    description="A public list whose only item is quarantined.",
                    kind=CollectionKind.user_list,
                    status=CurationStatus.published,
                    owner_profile_id=profile_id,
                    visibility="public",
                    moderation_status="approved",
                )
                hidden_list.items.append(CollectionItem(position=0, movie_id=hidden_movie.id))
                hidden_journey = Journey(
                    slug=journey_slug,
                    title=f"Boundary Journey {token}",
                    description="A journey whose only title is quarantined.",
                    status=CurationStatus.published,
                )
                hidden_chapter = JourneyChapter(position=0, title="Hidden chapter")
                hidden_chapter.items.append(JourneyItem(position=0, movie_id=hidden_movie.id))
                hidden_journey.chapters.append(hidden_chapter)
                db.add_all((public_source, hidden_source, hidden_list, hidden_journey))
                db.flush()
                completed_at = datetime.now(UTC)
                db.add_all(
                    (
                        ViewingActivity(
                            profile_id=profile_id,
                            playback_source_id=public_source.id,
                            activity_number=1,
                            watched_seconds=5_500,
                            completed=True,
                            completed_at=completed_at,
                        ),
                        ViewingActivity(
                            profile_id=profile_id,
                            playback_source_id=hidden_source.id,
                            activity_number=1,
                            watched_seconds=5_300,
                            completed=True,
                            completed_at=completed_at,
                        ),
                        WatchProgress(
                            profile_id=profile_id,
                            playback_source_id=hidden_source.id,
                            position_seconds=5_300,
                            duration_seconds=5_460,
                            percentage=97.07,
                            completed=True,
                        ),
                    )
                )
                db.commit()

                public_movie_id = public_movie.id
                hidden_movie_id = hidden_movie.id
                hidden_source_id = hidden_source.id
                hidden_list_id = hidden_list.id
                hidden_journey_item_id = hidden_chapter.items[0].id
                published_episode_id = published_episode.id
                draft_episode_id = draft_episode.id

                profile = db.get(Profile, profile_id)
                with pytest.raises(HTTPException) as error:
                    playable_source(db, hidden_source_id)
                assert error.value.status_code == 404

                recommendation_ids = {
                    (item.movie or item.series).id for item in recommend(db, profile).items
                }
                assert public_movie_id in recommendation_ids
                assert hidden_movie_id not in recommendation_ids

                prescription = prescribe(
                    db,
                    profile,
                    PrescriptionRequest(
                        preferred_genre_slugs=[genre_slug],
                        watch_state="either",
                    ),
                )
                assert prescription.movie.id == public_movie_id

                graph = film_graph(db, public_movie)
                assert any(node.label == person.name for node in graph.nodes)
                assert all(node.label != hidden_movie.title for node in graph.nodes)

                destination = credit_destination(db, kind="person", slug=person_slug)
                assert destination is not None
                destination_ids = {title.id for title in destination.titles}
                assert destination_ids == {public_movie_id, published_episode_id}
                assert draft_episode_id not in destination_ids

                room = after_credits_room(db, public_source, profile_id)
                assert room.unlocked is True
                assert room.recommended_next == []

                taste = taste_dna(db, profile)
                assert taste.watched_titles == 0
                passport = passport_report(db, profile)
                assert [item.title for item in passport.history] == [public_movie.title]

            recommendations = client.get("/recommendations")
            assert recommendations.status_code == 200, recommendations.text
            recommendation_ids = {
                item["movie"]["id"]
                for item in recommendations.json()["items"]
                if item["movie"]
            }
            assert str(public_movie_id) in recommendation_ids
            assert str(hidden_movie_id) not in recommendation_ids

            prescription = client.post(
                "/recommendations/movie-prescription",
                json={"preferred_genre_slugs": [genre_slug], "watch_state": "either"},
            )
            assert prescription.status_code == 200, prescription.text
            assert prescription.json()["movie"]["id"] == str(public_movie_id)

            public_playback = client.get(f"/playback/movies/{public_slug}")
            assert public_playback.status_code == 200, public_playback.text
            assert public_playback.json()["movie_id"] == str(public_movie_id)
            assert client.get(f"/playback/movies/{hidden_slug}").status_code == 404
            public_room = client.get(
                f"/cinephile/sources/{public_playback.json()['source_id']}/after-credits"
            )
            assert public_room.status_code == 200, public_room.text
            assert public_room.json()["recommended_next"] == []
            assert (
                client.get(f"/cinephile/sources/{hidden_source_id}/after-credits").status_code
                == 404
            )
            assert client.get(f"/community/movies/{hidden_movie_id}").status_code == 404

            graph = client.get(f"/catalog/movies/{public_slug}/knowledge-graph")
            assert graph.status_code == 200, graph.text
            assert all(node["label"] != f"Club Film {token}" for node in graph.json()["nodes"])
            credits = client.get(f"/catalog/people/{person_slug}/credits")
            assert credits.status_code == 200, credits.text
            credit_ids = {title["id"] for title in credits.json()["titles"]}
            assert credit_ids == {str(public_movie_id), str(published_episode_id)}
            assert str(draft_episode_id) not in credit_ids

            assert all(
                item["id"] != str(hidden_list_id) for item in client.get("/community/lists").json()
            )
            assert client.get(f"/community/lists/{list_slug}").status_code == 404
            assert client.get(f"/curation/journeys/{journey_slug}/progress").status_code == 404
            assert (
                client.put(
                    f"/curation/journeys/{journey_slug}/progress",
                    json={
                        "journey_item_id": str(hidden_journey_item_id),
                        "completed": True,
                    },
                ).status_code
                == 404
            )

            club = client.post(
                "/clubs",
                json={"name": f"Boundary Club {token}", "description": "Route matrix."},
            )
            assert club.status_code == 201, club.text
            club_id = club.json()["id"]
            linked = client.post(
                f"/clubs/{club_id}/lists",
                json={"collection_id": str(hidden_list_id)},
            )
            assert linked.status_code == 200, linked.text
            assert linked.json()["lists"] == []
            with SessionLocal() as db:
                historical_watch = ClubScheduledWatch(
                    club_id=uuid.UUID(club_id),
                    movie_id=hidden_movie_id,
                    playback_source_id=hidden_source_id,
                    created_by_profile_id=profile_id,
                    title="Historical fixture watch",
                    scheduled_at=datetime.now(UTC) + timedelta(hours=2),
                )
                db.add(historical_watch)
                db.flush()
                db.add(
                    ClubWatchHistory(
                        scheduled_watch_id=historical_watch.id,
                        profile_id=profile_id,
                    )
                )
                db.commit()
            historical_club = client.get(f"/clubs/{club_id}")
            assert historical_club.status_code == 200, historical_club.text
            assert historical_club.json()["scheduled_watches"] == []
            assert historical_club.json()["watch_history"] == []
            scheduled = client.post(
                f"/clubs/{club_id}/schedule",
                json={
                    "movie_id": str(hidden_movie_id),
                    "playback_source_id": str(hidden_source_id),
                    "title": "Must remain hidden",
                    "scheduled_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                },
            )
            assert scheduled.status_code == 404
    finally:
        with SessionLocal() as db:
            db.execute(delete(User).where(User.email == email))
            db.execute(delete(Journey).where(Journey.slug == journey_slug))
            db.execute(delete(Movie).where(Movie.slug.in_([public_slug, hidden_slug])))
            db.execute(delete(Series).where(Series.slug == series_slug))
            db.execute(delete(Person).where(Person.slug == person_slug))
            db.execute(delete(Genre).where(Genre.slug == genre_slug))
            db.execute(delete(Franchise).where(Franchise.slug == franchise_slug))
            db.commit()
