import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError

from app.auth import hash_password
from app.catalog_models import (
    Character,
    Company,
    Edition,
    Franchise,
    Genre,
    Movie,
    Person,
    Series,
    Tag,
    Theme,
)
from app.catalog_schemas import ArtworkCreate
from app.config import get_settings
from app.db import SessionLocal
from app.geo import sign_geo_assertion
from app.main import app
from app.models import Admin, AuditLog


def test_verified_title_relationships_filter_unverified_and_expired_destinations() -> None:
    suffix = uuid.uuid4().hex[:10]
    email = f"relationships-{suffix}@example.com"
    password = "AdministratorPass123"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        source = Movie(
            title=f"Source {suffix}",
            slug=f"source-{suffix}",
            short_description="Source",
            synopsis="Source film.",
            runtime_minutes=90,
            status="published",
        )
        verified = Movie(
            title=f"Verified {suffix}",
            slug=f"verified-{suffix}",
            short_description="Verified",
            synopsis="Verified related film.",
            runtime_minutes=91,
            status="published",
        )
        expired = Movie(
            title=f"Expired relation {suffix}",
            slug=f"expired-relation-{suffix}",
            short_description="Expired",
            synopsis="Expired related film.",
            runtime_minutes=92,
            status="published",
            rights_end_at=datetime.now(UTC) - timedelta(days=1),
        )
        hidden = Movie(
            title=f"Unverified {suffix}",
            slug=f"unverified-{suffix}",
            short_description="Unverified",
            synopsis="Unverified related film.",
            runtime_minutes=93,
            status="published",
        )
        db.add_all((admin, source, verified, expired, hidden))
        db.commit()
        admin_id = admin.id
        ids = {
            "source": source.id,
            "verified": verified.id,
            "expired": expired.id,
            "hidden": hidden.id,
        }

    with TestClient(app) as client:
        assert (
            client.post(
                "/admin/auth/login", json={"email": email, "password": password}
            ).status_code
            == 200
        )
        for target, kind, manually_verified in (
            ("verified", "influenced_by", True),
            ("expired", "remake", True),
            ("hidden", "companion", False),
        ):
            created = client.post(
                "/admin/catalog/title-relationships",
                json={
                    "source_movie_id": str(ids["source"]),
                    "target_movie_id": str(ids[target]),
                    "kind": kind,
                    "description": f"Verified editorial context for {target}.",
                    "source_note": "Administrator-reviewed fixture source.",
                    "manually_verified": manually_verified,
                },
            )
            assert created.status_code == 201, created.text
        duplicate = client.post(
            "/admin/catalog/title-relationships",
            json={
                "source_movie_id": str(ids["source"]),
                "target_movie_id": str(ids["verified"]),
                "kind": "influenced_by",
                "source_note": "Duplicate.",
                "manually_verified": True,
            },
        )
        assert duplicate.status_code == 409
        graph = client.get(f"/catalog/movies/source-{suffix}/knowledge-graph")
        assert graph.status_code == 200, graph.text
        movie_nodes = [node for node in graph.json()["nodes"] if node["kind"] == "movie"]
        assert {node["label"] for node in movie_nodes} == {f"Source {suffix}", f"Verified {suffix}"}
        assert any(edge["label"] == "influenced by" for edge in graph.json()["edges"])
        assert "Administrator-reviewed fixture source" not in graph.text

    with SessionLocal() as db:
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.execute(delete(Movie).where(Movie.id.in_(ids.values())))
        db.commit()


