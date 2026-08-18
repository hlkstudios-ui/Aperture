import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.config import get_settings
from app.db import SessionLocal
from app.geo import sign_geo_assertion
from app.main import app
from app.models import (
    Admin,
    AssetState,
    AuditLog,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    ProcessingState,
    User,
)


def test_private_club_and_entitlement_safe_party_synchronization() -> None:
    token = uuid.uuid4().hex[:10]
    host_email = f"club-host-{token}@example.com"
    member_email = f"club-member-{token}@example.com"
    password = "MovieClubViewerPassword123"
    now = datetime.now(UTC)
    with SessionLocal() as db:
        admin = Admin(
            email=f"club-admin-{token}@example.com", password_hash=hash_password(password)
        )
        movie = Movie(
            title=f"Club Film {token}",
            slug=f"club-film-{token}",
            short_description="Club fixture.",
            synopsis="Club fixture.",
            runtime_minutes=90,
            status=CatalogStatus.published,
            rights_start_at=now - timedelta(days=1),
            rights_end_at=now + timedelta(days=1),
            allowed_territories=["CA"],
        )
        db.add_all([admin, movie])
        db.flush()
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="club.mp4",
            media_type="video/mp4",
            size_bytes=1,
            checksum_sha256=hashlib.sha256(b"x").hexdigest(),
            storage_key=f"source/{token}.mp4",
            state=AssetState.completed,
            completed_at=now,
        )
        db.add(asset)
        db.flush()
        job = ProcessingJob(
            asset_id=asset.id,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=120,
            manifest_key=f"processed/{token}/master.m3u8",
            rendition_status=[],
            audio_tracks=[],
            subtitle_tracks=[],
        )
        db.add(job)
        db.flush()
        source = PlaybackSource(processing_job_id=job.id, movie_id=movie.id)
        db.add(source)
        db.commit()
        admin_id, movie_id, source_id, asset_id = admin.id, movie.id, source.id, asset.id
    with TestClient(app) as host, TestClient(app) as member:
        host_registration = host.post(
            "/auth/register",
            json={"email": host_email, "password": password, "profile_name": "Club Host"},
        )
        member_registration = member.post(
            "/auth/register",
            json={"email": member_email, "password": password, "profile_name": "Club Member"},
        )
        assert host_registration.status_code == member_registration.status_code == 201
        issued_at = int(datetime.now(UTC).timestamp())
        geo_headers = {
            "X-Aperture-Country": "CA",
            "X-Aperture-Geo-Timestamp": str(issued_at),
            "X-Aperture-Geo-Signature": sign_geo_assertion(
                "CA", issued_at, get_settings().geo_assertion_secret
            ),
        }
        host.headers.update(geo_headers)
        member.headers.update(geo_headers)
        club = host.post(
            "/clubs", json={"name": "Midnight Frames", "description": "Private weekly screenings."}
        )
        assert club.status_code == 201, club.text
        club_id = club.json()["id"]
        invite = club.json()["invite_token"]
        joined_club = member.post("/clubs/join", json={"invite_token": invite})
        assert joined_club.status_code == 200
        member_profile_id = next(
            item["profile_id"]
            for item in joined_club.json()["members"]
            if item["name"] == "Club Member"
        )
        promoted = host.put(
            f"/clubs/{club_id}/members/{member_profile_id}",
            json={"role": "moderator", "status": "active"},
        )
        assert promoted.status_code == 200
        scheduled = host.post(
            f"/clubs/{club_id}/schedule",
            json={
                "movie_id": str(movie_id),
                "playback_source_id": str(source_id),
                "title": "Friday screening",
                "scheduled_at": (now + timedelta(hours=1)).isoformat(),
            },
        )
        assert scheduled.status_code == 200, scheduled.text
        watch_id = scheduled.json()["scheduled_watches"][0]["id"]
        for name in geo_headers:
            del host.headers[name]
        assert host.get(f"/clubs/{club_id}").json()["scheduled_watches"] == []
        host.headers.update(geo_headers)
        poll = host.post(
            f"/clubs/{club_id}/polls",
            json={
                "question": "What should follow?",
                "options": [{"label": "A restoration"}, {"label": "A debut"}],
            },
        )
        assert poll.status_code == 200
        poll_id = poll.json()["polls"][0]["id"]
        option_id = poll.json()["polls"][0]["options"][0]["id"]
        assert (
            member.put(
                f"/clubs/{club_id}/polls/{poll_id}/vote", json={"option_id": option_id}
            ).status_code
            == 200
        )
        discussion = member.post(
            f"/clubs/{club_id}/discussion",
            json={"body": "The last composition rewards a second look.", "contains_spoilers": True},
        )
        assert (
            discussion.status_code == 200
            and discussion.json()["discussion"][0]["contains_spoilers"] is True
        )
        post_id = discussion.json()["discussion"][0]["id"]
        removed = host.delete(f"/clubs/{club_id}/discussion/{post_id}")
        assert removed.status_code == 200 and removed.json()["discussion"] == []
        party = host.post(f"/clubs/{club_id}/parties", json={"scheduled_watch_id": watch_id})
        assert party.status_code == 201, party.text
        party_id = party.json()["id"]
        party_token = party.json()["access_token"]
        duplicate = host.post(f"/clubs/{club_id}/parties", json={"scheduled_watch_id": watch_id})
        assert duplicate.status_code == 409
        joined = member.post(f"/clubs/parties/{party_id}/join", json={"access_token": party_token})
        assert joined.status_code == 200, joined.text
        assert len(joined.json()["participants"]) == 2
        assert (
            member.post(
                f"/clubs/parties/{party_id}/control",
                json={"kind": "play", "position_seconds": 10, "expected_revision": 0},
            ).status_code
            == 403
        )
        controlled = host.post(
            f"/clubs/parties/{party_id}/control",
            json={"kind": "play", "position_seconds": 10, "expected_revision": 0},
        )
        assert controlled.status_code == 200 and controlled.json()["revision"] == 1
        heartbeat = member.post(
            f"/clubs/parties/{party_id}/heartbeat",
            json={"client_position_seconds": 0, "expected_revision": 1},
        )
        assert heartbeat.status_code == 200 and heartbeat.json()["correction_required"] is True
        assert heartbeat.json()["seek_to_seconds"] >= 10
        stale_heartbeat = member.post(
            f"/clubs/parties/{party_id}/heartbeat",
            json={
                "client_position_seconds": heartbeat.json()["effective_position_seconds"],
                "expected_revision": 0,
            },
        )
        assert stale_heartbeat.status_code == 200
        assert stale_heartbeat.json()["correction_required"] is True
        message = member.post(
            f"/clubs/parties/{party_id}/messages", json={"kind": "reaction", "body": "👏"}
        )
        assert message.status_code == 200 and message.json()["messages"][0]["body"] == "👏"
        ended = host.post(
            f"/clubs/parties/{party_id}/control",
            json={"kind": "ended", "position_seconds": 120, "expected_revision": 1},
        )
        assert ended.status_code == 200 and ended.json()["state"] == "ended"
        assert (
            member.post(
                f"/clubs/parties/{party_id}/join", json={"access_token": party_token}
            ).status_code
            == 409
        )
        completed_club = host.get(f"/clubs/{club_id}")
        assert completed_club.json()["scheduled_watches"][0]["status"] == "completed"
        assert all(item["completed"] for item in completed_club.json()["watch_history"])
        with SessionLocal() as db:
            db.get(Movie, movie_id).rights_end_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        assert member.get(f"/clubs/parties/{party_id}").status_code == 404
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email.in_([host_email, member_email])))
        db.execute(delete(PlaybackSource).where(PlaybackSource.id == source_id))
        db.execute(delete(ProcessingJob).where(ProcessingJob.asset_id == asset_id))
        db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
