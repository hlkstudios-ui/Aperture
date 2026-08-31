import uuid
from datetime import UTC, date, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Genre, Movie, Season, Series
from app.config import get_settings
from app.db import SessionLocal
from app.geo import sign_geo_assertion
from app.main import app
from app.models import Admin, AuditLog, HomepageConfiguration, HomepageRail, User


def test_homepage_mode_changes_immediately_and_persists_per_profile() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"homepage-viewer-{token}@example.com"
    password = "HomepageViewer123"
    with TestClient(app) as client:
        registration = client.post(
            "/auth/register",
            json={"email": email, "password": password, "profile_name": "Curated viewer"},
        )
        assert registration.status_code == 201
        primary_id = registration.json()["active_profile_id"]
        assert client.get("/homepage/profile").json()["mode"] == "curated"

        changed = client.patch("/homepage/mode", json={"mode": "no_algorithm"})
        assert changed.status_code == 200, changed.text
        no_algorithm = changed.json()
        assert no_algorithm["mode"] == "no_algorithm"
        assert no_algorithm["strategy"] == "deterministic_catalog_indexes_v1"
        assert [rail["title"] for rail in no_algorithm["rails"][:3]] == [
            "Recently added",
            "A–Z",
            "Release year",
        ]
        assert client.get("/homepage/profile").json() == no_algorithm

        second = client.post("/profiles", json={"name": "Editorial viewer"})
        assert second.status_code == 201
        assert client.post(f"/profiles/{second.json()['id']}/switch").status_code == 200
        assert client.get("/homepage/profile").json()["mode"] == "curated"
        assert client.post(f"/profiles/{primary_id}/switch").status_code == 200
        assert client.get("/homepage/profile").json()["mode"] == "no_algorithm"
        assert client.patch("/homepage/mode", json={"mode": "random"}).status_code == 422

    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.commit()


