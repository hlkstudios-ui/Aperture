import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog, User


def test_collections_lists_and_journey_progress_respect_rights_and_profiles() -> None:
    suffix = uuid.uuid4().hex[:10]
    password = "AdministratorPass123"
    admin_email = f"curation-{suffix}@example.com"
    viewer_email = f"viewer-{suffix}@example.com"
    other_email = f"other-{suffix}@example.com"
    with SessionLocal() as db:
        admin = Admin(email=admin_email, password_hash=hash_password(password))
        visible = Movie(
            title=f"Visible {suffix}",
            slug=f"licensed-title-{suffix}",
            short_description="Visible",
            synopsis="Visible in its licensed window.",
            runtime_minutes=90,
            status=CatalogStatus.published,
        )
        expired = Movie(
            title=f"Expired {suffix}",
            slug=f"unlicensed-title-{suffix}",
            short_description="Expired",
            synopsis="No longer licensed.",
            runtime_minutes=91,
            status=CatalogStatus.published,
            rights_end_at=datetime.now(UTC) - timedelta(days=1),
        )
        db.add_all((admin, visible, expired))
        db.commit()
        admin_id, visible_id, expired_id = admin.id, visible.id, expired.id

    with TestClient(app) as admin_client:
        assert (
            admin_client.post(
                "/admin/auth/login", json={"email": admin_email, "password": password}
            ).status_code
            == 200
        )
        items = [{"movie_id": str(expired_id)}, {"movie_id": str(visible_id), "note": "Start here"}]
        collection = admin_client.post(
            "/admin/curation/collections",
            json={
                "slug": f"movement-{suffix}",
                "title": "A film movement",
                "description": "An ordered collection",
                "kind": "movement",
                "status": "published",
                "items": items,
            },
        )
        assert collection.status_code == 201, collection.text
        journey = admin_client.post(
            "/admin/curation/journeys",
            json={
                "slug": f"journey-{suffix}",
                "title": "A film journey",
                "description": "Learn in sequence",
                "status": "published",
                "chapters": [{"title": "Origins", "introduction": "An essay", "items": items}],
            },
        )
        assert journey.status_code == 201, journey.text

    with TestClient(app) as public:
        curated = public.get(f"/curation/collections/movement-{suffix}")
        assert curated.status_code == 200
        assert [item["slug"] for item in curated.json()["items"]] == [
            f"licensed-title-{suffix}"
        ]
        public_journey = public.get(f"/curation/journeys/journey-{suffix}").json()
        assert public_journey["total_items"] == 1
        visible_item_id = public_journey["chapters"][0]["items"][0]["item_id"]

    with TestClient(app) as viewer:
        registration = viewer.post(
            "/auth/register",
            json={
                "email": viewer_email,
                "password": "StrongPassword123",
                "profile_name": "Primary",
            },
        )
        assert registration.status_code == 201
        own_list = viewer.post(
            "/curation/my-lists",
            json={
                "title": "My canon",
                "items": [{"movie_id": str(visible_id)}, {"movie_id": str(expired_id)}],
            },
        )
        assert own_list.status_code == 201, own_list.text
        assert len(own_list.json()["items"]) == 1
        list_id = own_list.json()["id"]
        progress = viewer.put(
            f"/curation/journeys/journey-{suffix}/progress",
            json={"journey_item_id": visible_item_id, "completed": True},
        )
        assert progress.status_code == 200, progress.text
        assert progress.json()["completed"] is True

    with TestClient(app) as other:
        other.post(
            "/auth/register",
            json={"email": other_email, "password": "StrongPassword123", "profile_name": "Other"},
        )
        assert (
            other.put(
                f"/curation/my-lists/{list_id}", json={"title": "Stolen", "items": []}
            ).status_code
            == 404
        )
        assert (
            other.get(f"/curation/journeys/journey-{suffix}/progress").json()["completed"] is False
        )

    with SessionLocal() as db:
        db.execute(delete(User).where(User.email.in_((viewer_email, other_email))))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.execute(delete(Movie).where(Movie.id.in_((visible_id, expired_id))))
        db.commit()