def test_admin_catalog_crud_and_published_customer_reads() -> None:
    suffix = uuid.uuid4().hex[:10]
    email = f"catalog-{suffix}@example.com"
    password = "AdministratorPass123"
    with SessionLocal() as db:
        admin = Admin(email=email, password_hash=hash_password(password))
        db.add(admin)
        db.commit()
        admin_id = admin.id

    with TestClient(app) as anonymous:
        assert anonymous.get("/admin/catalog/movies").status_code == 401

    with TestClient(app) as client:
        login = client.post("/admin/auth/login", json={"email": email, "password": password})
        assert login.status_code == 200

        language = client.post(
            "/admin/catalog/locales/languages", json={"code": "ja", "name": "Japanese"}
        )
        if language.status_code == 409:
            assert client.get("/admin/catalog/locales/languages").status_code == 200
        else:
            assert language.status_code == 201
        country = client.post(
            "/admin/catalog/locales/countries", json={"code": "JP", "name": "Japan"}
        )
        if country.status_code not in {201, 409}:
            raise AssertionError(country.text)

        named_ids = {}
        for resource, label in (
            ("genres", "Animation"),
            ("themes", "Identity"),
            ("tags", "Hand-drawn"),
            ("franchises", f"Aperture Anthology {suffix}"),
            ("companies", f"Aperture Pictures {suffix}"),
            ("people", f"Mina Sato {suffix}"),
            ("characters", f"Hana {suffix}"),
        ):
            created = client.post(
                f"/admin/catalog/named/{resource}",
                json={"name": label, "slug": f"{resource}-{suffix}"},
            )
            assert created.status_code == 201, created.text
            named_ids[resource] = created.json()["id"]

        movie_payload = {
            "title": f"The Lantern Sea {suffix}",
            "slug": f"catalog-lantern-sea-{suffix}",
            "short_description": "A cartographer follows a light beyond the known coast.",
            "synopsis": "A licensed development title used to verify the catalog lifecycle.",
            "release_date": "2026-08-15",
            "runtime_minutes": 104,
            "maturity_rating": "PG",
            "original_language_code": "ja",
            "country_code": "JP",
            "allowed_territories": ["ca", "US"],
            "franchise_id": named_ids["franchises"],
            "genre_ids": [named_ids["genres"]],
            "theme_ids": [named_ids["themes"]],
            "tag_ids": [named_ids["tags"]],
        }
        movie = client.post("/admin/catalog/movies", json=movie_payload)
        assert movie.status_code == 201, movie.text
        movie_id = movie.json()["id"]
        assert movie.json()["status"] == "draft"
        assert movie.json()["allowed_territories"] == ["CA", "US"]
        assert client.get(f"/catalog/movies/{movie_payload['slug']}").status_code == 404

        edition = client.post(
            "/admin/catalog/editions",
            json={
                "movie_id": movie_id,
                "name": "Theatrical Cut",
                "runtime_minutes": 104,
                "is_default": True,
            },
        )
        assert edition.status_code == 201, edition.text
        credit = client.post(
            "/admin/catalog/credits",
            json={
                "movie_id": movie_id,
                "person_id": named_ids["people"],
                "character_id": named_ids["characters"],
                "company_id": named_ids["companies"],
                "role": "Actor",
                "billing_order": 1,
            },
        )
        assert credit.status_code == 201, credit.text
        artwork = client.post(
            "/admin/catalog/artwork",
            json={
                "movie_id": movie_id,
                "kind": "poster",
                "storage_key": f"demo/{suffix}/poster.webp",
                "alt_text": "Painted lanterns floating over a dark sea",
                "width": 1200,
                "height": 1800,
            },
        )
        assert artwork.status_code == 201, artwork.text
        preview = client.post(
            "/admin/catalog/previews",
            json={
                "movie_id": movie_id,
                "kind": "trailer",
                "title": "Official trailer",
                "external_url": "https://example.com/licensed-demo-trailer",
                "duration_seconds": 90,
            },
        )
        assert preview.status_code == 201, preview.text

        publish = client.patch(f"/admin/catalog/movies/{movie_id}", json={"status": "published"})
        assert publish.status_code == 200, publish.text
        assert client.get(f"/catalog/movies/{movie_payload['slug']}").status_code == 404
        issued_at = int(datetime.now(UTC).timestamp())
        geo_headers = {
            "X-Aperture-Country": "CA",
            "X-Aperture-Geo-Timestamp": str(issued_at),
            "X-Aperture-Geo-Signature": sign_geo_assertion(
                "CA", issued_at, get_settings().geo_assertion_secret
            ),
        }
        public_movie = client.get(f"/catalog/movies/{movie_payload['slug']}", headers=geo_headers)
        assert public_movie.status_code == 200
        assert public_movie.json()["genres"][0]["name"] == "Animation"
        for suffix_path in ("credits", "artwork", "previews"):
            response = client.get(
                f"/catalog/movies/{movie_payload['slug']}/{suffix_path}",
                headers=geo_headers,
            )
            assert len(response.json()) == 1
        assert (
            len(
                client.get(
                    f"/catalog/movies?query=Lantern%20Sea%20{suffix}", headers=geo_headers
                ).json()
            )
            == 1
        )

        series = client.post(
            "/admin/catalog/series",
            json={
                "title": f"Harbor Signals {suffix}",
                "slug": f"harbor-signals-{suffix}",
                "short_description": "Signals cross a quiet harbor.",
                "synopsis": "A development series used to verify ordered episodic metadata.",
                "release_date": "2026-08-15",
                "maturity_rating": "TV-PG",
                "status": "published",
                "genre_ids": [named_ids["genres"]],
            },
        )
        assert series.status_code == 201, series.text
        series_id = series.json()["id"]
        season = client.post(
            "/admin/catalog/seasons",
            json={"series_id": series_id, "number": 1, "title": "First Light"},
        )
        assert season.status_code == 201, season.text
        episode = client.post(
            "/admin/catalog/episodes",
            json={
                "season_id": season.json()["id"],
                "number": 1,
                "title": "The Bell",
                "synopsis": "A bell rings across an empty harbor.",
                "runtime_minutes": 42,
                "status": "published",
            },
        )
        assert episode.status_code == 201, episode.text
        public_series = client.get(f"/catalog/series/harbor-signals-{suffix}")
        assert public_series.status_code == 200, public_series.text
        assert public_series.json()["seasons"][0]["episodes"][0]["title"] == "The Bell"

        assert client.delete(f"/admin/catalog/movies/{movie_id}").status_code == 204
        assert client.get(f"/catalog/movies/{movie_payload['slug']}").status_code == 404

    with SessionLocal() as db:
        db.execute(delete(Series).where(Series.slug == f"harbor-signals-{suffix}"))
        for model in (Genre, Theme, Tag, Franchise, Company, Person, Character):
            db.execute(delete(model).where(model.slug == f"{model.__tablename__}-{suffix}"))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()


def test_catalog_database_parent_constraints() -> None:
    with pytest.raises(ValidationError):
        ArtworkCreate(
            kind="poster",
            storage_key="invalid/poster.webp",
            alt_text="Invalid parentless artwork",
        )

    with SessionLocal() as db:
        movie = Movie(
            title="Constraint probe",
            slug=f"constraint-probe-{uuid.uuid4().hex}",
            short_description="Temporary constraint test.",
            synopsis="Rolled back after the database rejects an invalid edition.",
            runtime_minutes=1,
        )
        db.add(movie)
        db.flush()
        db.add(Edition(name="Parentless edition"))
        with pytest.raises(IntegrityError):
            db.flush()
        db.rollback()