def test_homepage_draft_publish_scheduling_and_rights_windows() -> None:
    token = uuid.uuid4().hex[:10]
    email = f"homepage-{token}@example.com"
    password = "HomepageAdministrator123"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        genre = Genre(name=f"Science Fiction {token}", slug=f"science-fiction-{token}")
        scheduled = Movie(
            title=f"Scheduled Feature {token}",
            slug=f"scheduled-feature-{token}",
            short_description="A title published by a UTC schedule.",
            synopsis="Homepage scheduling integration fixture.",
            release_date=date(2024, 10, 4),
            runtime_minutes=90,
            maturity_rating="PG-13",
            status=CatalogStatus.ready,
            publish_at=now - timedelta(minutes=1),
            rights_start_at=now - timedelta(days=1),
            rights_end_at=now + timedelta(days=1),
            allowed_territories=["CA"],
            genres=[genre],
        )
        unavailable = Series(
            title=f"Future Rights {token}",
            slug=f"future-rights-{token}",
            short_description="Published metadata outside its rights window.",
            synopsis="Rights filtering integration fixture.",
            status=CatalogStatus.published,
            rights_start_at=now + timedelta(days=1),
        )
        available_series = Series(
            title=f"Available Series {token}",
            slug=f"available-series-{token}",
            short_description="A series with card metadata.",
            synopsis="Homepage series metadata integration fixture.",
            release_date=date(2023, 6, 12),
            maturity_rating="TV-14",
            status=CatalogStatus.published,
            rights_start_at=now - timedelta(days=1),
            rights_end_at=now + timedelta(days=1),
            allowed_territories=["CA"],
            genres=[genre],
            seasons=[Season(number=1, title="Season One"), Season(number=2, title="Season Two")],
        )
        db.add_all([admin, scheduled, unavailable, available_series])
        db.commit()
        admin_id = admin.id
        movie_id = scheduled.id
        unavailable_series_id = unavailable.id
        available_series_id = available_series.id
        genre_id = genre.id

    with TestClient(app) as client:
        issued_at = int(datetime.now(UTC).timestamp())
        geo_headers = {
            "X-Aperture-Country": "CA",
            "X-Aperture-Geo-Timestamp": str(issued_at),
            "X-Aperture-Geo-Signature": sign_geo_assertion(
                "CA", issued_at, get_settings().geo_assertion_secret
            ),
        }
        assert (
            client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        draft_before = client.get("/admin/homepage").json()
        existing_count = len(draft_before["rails"])
        old_hero_movie = draft_before["hero_movie_id"]
        old_hero_series = draft_before["hero_series_id"]
        with SessionLocal() as db:
            config = db.get(HomepageConfiguration, uuid.UUID(draft_before["id"]))
            old_snapshot = config.published_snapshot
            old_published_at = config.published_at
            position = db.scalar(select(func.max(HomepageRail.position)))
            position = (position if position is not None else -1) + 1

        assert client.get(f"/catalog/movies/scheduled-feature-{token}").status_code == 404
        assert (
            client.get(
                f"/catalog/movies/scheduled-feature-{token}", headers=geo_headers
            ).status_code
            == 200
        )
        assert client.get(f"/catalog/series/future-rights-{token}").status_code == 404
        assert (
            client.patch(
                f"/admin/catalog/movies/{movie_id}",
                json={"publish_at": "2026-08-16T12:00:00"},
            ).status_code
            == 422
        )
        assert (
            client.put("/admin/homepage/hero", json={"movie_id": str(movie_id)}).status_code == 200
        )
        rail = client.post(
            "/admin/homepage/rails",
            json={
                "title": f"Festival Selection {token}",
                "eyebrow": "Programmed in Studio",
                "source": "pinned",
                "position": position,
                "enabled": True,
            },
        )
        assert rail.status_code == 201, rail.text
        rail_id = rail.json()["id"]
        item = client.post(
            f"/admin/homepage/rails/{rail_id}/items",
            json={"movie_id": str(movie_id), "position": 0},
        )
        assert item.status_code == 201, item.text
        series_item = client.post(
            f"/admin/homepage/rails/{rail_id}/items",
            json={"series_id": str(available_series_id), "position": 1},
        )
        assert series_item.status_code == 201, series_item.text
        preview = client.get("/admin/homepage/preview")
        assert preview.status_code == 200
        preview_payload = preview.json()
        preview_hero = preview_payload["hero"]
        assert preview_hero["title"] == f"Scheduled Feature {token}"
        assert preview_hero["release_date"] == "2024-10-04"
        assert preview_hero["runtime_minutes"] == 90
        assert preview_hero["maturity_rating"] == "PG-13"
        assert preview_hero["season_count"] is None
        assert preview_hero["genres"] == [
            {
                "id": str(genre_id),
                "name": f"Science Fiction {token}",
                "slug": f"science-fiction-{token}",
            }
        ]
        preview_series = next(
            title
            for title in preview_payload["rails"][-1]["items"]
            if title["id"] == str(available_series_id)
        )
        assert preview_series["release_date"] == "2023-06-12"
        assert preview_series["runtime_minutes"] is None
        assert preview_series["maturity_rating"] == "TV-14"
        assert preview_series["season_count"] == 2
        assert preview_series["genres"] == preview_hero["genres"]
        live_before = client.get("/homepage").json()
        assert all(rail["id"] != rail_id for rail in live_before["rails"])
        published = client.post("/admin/homepage/publish")
        assert published.status_code == 200, published.text
        assert any(rail["id"] == rail_id for rail in published.json()["rails"])
        assert client.get("/homepage").json()["hero"] is None
        live = client.get("/homepage", headers=geo_headers).json()
        assert live["hero"]["id"] == str(movie_id)
        live_series = next(
            title
            for rail in live["rails"]
            for title in rail["items"]
            if title["id"] == str(available_series_id)
        )
        assert live_series["season_count"] == 2
        assert live_series["genres"] == preview_hero["genres"]

    with SessionLocal() as db:
        config = db.scalar(select(HomepageConfiguration))
        config.draft_hero_movie_id = uuid.UUID(old_hero_movie) if old_hero_movie else None
        config.draft_hero_series_id = uuid.UUID(old_hero_series) if old_hero_series else None
        config.published_snapshot = old_snapshot
        config.published_at = old_published_at
        db.execute(delete(HomepageRail).where(HomepageRail.id == uuid.UUID(rail_id)))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(
            delete(Series).where(Series.id.in_([unavailable_series_id, available_series_id]))
        )
        db.execute(delete(Genre).where(Genre.id == genre_id))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
        assert existing_count == db.scalar(select(func.count(HomepageRail.id)))
