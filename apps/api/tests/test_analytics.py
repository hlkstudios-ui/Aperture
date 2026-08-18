import uuid
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AnalyticsEvent, AuditLog, User


def event(kind: str, movie_id: uuid.UUID | None = None, **values):
    return {
        "client_event_id": str(uuid.uuid4()),
        "event_type": kind,
        "movie_id": str(movie_id) if movie_id else None,
        "occurred_at": datetime.now(UTC).isoformat(),
        **values,
    }


def test_bounded_idempotent_analytics_and_admin_aggregates() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"analytics-{token}@example.com"
    admin_email = f"analytics-admin-{token}@example.com"
    password = "AnalyticsPassword123"
    with SessionLocal() as db:
        admin = Admin(email=admin_email, password_hash=hash_password(password))
        movie = Movie(
            title=f"Analytics Fixture {token}",
            slug=f"analytics-fixture-{token}",
            short_description="An event aggregation fixture.",
            synopsis="Original analytics integration test metadata.",
            runtime_minutes=90,
            status=CatalogStatus.published,
        )
        db.add_all([admin, movie])
        db.commit()
        admin_id, movie_id = admin.id, movie.id

    with TestClient(app) as anonymous:
        assert anonymous.post("/analytics/events", json={"events": []}).status_code == 401

    with TestClient(app, headers={"user-agent": "Aperture Analytics Browser"}) as viewer:
        registration = viewer.post(
                "/auth/register",
                json={"email": email, "password": password, "profile_name": "Metrics Viewer"},
        )
        assert registration.status_code == 201
        profile_id = registration.json()["active_profile_id"]
        play = event("play_start", movie_id, position_seconds=0, duration_seconds=120, value=0)
        bypass = viewer.patch(
            f"/profiles/{profile_id}",
            json={"preference": {"analytics_enabled": True}},
        )
        assert bypass.status_code == 200
        assert bypass.json()["preference"]["analytics_enabled"] is False
        assert viewer.post("/analytics/events", json={"events": [play]}).status_code == 403
        consent = viewer.put(
            f"/profiles/{profile_id}/privacy",
            json={"analytics_enabled": True, "homepage_mode": "curated"},
        )
        assert consent.status_code == 200
        assert consent.json()["preference"]["analytics_enabled"] is True
        assert consent.json()["preference"]["consent_updated_at"] is not None
        payload = {
            "events": [
                play,
                event("progress", movie_id, position_seconds=10, duration_seconds=120, value=10),
                event("progress", movie_id, position_seconds=20, duration_seconds=120, value=10),
                event("completion", movie_id, position_seconds=119, duration_seconds=120, value=0),
                event(
                    "playback_startup",
                    movie_id,
                    position_seconds=0,
                    duration_seconds=120,
                    value=480,
                    properties={"source": "customer_player"},
                ),
                event(
                    "playback_buffer",
                    movie_id,
                    position_seconds=30,
                    duration_seconds=120,
                    value=0.25,
                    properties={"buffered_seconds": 0.25},
                ),
                event(
                    "quality_change",
                    movie_id,
                    position_seconds=45,
                    duration_seconds=120,
                    properties={"quality_height": 720, "action": "manual"},
                ),
                event(
                    "playback_error",
                    movie_id,
                    position_seconds=50,
                    duration_seconds=120,
                    properties={"error_code": "network:timeout", "source": "hls.js"},
                ),
                event("search", query="analytics fixture", result_count=1),
            ]
        }
        ingested = viewer.post("/analytics/events", json=payload)
        assert ingested.status_code == 202, ingested.text
        assert ingested.json() == {"accepted": 8, "duplicate_or_coalesced": 1}
        duplicate = viewer.post("/analytics/events", json={"events": [play]})
        assert duplicate.json() == {"accepted": 0, "duplicate_or_coalesced": 1}
        invalid = event(
            "play_start",
            movie_id,
            position_seconds=0,
            duration_seconds=120,
            properties={"email": email},
        )
        assert viewer.post("/analytics/events", json={"events": [invalid]}).status_code == 422

    with TestClient(app) as admin_client:
        assert (
            admin_client.post(
                "/admin/auth/login", json={"email": admin_email, "password": password}
            ).status_code
            == 200
        )
        summary = admin_client.get("/admin/analytics/summary")
        assert summary.status_code == 200, summary.text
        body = summary.json()
        # Platform totals include deliberately durable anonymous aggregates from prior titles.
        assert body["totals"]["play_start"] >= 1
        assert body["totals"]["progress"] >= 1
        assert body["totals"]["completion"] >= 1
        assert body["totals"]["playback_startup"] >= 1
        assert body["totals"]["playback_buffer"] >= 1
        assert body["totals"]["playback_error"] >= 1
        assert body["totals"]["quality_change"] >= 1
        assert body["playback_quality"]["startup_samples"] >= 1
        assert body["playback_quality"]["average_startup_ms"] > 0
        assert body["playback_quality"]["buffer_seconds"] >= 0.25
        assert body["playback_quality"]["fatal_errors"] >= 1
        assert body["playback_quality"]["error_rate_percent"] > 0
        # Anonymous aggregate dimensions intentionally outlive deleted test users/titles.
        assert body["totals"]["search"] >= 1
        assert body["unique_viewers"] >= 1
        assert body["completion_rate"] > 0
        title = next(item for item in body["titles"] if item["movie_id"] == str(movie_id))
        assert title["title_label"] == f"Analytics Fixture {token}"
        assert title["plays"] == 1 and title["completions"] == 1
        assert any(item["event_type"] == "play_start" for item in body["recent"])

    with TestClient(app) as viewer:
        assert (
            viewer.post("/auth/login", json={"email": email, "password": password}).status_code
            == 200
        )
        withdrawn = viewer.put(
            f"/profiles/{profile_id}/privacy",
            json={"analytics_enabled": False, "homepage_mode": "no_algorithm"},
        )
        assert withdrawn.status_code == 200
        assert withdrawn.json()["preference"]["analytics_enabled"] is False
        assert withdrawn.json()["preference"]["homepage_mode"] == "no_algorithm"
        denied = viewer.post(
            "/analytics/events",
            json={"events": [event("search", query="x", result_count=0)]},
        )
        assert denied.status_code == 403

    with SessionLocal() as db:
        raw_count = db.scalar(
            select(func.count(AnalyticsEvent.id)).where(AnalyticsEvent.profile_id == profile_id)
        )
        assert raw_count == 0
        db.execute(delete(User).where(User.email == email))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
