import hashlib
import uuid
from datetime import UTC, date, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Genre, Movie
from app.config import get_settings
from app.db import SessionLocal
from app.geo import sign_geo_assertion
from app.main import app
from app.models import (
    Admin,
    AggregatedMetric,
    AnalyticsEventType,
    AssetState,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    ProcessingState,
    Profile,
    User,
    WatchProgress,
)


def movie(token: str, suffix: str, genre: Genre) -> Movie:
    record = Movie(
        title=f"Recommendation {suffix} {token}",
        slug=f"rules-pick-{suffix.lower()}-{token}",
        short_description="An explainable recommendation fixture.",
        synopsis="Original rules-based recommendation test metadata.",
        release_date=date(2026, 1, 1),
        runtime_minutes=90,
        status=CatalogStatus.published,
    )
    record.genres = [genre]
    return record


def test_explainable_rules_preferences_popularity_and_watched_exclusion() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"recommendations-{token}@example.com"
    password = "RecommendationPassword123"
    with SessionLocal() as db:
        admin = Admin(
            email=f"recommendation-admin-{token}@example.com",
            password_hash=hash_password(password),
        )
        drama = Genre(name=f"Drama {token}", slug=f"drama-{token}")
        comedy = Genre(name=f"Comedy {token}", slug=f"comedy-{token}")
        watched = movie(token, "Watched", drama)
        similar = movie(token, "Similar", drama)
        popular = movie(token, "Popular", comedy)
        popular.allowed_territories = ["CA"]
        db.add_all([admin, drama, comedy, watched, similar, popular])
        db.flush()
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="recommendation.mp4",
            media_type="video/mp4",
            size_bytes=1,
            checksum_sha256=hashlib.sha256(b"x").hexdigest(),
            storage_key=f"recommendations/{token}.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        job = ProcessingJob(
            asset=asset,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=60,
            manifest_key=f"recommendations/{token}/master.m3u8",
        )
        source = PlaybackSource(processing_job=job, movie_id=watched.id)
        asset_two = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="recommendation-two.mp4",
            media_type="video/mp4",
            size_bytes=1,
            checksum_sha256=hashlib.sha256(b"y").hexdigest(),
            storage_key=f"recommendations/{token}-two.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        job_two = ProcessingJob(
            asset=asset_two,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=60,
            manifest_key=f"recommendations/{token}/second-master.m3u8",
        )
        source_two = PlaybackSource(processing_job=job_two, movie_id=popular.id)
        db.add_all([asset, job, source, asset_two, job_two, source_two])
        db.commit()
        ids = {
            "admin": admin.id,
            "asset": asset.id,
            "asset_two": asset_two.id,
            "watched": watched.id,
            "similar": similar.id,
            "popular": popular.id,
            "drama": drama.id,
            "comedy": comedy.id,
            "source": source.id,
            "source_two": source_two.id,
        }

    with TestClient(app) as anonymous:
        assert anonymous.get("/recommendations").status_code == 401

    with TestClient(app) as viewer:
        registered = viewer.post(
            "/auth/register",
            json={"email": email, "password": password, "profile_name": "Taste Tester"},
        )
        assert registered.status_code == 201
        cold = viewer.get("/recommendations")
        assert cold.status_code == 200, cold.text
        assert cold.json()["strategy"] == "rules_v1"
        assert cold.json()["cold_start"] is True
        assert all("cold_start" in item["reasons"] for item in cold.json()["items"])
        assert all(
            not item["movie"] or item["movie"]["id"] != str(ids["popular"])
            for item in cold.json()["items"]
        )
        issued_at = int(datetime.now(UTC).timestamp())
        viewer.headers.update(
            {
                "X-Aperture-Country": "CA",
                "X-Aperture-Geo-Timestamp": str(issued_at),
                "X-Aperture-Geo-Signature": sign_geo_assertion(
                    "CA", issued_at, get_settings().geo_assertion_secret
                ),
            }
        )

        preferred = viewer.put(
            "/recommendations/preferences",
            json={"preferred_genre_slugs": [f"drama-{token}", f"drama-{token}"]},
        )
        assert preferred.status_code == 200, preferred.text
        assert preferred.json()["preferred_genre_slugs"] == [f"drama-{token}"]
        ranked = viewer.get("/recommendations").json()
        similar_item = next(
            item for item in ranked["items"] if item["movie"]["id"] == str(ids["similar"])
        )
        assert "profile_genre_preference" in similar_item["reasons"]

        with SessionLocal() as db:
            profile_id = db.scalar(select(Profile.id).join(User).where(User.email == email))
            db.add(
                WatchProgress(
                    profile_id=profile_id,
                    playback_source_id=ids["source"],
                    position_seconds=55,
                    duration_seconds=60,
                    percentage=91.67,
                    completed=True,
                )
            )
            db.add(
                AggregatedMetric(
                    day=datetime.now(UTC).date(),
                    event_type=AnalyticsEventType.play_start,
                    movie_id=ids["popular"],
                    event_count=50,
                    unique_profiles=20,
                    total_value=0,
                )
            )
            db.commit()

        personalized = viewer.get("/recommendations").json()
        returned_ids = {item["movie"]["id"] for item in personalized["items"] if item["movie"]}
        assert str(ids["watched"]) not in returned_ids
        assert personalized["watched_titles_excluded"] == 1
        similar_item = next(
            item
            for item in personalized["items"]
            if item["movie"] and item["movie"]["id"] == str(ids["similar"])
        )
        popular_item = next(
            item
            for item in personalized["items"]
            if item["movie"] and item["movie"]["id"] == str(ids["popular"])
        )
        assert "similar_genres" in similar_item["reasons"]
        assert "popular_now" in popular_item["reasons"]

        privacy = viewer.put(
            f"/profiles/{profile_id}/privacy",
            json={"analytics_enabled": False, "homepage_mode": "no_algorithm"},
        )
        assert privacy.status_code == 200, privacy.text
        nonpersonalized = viewer.get("/recommendations").json()
        assert nonpersonalized["strategy"] == "editorial_popularity_v1"
        assert nonpersonalized["personalized"] is False
        assert nonpersonalized["watched_titles_excluded"] == 0
        personalized_reasons = {
            "similar_genres", "similar_themes", "similar_tags", "profile_genre_preference"
        }
        assert all(
            not personalized_reasons.intersection(item["reasons"])
            for item in nonpersonalized["items"]
        )

        dna_one = viewer.get("/recommendations/taste-dna")
        assert dna_one.status_code == 200, dna_one.text
        assert dna_one.json()["derived_from"] == "persisted_watch_progress"
        assert dna_one.json()["genres"][0]["key"] == f"drama-{token}"
        prescription_one = viewer.post(
            "/recommendations/movie-prescription", json={"watch_state": "either"}
        )
        assert prescription_one.status_code == 200, prescription_one.text
        assert prescription_one.json()["movie"]["id"] == str(ids["similar"])
        assert any(
            item["dimension"] == "taste_dna" and item["status"] == "matched"
            for item in prescription_one.json()["match_dimensions"]
        )

        second = viewer.post(
            "/profiles",
            json={"name": "Second Taste", "preference": {}},
        )
        assert second.status_code == 201, second.text
        second_id = second.json()["id"]
        with SessionLocal() as db:
            db.add(
                WatchProgress(
                    profile_id=uuid.UUID(second_id),
                    playback_source_id=ids["source_two"],
                    position_seconds=58,
                    duration_seconds=60,
                    percentage=96.67,
                    completed=True,
                )
            )
            db.commit()
        switched = viewer.post(f"/profiles/{second_id}/switch")
        assert switched.status_code == 200, switched.text
        dna_two = viewer.get("/recommendations/taste-dna").json()
        assert dna_two["genres"][0]["key"] == f"comedy-{token}"
        prescription_two = viewer.post(
            "/recommendations/movie-prescription", json={"watch_state": "either"}
        )
        assert prescription_two.status_code == 200, prescription_two.text
        assert prescription_two.json()["movie"]["id"] == str(ids["popular"])
        assert prescription_two.json()["movie"]["id"] != prescription_one.json()["movie"]["id"]

    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.execute(delete(MediaAsset).where(MediaAsset.id == ids["asset"]))
        db.execute(delete(MediaAsset).where(MediaAsset.id == ids["asset_two"]))
        db.execute(
            delete(Movie).where(Movie.id.in_([ids["watched"], ids["similar"], ids["popular"]]))
        )
        db.execute(delete(Genre).where(Genre.id.in_([ids["drama"], ids["comedy"]])))
        db.execute(delete(Admin).where(Admin.id == ids["admin"]))
        db.commit()
