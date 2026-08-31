import hashlib
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from threading import Barrier
from urllib.parse import urlsplit

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Character, Credit, Language, Movie, Person
from app.config import get_settings
from app.db import SessionLocal
from app.main import app
from app.models import (
    Admin,
    AskMovieLog,
    AssetState,
    AuditLog,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    ProcessingState,
    User,
)
from app.object_storage import s3_client
from app.scene_models import SceneRelationship
from app.scene_worker import process_scene_job


def test_secure_playback_assignment_delivery_and_profile_progress() -> None:
    token = uuid.uuid4()
    prefix = f"processed/playback-test/{token}"
    manifest = b"#EXTM3U\n#EXT-X-STREAM-INF:BANDWIDTH=500000,RESOLUTION=640x360\n360p/index.m3u8\n"
    variant = b"#EXTM3U\n#EXTINF:3.0,\nsegment_00000.ts\n#EXT-X-ENDLIST\n"
    segment = b"test-transport-stream-payload"
    captions = b"""WEBVTT

00:00:00.000 --> 00:00:03.000
The signal begins at the beacon.

00:00:08.000 --> 00:00:11.000
The harbor answers.
"""
    client_s3 = s3_client()
    for key, body, media_type in (
        (f"{prefix}/master.m3u8", manifest, "application/vnd.apple.mpegurl"),
        (f"{prefix}/360p/index.m3u8", variant, "application/vnd.apple.mpegurl"),
        (f"{prefix}/360p/segment_00000.ts", segment, "video/mp2t"),
        (f"{prefix}/subtitles/track-0.vtt", captions, "text/vtt"),
    ):
        client_s3.put_object(
            Bucket=get_settings().s3_bucket, Key=key, Body=body, ContentType=media_type
        )

    admin_email = f"playback-admin-{token}@example.com"
    viewer_email = f"playback-viewer-{token}@example.com"
    password = "PlaybackAdministrator123"
    english_locale_created = False
    with SessionLocal() as db:
        if db.get(Language, "en") is None:
            db.add(Language(code="en", name="English"))
            english_locale_created = True
        admin = Admin(email=admin_email, password_hash=hash_password(password))
        movie = Movie(
            title=f"Playback Fixture {token}",
            slug=f"secure-playback-film-{token}",
            short_description="A secure playback integration fixture.",
            synopsis="Original test metadata.",
            runtime_minutes=1,
            status=CatalogStatus.published,
        )
        db.add_all([admin, movie])
        db.flush()
        director = Person(
            name=f"Playback Director {token}",
            slug=f"playback-director-{token}",
        )
        actor = Person(
            name=f"Playback Actor {token}",
            slug=f"playback-actor-{token}",
        )
        db.add_all([director, actor])
        character = Character(
            name=f"Playback Character {token}",
            slug=f"playback-character-{token}",
        )
        db.add(character)
        db.flush()
        db.add(Credit(movie_id=movie.id, person_id=director.id, role="director"))
        db.add(
            Credit(
                movie_id=movie.id,
                person_id=actor.id,
                character_id=character.id,
                role="actor",
            )
        )
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="playback-fixture.mp4",
            media_type="video/mp4",
            size_bytes=len(segment),
            checksum_sha256=hashlib.sha256(segment).hexdigest(),
            storage_key=f"source/{token}/{token}.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        db.add(asset)
        db.flush()
        job = ProcessingJob(
            asset=asset,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=30,
            manifest_key=f"{prefix}/master.m3u8",
            rendition_status=[
                {
                    "height": 360,
                    "width": 640,
                    "bandwidth": 500000,
                    "state": "ready",
                }
            ],
            audio_tracks=[{"index": 1, "codec": "aac", "language": "en"}],
            subtitle_tracks=[
                {
                    "index": 2,
                    "codec": "webvtt",
                    "language": "en",
                    "state": "ready",
                    "key": "subtitles/track-0.vtt",
                }
            ],
        )
        db.add(job)
        alternate_asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="playback-fixture-extended.mp4",
            media_type="video/mp4",
            size_bytes=len(segment),
            checksum_sha256=hashlib.sha256(segment).hexdigest(),
            storage_key=f"source/{token}/{token}-extended.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        db.add(alternate_asset)
        db.flush()
        alternate_job = ProcessingJob(
            asset=alternate_asset,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=30,
            manifest_key=f"{prefix}/master.m3u8",
            rendition_status=job.rendition_status,
            audio_tracks=[{"index": 1, "codec": "aac", "language": "en"}],
            subtitle_tracks=[],
        )
        db.add(alternate_job)
        db.commit()
        admin_id, movie_id, director_id, actor_id, character_id, job_id, alternate_job_id, slug = (
            admin.id,
            movie.id,
            director.id,
            actor.id,
            character.id,
            job.id,
            alternate_job.id,
            movie.slug,
        )
        alternate_asset_id = alternate_asset.id

    with TestClient(app) as anonymous:
        assert anonymous.get(f"/playback/movies/{slug}").status_code == 401

    with TestClient(app) as admin_client:
        assert (
            admin_client.post(
                "/admin/auth/login", json={"email": admin_email, "password": password}
            ).status_code
            == 200
        )
        theatrical = admin_client.post(
            "/admin/catalog/editions",
            json={
                "movie_id": str(movie_id),
                "name": "Original theatrical presentation",
                "runtime_minutes": 1,
                "notes": "Verified original release configuration.",
                "is_default": True,
                "intended_presentation": True,
                "aspect_ratio": "2.39:1",
                "frame_rate": 24,
                "presentation_format": "Original theatrical framing",
                "capture_format": "35 mm",
                "audio_format": "5.1 surround",
                "original_language_code": "en",
                "restoration_info": "Restored from the project test master.",
                "source_info": "Original project-owned source master.",
            },
        )
        assert theatrical.status_code == 201, theatrical.text
        theatrical_id = theatrical.json()["id"]
        extended = admin_client.post(
            "/admin/catalog/editions",
            json={
                "movie_id": str(movie_id),
                "name": "Extended comparison cut",
                "runtime_minutes": 2,
                "notes": "Licensed comparison metadata; media not yet assigned.",
            },
        )
        assert extended.status_code == 201, extended.text
        extended_id = extended.json()["id"]
        difference = admin_client.post(
            "/admin/catalog/edition-differences",
            json={
                "source_edition_id": theatrical_id,
                "target_edition_id": extended_id,
                "kind": "inserted_scene",
                "description": "The extended cut adds the verified archive epilogue.",
                "reveal_seconds": 30,
                "source_note": "Original project comparison record.",
                "manually_verified": True,
            },
        )
        assert difference.status_code == 201, difference.text
        assigned = admin_client.post(
            "/admin/playback/sources",
            json={
                "processing_job_id": str(job_id),
                "movie_id": str(movie_id),
                "edition_id": theatrical_id,
                "intro_start_seconds": 0,
                "intro_end_seconds": 5,
                "credits_start_seconds": 25,
            },
        )
        assert assigned.status_code == 201, assigned.text
        source_id = assigned.json()["id"]
        alternate_assigned = admin_client.post(
            "/admin/playback/sources",
            json={
                "processing_job_id": str(alternate_job_id),
                "movie_id": str(movie_id),
                "edition_id": extended_id,
                "credits_start_seconds": 25,
            },
        )
        assert alternate_assigned.status_code == 201, alternate_assigned.text
        alternate_source_id = alternate_assigned.json()["id"]
        version = admin_client.post(
            "/admin/scenes",
            json={"playback_source_id": source_id, "notes": "Manual acceptance version"},
        )
        assert version.status_code == 201, version.text
        version_id = version.json()["id"]
        invalid_empty = admin_client.post(f"/admin/scenes/{version_id}/validate")
        assert invalid_empty.status_code == 422
        assert "At least one provenance source" in str(invalid_empty.json())
        provenance = admin_client.post(
            f"/admin/scenes/{version_id}/sources",
            json={
                "kind": "manual",
                "label": "Administrator scene review",
                "license_basis": "Original test metadata owned by the project",
            },
        )
        assert provenance.status_code == 201, provenance.text
        source_provenance_id = provenance.json()["id"]
        subtitle_provenance = admin_client.post(
            f"/admin/scenes/{version_id}/sources",
            json={
                "kind": "subtitle",
                "label": "Licensed embedded English captions",
                "source_uri": f"storage://{prefix}/subtitles/track-0.vtt",
                "checksum_sha256": hashlib.sha256(captions).hexdigest(),
                "license_basis": "Original test captions owned by the project",
            },
        )
        assert subtitle_provenance.status_code == 201, subtitle_provenance.text
        invalid_scene = admin_client.post(
            f"/admin/scenes/{version_id}/scenes",
            json={
                "source_id": source_provenance_id,
                "ordinal": 1,
                "title": "Outside the reel",
                "summary": "This must be rejected.",
                "start_seconds": 20,
                "end_seconds": 40,
                "confidence": 1,
                "manually_verified": True,
            },
        )
        assert invalid_scene.status_code == 422
        scene = admin_client.post(
            f"/admin/scenes/{version_id}/scenes",
            json={
                "source_id": source_provenance_id,
                "ordinal": 1,
                "title": "The signal",
                "summary": "A verified original scene summary.",
                "start_seconds": 0,
                "end_seconds": 30,
                "confidence": 1,
                "manually_verified": True,
            },
        )
        assert scene.status_code == 201, scene.text
        scene_id = scene.json()["id"]
        assert (
            admin_client.post(
                f"/admin/scenes/{version_id}/chapters",
                json={
                    "source_id": source_provenance_id,
                    "ordinal": 1,
                    "title": "Arrival",
                    "start_seconds": 0,
                    "end_seconds": 30,
                },
            ).status_code
            == 201
        )
        character_link = admin_client.post(
            f"/admin/scenes/{version_id}/scenes/{scene_id}/characters",
            json={
                "source_id": source_provenance_id,
                "character_id": str(character_id),
                "confidence": 1,
                "reveal_seconds": 2,
                "manually_verified": True,
            },
        )
        assert character_link.status_code == 201, character_link.text
        entity_one = admin_client.post(
            f"/admin/scenes/{version_id}/scenes/{scene_id}/entities",
            json={
                "source_id": source_provenance_id,
                "entity_type": "place",
                "name": "Beacon",
                "canonical_key": "beacon",
                "description": "A signal tower.",
                "confidence": 1,
                "reveal_seconds": 3,
            },
        )
        entity_two = admin_client.post(
            f"/admin/scenes/{version_id}/scenes/{scene_id}/entities",
            json={
                "source_id": source_provenance_id,
                "entity_type": "object",
                "name": "Signal",
                "canonical_key": "signal",
                "confidence": 1,
                "reveal_seconds": 4,
            },
        )
        assert entity_one.status_code == 201 and entity_two.status_code == 201
        relationship = admin_client.post(
            f"/admin/scenes/{version_id}/scenes/{scene_id}/relationships",
            json={
                "source_id": source_provenance_id,
                "subject_entity_id": entity_one.json()["id"],
                "object_entity_id": entity_two.json()["id"],
                "relationship": "emits",
                "confidence": 1,
                "reveal_seconds": 4,
            },
        )
        assert relationship.status_code == 201, relationship.text
        relationship_id = relationship.json()["id"]
        assert (
            admin_client.post(
                f"/admin/scenes/{version_id}/scenes/{scene_id}/music-cues",
                json={
                    "source_id": source_provenance_id,
                    "title": "Original Signal",
                    "composer": "Project Composer",
                    "start_seconds": 5,
                    "end_seconds": 8,
                },
            ).status_code
            == 201
        )
        assert (
            admin_client.post(
                f"/admin/scenes/{version_id}/scenes/{scene_id}/production-notes",
                json={
                    "source_id": source_provenance_id,
                    "category": "camera",
                    "note": "Original manual production note.",
                    "reveal_seconds": 6,
                },
            ).status_code
            == 201
        )
        after_credits_note = admin_client.post(
            f"/admin/scenes/{version_id}/scenes/{scene_id}/production-notes",
            json={
                "source_id": source_provenance_id,
                "category": "ending_analysis",
                "note": "The verified signal ending resolves the opening visual motif.",
                "reveal_seconds": 30,
            },
        )
        assert after_credits_note.status_code == 201, after_credits_note.text
        assert (
            admin_client.post(
                f"/admin/scenes/{version_id}/spoiler-boundaries",
                json={
                    "source_id": source_provenance_id,
                    "label": "Signal reveal",
                    "description": "The signal source becomes visible.",
                    "reveal_seconds": 4,
                },
            ).status_code
            == 201
        )
        queued = admin_client.post(f"/admin/scenes/{version_id}/jobs")
        assert queued.status_code == 202
        process_scene_job(uuid.UUID(queued.json()["id"]))
        enriched = admin_client.get(f"/admin/scenes/{version_id}")
        assert enriched.json()["jobs"][0]["state"] == "completed"
        search = admin_client.get("/admin/scenes/search", params={"q": "harbor"})
        assert search.status_code == 200, search.text
        assert any(result["scene"]["id"] == scene_id for result in search.json())
        validated = admin_client.post(f"/admin/scenes/{version_id}/validate")
        assert validated.status_code == 200, validated.text
        published = admin_client.post(f"/admin/scenes/{version_id}/publish")
        assert published.status_code == 200, published.text
        assert published.json()["state"] == "published"
        detail = admin_client.get(f"/admin/scenes/{version_id}")
        assert detail.status_code == 200, detail.text
        assert detail.json()["validation_errors"] == []
        assert len(detail.json()["scenes"]) == 1
        assert len(detail.json()["entities"]) == 2
        assert len(detail.json()["relationships"]) == 1
        assert len(detail.json()["music_cues"]) == 1
        assert len(detail.json()["production_notes"]) == 2
        assert len(detail.json()["spoiler_boundaries"]) == 1
        gallery_key = f"gallery/playback-test/{token}.jpg"
        client_s3.put_object(
            Bucket=get_settings().s3_bucket,
            Key=gallery_key,
            Body=b"\xff\xd8\xff\xdbpermitted-test-still\xff\xd9",
            ContentType="image/jpeg",
        )
        invalid_gallery = admin_client.post(
            "/admin/catalog/artwork",
            json={
                "movie_id": str(movie_id),
                "kind": "still",
                "storage_key": gallery_key,
                "alt_text": "The verified beacon still",
                "permitted_for_gallery": True,
            },
        )
        assert invalid_gallery.status_code == 422
        gallery = admin_client.post(
            "/admin/catalog/artwork",
            json={
                "movie_id": str(movie_id),
                "kind": "still",
                "scene_id": scene_id,
                "timestamp_seconds": 4,
                "rights_basis": "Original test still owned by the project",
                "permitted_for_gallery": True,
                "storage_key": gallery_key,
                "alt_text": "The verified beacon still",
                "width": 640,
                "height": 360,
            },
        )
        assert gallery.status_code == 201, gallery.text
        gallery_id = gallery.json()["id"]

    with TestClient(app) as viewer:
        registration = viewer.post(
            "/auth/register",
            json={
                "email": viewer_email,
                "password": "PlaybackViewerPassword123",
                "profile_name": "Viewer One",
            },
        )
        assert registration.status_code == 201
        primary_profile_id = registration.json()["active_profile_id"]
        preference = viewer.patch(
            f"/profiles/{primary_profile_id}",
            json={
                "preference": {
                    "preferred_audio_language": "en",
                    "preferred_subtitle_language": "en",
                    "preferred_secondary_subtitle_language": "fr",
                    "subtitles_enabled": True,
                    "timezone": "America/Toronto",
                    "caption_size": "large",
                    "caption_background": "solid",
                    "caption_position": "top",
                }
            },
        )
        assert preference.status_code == 200, preference.text
        config = viewer.get(f"/playback/movies/{slug}")
        assert config.status_code == 200, config.text
        assert config.json()["edition_id"] == theatrical_id
        assert config.json()["original_language_code"] == "en"
        assert config.json()["preferred_audio_language"] == "en"
        assert config.json()["preferred_subtitle_language"] == "en"
        assert config.json()["preferred_secondary_subtitle_language"] == "fr"
        assert config.json()["subtitles_enabled"] is True
        assert config.json()["caption_size"] == "large"
        assert config.json()["caption_background"] == "solid"
        assert config.json()["caption_position"] == "top"
        assert config.json()["manifest_url"] == (
            f"/playback/sources/{source_id}/media/master.m3u8"
        )
        assert all(
            track["url"].startswith(f"/playback/sources/{source_id}/media/")
            for track in config.json()["subtitle_tracks"]
        )
        knowledge = viewer.get(f"/catalog/movies/{slug}/knowledge-graph")
        assert knowledge.status_code == 200, knowledge.text
        assert knowledge.json()["derived_from"] == "normalized_verified_catalog"
        assert any(
            node["kind"] == "person" and node["label"].startswith("Playback Director")
            for node in knowledge.json()["nodes"]
        )
        assert any(edge["label"] == "portrays" for edge in knowledge.json()["edges"])
        actor_destination = viewer.get(f"/catalog/people/playback-actor-{token}/credits")
        assert actor_destination.status_code == 200, actor_destination.text
        assert actor_destination.json()["titles"] == [
            {
                "id": str(movie_id),
                "kind": "movie",
                "title": f"Playback Fixture {token}",
                "href": f"/movies/{slug}",
                "role": "actor",
                "character_name": f"Playback Character {token}",
            }
        ]
        assert config.json()["intro"] == [0.0, 5.0]
        assert config.json()["qualities"][0]["height"] == 360
        assert (
            viewer.get(
                f"/scene-intelligence/sources/{source_id}/context",
                params={"timestamp": "nan"},
            ).status_code
            == 422
        )
        assert (
            viewer.get(
                f"/scene-intelligence/sources/{source_id}/context",
                params={"timestamp": 31},
            ).status_code
            == 422
        )
        before_relationship = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 3.99},
        )
        assert before_relationship.status_code == 200, before_relationship.text
        before_kinds = [item["kind"] for item in before_relationship.json()["facts"]]
        assert "character" in before_kinds
        assert "relationship" not in before_kinds
        assert "scene" not in before_kinds
        assert before_relationship.json()["withheld"]["relationship"] == 1
        exactly_relationship = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 4},
        )
        exact_body = exactly_relationship.json()
        assert exact_body["equality_policy"] == "inclusive"
        assert exact_body["current_scene"]["id"] == scene_id
        assert any(item["kind"] == "relationship" for item in exact_body["facts"])
        character_fact = next(item for item in exact_body["facts"] if item["kind"] == "character")
        assert character_fact["payload"]["character_name"].startswith("Playback Character")
        assert character_fact["payload"]["actor_name"].startswith("Playback Actor")
        who_tool = viewer.get(
            f"/scene-intelligence/sources/{source_id}/who-was-that",
            params={"timestamp": 4},
        )
        assert who_tool.status_code == 200, who_tool.text
        assert who_tool.json()["characters"][0]["actor_name"].startswith("Playback Actor")
        assert who_tool.json()["known_relationships"] == ["Beacon emits Signal"]
        graph_before_reveal = viewer.get(
            f"/scene-intelligence/sources/{source_id}/relationship-graph",
            params={"timestamp": 3},
        )
        assert graph_before_reveal.status_code == 200
        assert graph_before_reveal.json()["edges"] == []
        graph_at_reveal = viewer.get(
            f"/scene-intelligence/sources/{source_id}/relationship-graph",
            params={"timestamp": 4},
        )
        assert graph_at_reveal.status_code == 200
        assert len(graph_at_reveal.json()["nodes"]) == 2
        assert graph_at_reveal.json()["edges"][0]["label"] == "emits"
        assert graph_at_reveal.json()["edges"][0]["reveal_seconds"] == 4
        toolkit_before_still = viewer.get(
            f"/cinephile/sources/{source_id}", params={"timestamp": 3.99}
        )
        assert toolkit_before_still.status_code == 200
        assert toolkit_before_still.json()["stills"] == []
        assert toolkit_before_still.json()["music_timeline"] == []
        toolkit_at_still = viewer.get(f"/cinephile/sources/{source_id}", params={"timestamp": 4})
        assert toolkit_at_still.status_code == 200, toolkit_at_still.text
        assert toolkit_at_still.json()["stills"][0]["id"] == gallery_id
        assert len(toolkit_at_still.json()["credits"]) == 2
        assert toolkit_at_still.json()["rewatch"]["viewings_started"] == 0
        assert toolkit_at_still.json()["edition_comparison_unlocked"] is False
        assert toolkit_at_still.json()["edition_comparisons"] == []
        assert toolkit_at_still.json()["editions"][0]["aspect_ratio"] == "2.39:1"
        assert toolkit_at_still.json()["editions"][0]["available"] is True
        assert toolkit_at_still.json()["editions"][1]["available"] is True
        assert toolkit_at_still.json()["editions"][1]["playback_source_id"] == alternate_source_id
        locked_room = viewer.get(f"/cinephile/sources/{source_id}/after-credits")
        assert locked_room.status_code == 200, locked_room.text
        assert locked_room.json()["unlocked"] is False
        assert locked_room.json()["modules"] == []
        assert (
            viewer.get(
                f"/cinephile/sources/{source_id}/stills/{gallery_id}",
                params={"timestamp": 3.99},
            ).status_code
            == 404
        )
        permitted_image = viewer.get(
            f"/cinephile/sources/{source_id}/stills/{gallery_id}",
            params={"timestamp": 4},
        )
        assert permitted_image.status_code == 200
        assert permitted_image.headers["content-type"] == "image/jpeg"
        toolkit_details = viewer.get(
            f"/cinephile/sources/{source_id}", params={"timestamp": 6}
        ).json()
        assert toolkit_details["music_timeline"][0]["title"] == "Original Signal"
        assert toolkit_details["filmmaking"][0]["category"] == "camera"
        missed_early = viewer.post(
            f"/scene-intelligence/sources/{source_id}/what-did-i-miss",
            json={"start_seconds": 0, "end_seconds": 29, "current_timestamp": 29},
        )
        assert missed_early.json()["confidence"] == "unavailable"
        missed_boundary = viewer.post(
            f"/scene-intelligence/sources/{source_id}/what-did-i-miss",
            json={"start_seconds": 0, "end_seconds": 30, "current_timestamp": 30},
        )
        assert missed_boundary.json()["recap"] == "A verified original scene summary."
        future_interval = viewer.post(
            f"/scene-intelligence/sources/{source_id}/what-did-i-miss",
            json={"start_seconds": 0, "end_seconds": 30, "current_timestamp": 29},
        )
        assert future_interval.status_code == 422
        who = viewer.post(
            f"/scene-intelligence/sources/{source_id}/ask",
            json={"question": "Who is this character?", "timestamp_seconds": 4},
        )
        assert who.status_code == 200, who.text
        assert who.json()["confidence"] == "supported"
        assert "Playback Actor" in who.json()["answer"]
        future_summary = viewer.post(
            f"/scene-intelligence/sources/{source_id}/ask",
            json={"question": "What happened in this scene?", "timestamp_seconds": 29},
        )
        assert future_summary.json()["confidence"] == "unavailable"
        assert "not available" in future_summary.json()["answer"]
        ending_summary = viewer.post(
            f"/scene-intelligence/sources/{source_id}/ask",
            json={"question": "What happened in this scene?", "timestamp_seconds": 30},
        )
        assert ending_summary.json()["answer"] == "A verified original scene summary."
        unsupported = viewer.post(
            f"/scene-intelligence/sources/{source_id}/ask",
            json={"question": "Why does the future matter?", "timestamp_seconds": 4},
        )
        assert unsupported.json()["confidence"] == "unavailable"
        assert unsupported.json()["evidence"] == []
        bookmark = viewer.post(
            f"/scene-intelligence/sources/{source_id}/bookmarks",
            json={"scene_id": scene_id, "timestamp_seconds": 4, "title": "The signal"},
        )
        assert bookmark.status_code == 201, bookmark.text
        note = viewer.post(
            f"/scene-intelligence/sources/{source_id}/notes",
            json={"scene_id": scene_id, "timestamp_seconds": 4, "body": "Remember the beacon."},
        )
        assert note.status_code == 201, note.text
        lens_library = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context", params={"timestamp": 4}
        ).json()
        assert lens_library["bookmarks"][0]["title"] == "The signal"
        assert lens_library["notes"][0]["body"] == "Remember the beacon."
        assert (
            viewer.delete(f"/scene-intelligence/bookmarks/{bookmark.json()['id']}").status_code
            == 204
        )
        assert viewer.delete(f"/scene-intelligence/notes/{note.json()['id']}").status_code == 204
        with SessionLocal() as db:
            logs = list(
                db.scalars(
                    select(AskMovieLog).where(
                        AskMovieLog.playback_source_id == uuid.UUID(source_id)
                    )
                )
            )
            assert len(logs) == 4
            assert all(len(item.question_sha256) == 64 for item in logs)
            assert all("Who is this character?" not in str(item.provenance) for item in logs)
            assert all(
                fact["reveal_seconds"] <= item.timestamp_seconds
                for item in logs
                for fact in item.provenance
            )
        assert not any(item["kind"] == "production_note" for item in exact_body["facts"])
        ending_blocked = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 29},
        )
        assert not any(item["kind"] == "scene" for item in ending_blocked.json()["facts"])
        ending_available = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 30},
        )
        assert any(item["kind"] == "scene" for item in ending_available.json()["facts"])
        locked_full = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 4, "mode": "full"},
        )
        assert locked_full.status_code == 403
        with SessionLocal() as db:
            record = db.get(SceneRelationship, uuid.UUID(relationship_id))
            record.reveal_seconds = float("nan")
            db.commit()
        malformed = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 30},
        )
        assert malformed.json()["safety_state"] == "malformed_evidence_omitted"
        assert not any(item["kind"] == "relationship" for item in malformed.json()["facts"])
        with SessionLocal() as db:
            record = db.get(SceneRelationship, uuid.UUID(relationship_id))
            record.reveal_seconds = 4
            db.commit()
        settings = get_settings()
        original_delivery = (
            settings.media_delivery_mode,
            settings.cdn_public_origin,
            settings.cdn_signing_secret,
            settings.cdn_origin_secret,
        )
        settings.media_delivery_mode = "cdn"
        settings.cdn_public_origin = "https://media.example.test"
        settings.cdn_signing_secret = "test-signing-secret-with-at-least-32-characters"
        settings.cdn_origin_secret = "test-origin-secret-with-at-least-32-characters"
        try:
            cdn_config = viewer.get(f"/playback/movies/{slug}").json()
            cdn_path = urlsplit(cdn_config["manifest_url"]).path
            assert cdn_path.startswith(f"/media/{source_id}/")
            origin_path = cdn_path.replace("/media/", "/edge-media/", 1)
            assert viewer.get(origin_path).status_code == 404
            edge = viewer.get(
                origin_path,
                headers={"X-Aperture-Origin-Secret": settings.cdn_origin_secret},
            )
            assert edge.status_code == 200 and edge.content == manifest
            segment_origin = origin_path.replace("master.m3u8", "360p/segment_00000.ts")
            edge_range = viewer.get(
                segment_origin,
                headers={
                    "X-Aperture-Origin-Secret": settings.cdn_origin_secret,
                    "Range": "bytes=0-3",
                },
            )
            assert edge_range.status_code == 206 and edge_range.content == segment[:4]
            tampered_parts = origin_path.split("/")
            replacement = "A" if tampered_parts[5][0] != "A" else "B"
            tampered_parts[5] = replacement + tampered_parts[5][1:]
            tampered = "/".join(tampered_parts)
            assert (
                viewer.get(
                    tampered,
                    headers={"X-Aperture-Origin-Secret": settings.cdn_origin_secret},
                ).status_code
                == 403
            )
        finally:
            (
                settings.media_delivery_mode,
                settings.cdn_public_origin,
                settings.cdn_signing_secret,
                settings.cdn_origin_secret,
            ) = original_delivery
        delivered = viewer.get(f"/playback/sources/{source_id}/media/master.m3u8")
        assert delivered.status_code == 200
        assert delivered.content == manifest
        ranged = viewer.get(
            f"/playback/sources/{source_id}/media/360p/segment_00000.ts",
            headers={"Range": "bytes=0-3"},
        )
        assert ranged.status_code == 206
        assert ranged.content == segment[:4]
        saved = viewer.put(
            f"/playback/sources/{source_id}/progress",
            json={"position_seconds": 12.5, "duration_seconds": 30},
        )
        assert saved.status_code == 200, saved.text
        assert saved.json()["position_seconds"] == 12.5
        assert viewer.get(f"/playback/movies/{slug}").json()["progress"]["position_seconds"] == 12.5

        progress_barrier = Barrier(4)

        def save_concurrent_progress(position: float) -> tuple[int, str]:
            with TestClient(app) as concurrent_viewer:
                login = concurrent_viewer.post(
                    "/auth/login",
                    json={"email": viewer_email, "password": "PlaybackViewerPassword123"},
                )
                assert login.status_code == 200, login.text
                progress_barrier.wait()
                response = concurrent_viewer.put(
                    f"/playback/sources/{source_id}/progress",
                    json={
                        "position_seconds": position,
                        "duration_seconds": 30,
                        "watched_seconds_delta": 1,
                    },
                )
                return response.status_code, response.text

        with ThreadPoolExecutor(max_workers=4) as executor:
            concurrent_results = list(
                executor.map(save_concurrent_progress, (13.0, 13.5, 14.0, 14.5))
            )
        assert all(status_code == 200 for status_code, _ in concurrent_results), concurrent_results
        first_completion = viewer.put(
            f"/playback/sources/{source_id}/progress",
            json={
                "position_seconds": 28,
                "duration_seconds": 30,
                "watched_seconds_delta": 15,
            },
        )
        assert first_completion.json()["completed"] is True
        unlocked_room = viewer.get(f"/cinephile/sources/{source_id}/after-credits")
        assert unlocked_room.status_code == 200, unlocked_room.text
        assert unlocked_room.json()["unlocked"] is True
        assert unlocked_room.json()["community_available"] is False
        assert unlocked_room.json()["modules"] == [
            {
                "id": after_credits_note.json()["id"],
                "kind": "ending_analysis",
                "title": "Ending analysis",
                "body": "The verified signal ending resolves the opening visual motif.",
                "source_label": "Administrator scene review",
            }
        ]
        second_profile = viewer.post("/profiles", json={"name": "Unspoiled viewer"})
        assert second_profile.status_code == 201, second_profile.text
        assert viewer.post(f"/profiles/{second_profile.json()['id']}/switch").status_code == 200
        isolated_room = viewer.get(f"/cinephile/sources/{source_id}/after-credits")
        assert isolated_room.json()["unlocked"] is False
        assert isolated_room.json()["modules"] == []
        assert viewer.post(f"/profiles/{primary_profile_id}/switch").status_code == 200
        prior_bookmark = viewer.post(
            f"/scene-intelligence/sources/{source_id}/bookmarks",
            json={"scene_id": scene_id, "timestamp_seconds": 4, "title": "Prior signal"},
        )
        prior_note = viewer.post(
            f"/scene-intelligence/sources/{source_id}/notes",
            json={
                "scene_id": scene_id,
                "timestamp_seconds": 4,
                "body": "Look again at the opening signal.",
            },
        )
        assert prior_bookmark.status_code == 201 and prior_note.status_code == 201
        unlocked_toolkit = viewer.get(
            f"/cinephile/sources/{source_id}", params={"timestamp": 30}
        ).json()
        assert unlocked_toolkit["edition_comparison_unlocked"] is True
        assert unlocked_toolkit["edition_comparisons"][0]["kind"] == "inserted_scene"
        assert "archive epilogue" in unlocked_toolkit["edition_comparisons"][0]["description"]
        unlocked_full = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 2, "mode": "full"},
        )
        assert unlocked_full.status_code == 200, unlocked_full.text
        assert unlocked_full.json()["completion_unlock"] is True
        assert any(item["kind"] == "scene" for item in unlocked_full.json()["facts"])
        rewatch_start = viewer.put(
            f"/playback/sources/{source_id}/progress",
            json={
                "position_seconds": 2,
                "duration_seconds": 30,
                "watched_seconds_delta": 2,
            },
        )
        assert rewatch_start.json()["completed"] is False
        rewatch_toolkit = viewer.get(
            f"/cinephile/sources/{source_id}", params={"timestamp": 4}
        ).json()
        assert rewatch_toolkit["rewatch"]["active"] is True
        assert rewatch_toolkit["rewatch"]["saved_scenes"][0]["title"] == "Prior signal"
        assert "opening signal" in rewatch_toolkit["rewatch"]["personal_notes"][0]["body"]
        assert rewatch_toolkit["rewatch"]["spoiler_aware_insights_available"] is True
        disabled = viewer.patch(
            f"/profiles/{primary_profile_id}",
            json={"preference": {"rewatch_intelligence_enabled": False}},
        )
        assert disabled.status_code == 200, disabled.text
        disabled_toolkit = viewer.get(
            f"/cinephile/sources/{source_id}", params={"timestamp": 4}
        ).json()
        assert disabled_toolkit["rewatch"]["enabled"] is False
        assert disabled_toolkit["rewatch"]["saved_scenes"] == []
        assert disabled_toolkit["rewatch"]["personal_notes"] == []
        rewatch_completion = viewer.put(
            f"/playback/sources/{source_id}/progress",
            json={
                "position_seconds": 29,
                "duration_seconds": 30,
                "watched_seconds_delta": 27,
            },
        )
        assert rewatch_completion.json()["completed"] is True
        rewatch_full = viewer.get(
            f"/scene-intelligence/sources/{source_id}/context",
            params={"timestamp": 2, "mode": "full"},
        )
        assert rewatch_full.status_code == 200
        passport = viewer.get("/passport")
        assert passport.status_code == 200, passport.text
        report = passport.json()
        assert report["generated_from"] == "viewing_activities"
        assert report["privacy"] == "private_to_profile"
        assert report["films_watched"] == 1
        assert report["completed_views"] == 2
        assert report["first_watches"] == 1
        assert report["rewatches"] == 1
        assert len(report["history"]) == 2
        creator = next(
            item for item in report["favorite_creators"] if item["person_id"] == str(director_id)
        )
        assert creator["roles"] == ["director"]
        assert creator["completed_views"] == 2
        year = datetime.now(UTC).year
        yearly = viewer.get(f"/passport?year={year}")
        assert yearly.status_code == 200
        assert yearly.json()["year"] == year
        assert year in yearly.json()["available_years"]

    for key in (
        f"{prefix}/master.m3u8",
        f"{prefix}/360p/index.m3u8",
        f"{prefix}/360p/segment_00000.ts",
        f"{prefix}/subtitles/track-0.vtt",
    ):
        client_s3.delete_object(Bucket=get_settings().s3_bucket, Key=key)
    with SessionLocal() as db:
        db.execute(delete(User).where(User.email == viewer_email))
        db.execute(delete(PlaybackSource).where(PlaybackSource.id == uuid.UUID(source_id)))
        db.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
        db.execute(delete(MediaAsset).where(MediaAsset.id == alternate_asset_id))
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(delete(Person).where(Person.id == director_id))
        db.execute(delete(Person).where(Person.id == actor_id))
        db.execute(delete(Character).where(Character.id == character_id))
        db.execute(delete(AuditLog).where(AuditLog.actor_id == admin_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        if english_locale_created:
            db.execute(delete(Language).where(Language.code == "en"))
        db.commit()
