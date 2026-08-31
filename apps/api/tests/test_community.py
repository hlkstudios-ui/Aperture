import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.community_models import ModerationAction
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import Admin, AuditLog, User


def test_review_writes_are_rate_limited(monkeypatch) -> None:
    token = uuid.uuid4().hex[:10]
    email = f"review-rate-{token}@example.com"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        movie = Movie(
            title=f"Rate Limit Film {token}",
            slug=f"review-rate-film-{token}",
            short_description="Rate-limit fixture.",
            synopsis="Rate-limit fixture.",
            runtime_minutes=80,
            status=CatalogStatus.published,
            rights_start_at=now - timedelta(days=1),
            rights_end_at=now + timedelta(days=1),
        )
        db.add(movie)
        db.commit()
        movie_id = movie.id
    with TestClient(app) as client:
        assert (
            client.post(
                "/auth/register",
                json={
                    "email": email,
                    "password": "RateLimitViewerPassword123",
                    "profile_name": "Rate Limited",
                },
            ).status_code
            == 201
        )
        settings = get_settings()
        monkeypatch.setattr(
            "app.rate_limit.get_settings",
            lambda: SimpleNamespace(app_env="production", redis_url=settings.redis_url),
        )
        results = [
            client.put(
                f"/community/movies/{movie_id}/review",
                json={"body": f"Bounded review edit {index}."},
            )
            for index in range(9)
        ]
        assert [response.status_code for response in results[:8]] == [200] * 8
        assert results[8].status_code == 429
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == email))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.commit()


def test_reviews_are_moderated_reportable_and_safety_filtered() -> None:
    token = uuid.uuid4().hex[:10]
    author_email = f"review-author-{token}@example.com"
    reader_email = f"review-reader-{token}@example.com"
    admin_email = f"review-admin-{token}@example.com"
    password = "CommunityViewerPassword123"
    admin_password = "CommunityAdminPassword123"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        movie = Movie(
            title=f"Community Film {token}",
            slug=f"moderated-film-{token}",
            short_description="A moderated community fixture.",
            synopsis="Community acceptance.",
            runtime_minutes=90,
            status=CatalogStatus.published,
            rights_start_at=now - timedelta(days=1),
            rights_end_at=now + timedelta(days=1),
        )
        admin = Admin(email=admin_email, password_hash=hash_password(admin_password))
        db.add_all([movie, admin])
        db.commit()
        movie_id, admin_id = movie.id, admin.id

    with (
        TestClient(app) as author,
        TestClient(app) as reader,
        TestClient(app) as moderator,
    ):
        author_registration = author.post(
            "/auth/register",
            json={"email": author_email, "password": password, "profile_name": "Reviewer"},
        )
        reader_registration = reader.post(
            "/auth/register",
            json={"email": reader_email, "password": password, "profile_name": "Reader"},
        )
        assert author_registration.status_code == reader_registration.status_code == 201
        author_profile = author_registration.json()["active_profile_id"]
        reader_profile = reader_registration.json()["active_profile_id"]

        rating = author.put(f"/community/movies/{movie_id}/rating", json={"score": 5})
        assert rating.status_code == 200, rating.text
        assert rating.json()["score"] == 5
        review = author.put(
            f"/community/movies/{movie_id}/review",
            json={
                "headline": "A precise ending",
                "body": "The final image changes the meaning of the opening.",
                "contains_spoilers": True,
            },
        )
        assert review.status_code == 200, review.text
        assert review.json()["status"] == "pending"
        review_id = review.json()["id"]
        assert reader.get(f"/community/movies/{movie_id}").json()["reviews"] == []
        assert (
            reader.post(
                "/community/reports",
                json={"review_id": review_id, "reason": "spoiler"},
            ).status_code
            == 404
        )

        assert (
            moderator.post(
                "/admin/auth/login", json={"email": admin_email, "password": admin_password}
            ).status_code
            == 200
        )
        queue = moderator.get("/admin/community/queue")
        assert queue.status_code == 200
        assert any(item["id"] == review_id for item in queue.json()["reviews"])
        decision = moderator.post(
            f"/admin/community/reviews/{review_id}/decision",
            json={"status": "approved", "reason": "Meets the community guidelines."},
        )
        assert decision.status_code == 200, decision.text

        community = reader.get(f"/community/movies/{movie_id}").json()
        assert community["rating_count"] == 1
        assert community["average_rating"] == 5.0
        assert community["viewer_rating"] is None
        assert community["reviews"][0]["contains_spoilers"] is True
        assert community["reviews"][0]["profile_name"] == "Reviewer"
        assert community["reviews"][0]["moderation_note"] is None

        follow = reader.put(f"/community/follows/{author_profile}")
        assert follow.status_code == 200 and follow.json()["following"] is True
        public_list = author.post(
            "/curation/my-lists",
            json={
                "title": "Ending Studies",
                "description": "A moderated public list.",
                "visibility": "public",
                "items": [{"movie_id": str(movie_id), "note": "Study the final image."}],
            },
        )
        assert public_list.status_code == 201, public_list.text
        list_id = public_list.json()["id"]
        list_slug = public_list.json()["slug"]
        assert reader.get("/community/lists").json() == []
        queue_with_list = moderator.get("/admin/community/queue").json()
        assert any(item["id"] == list_id for item in queue_with_list["lists"])
        assert (
            moderator.post(
                f"/admin/community/lists/{list_id}/decision",
                json={"status": "approved", "reason": "The list meets publication policy."},
            ).status_code
            == 200
        )
        visible_lists = reader.get("/community/lists").json()
        assert visible_lists[0]["slug"] == list_slug
        assert visible_lists[0]["owner_profile_name"] == "Reviewer"
        assert reader.get(f"/community/lists/{list_slug}").status_code == 200
        activity_kinds = {item["kind"] for item in reader.get("/community/activity").json()}
        assert {"review_published", "list_published"} <= activity_kinds
        report = reader.post(
            "/community/reports",
            json={"review_id": review_id, "reason": "spoiler", "details": "Spoiler label check"},
        )
        assert report.status_code == 201, report.text
        report_id = report.json()["id"]
        assert moderator.get("/admin/community/queue").json()["reports"][0]["id"] == report_id
        assert (
            moderator.post(
                f"/admin/community/reports/{report_id}/decision",
                json={"status": "dismissed", "reason": "The spoiler flag is already present."},
            ).status_code
            == 200
        )

        muted = reader.put(f"/community/safety/{author_profile}/mute")
        assert muted.status_code == 200
        assert reader.get(f"/community/movies/{movie_id}").json()["reviews"] == []
        assert reader.get("/community/lists").json() == []
        assert reader.get("/community/activity").json() == []
        assert reader.delete(f"/community/safety/{author_profile}/mute").status_code == 204
        assert len(reader.get(f"/community/movies/{movie_id}").json()["reviews"]) == 1
        assert reader.put(f"/community/safety/{author_profile}/block").status_code == 200
        assert reader.put(f"/community/follows/{author_profile}").status_code == 409
        assert author.put(f"/community/follows/{reader_profile}").status_code == 409

        edited = author.put(
            f"/community/movies/{movie_id}/review",
            json={"body": "Edited content requires a fresh decision.", "contains_spoilers": False},
        )
        assert edited.status_code == 200 and edited.json()["status"] == "pending"
        assert reader.get(f"/community/movies/{movie_id}").json()["reviews"] == []

    with SessionLocal() as db:
        db.execute(delete(ModerationAction).where(ModerationAction.admin_id == admin_id))
        db.execute(delete(User).where(User.email.in_([author_email, reader_email])))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
