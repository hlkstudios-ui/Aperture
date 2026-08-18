import hashlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.db import SessionLocal
from app.models import Admin, AssetState, MediaAsset, PlaybackSource, ProcessingJob, ProcessingState
from app.scene_models import (
    EnrichmentJobState,
    IntelligenceVersionState,
    SceneIntelligenceJob,
    SceneIntelligenceVersion,
)
from app.scene_worker import boundaries, parse_webvtt, recover_expired_jobs, update_job


def test_webvtt_ingestion_aligns_and_segments_without_inventing_metadata() -> None:
    cues = parse_webvtt(
        """WEBVTT

00:00:00.000 --> 00:00:02.000
The beacon is dark.

00:00:02.100 --> 00:00:04.000
Wait for the signal.

00:00:09.000 --> 00:00:11.000
There it is.

00:11.100 --> 00:12.000
Short WebVTT timestamps are valid too.
""",
        12,
    )
    assert [(cue.start, cue.end, cue.text) for cue in cues] == [
        (0, 2, "The beacon is dark."),
        (2.1, 4, "Wait for the signal."),
        (9, 11, "There it is."),
        (11.1, 12, "Short WebVTT timestamps are valid too."),
    ]
    scenes = boundaries(cues, 12)
    assert [(start, end, len(group)) for start, end, group in scenes] == [
        (0, 4, 2),
        (9, 12, 2),
    ]


@pytest.mark.parametrize(
    "payload,error",
    [
        ("not captions", "not a WebVTT"),
        ("WEBVTT\n\n00:00:04.000 --> nonsense\nBad", "malformed timestamp"),
        (
            "WEBVTT\n\n00:00:11.000 --> 00:00:13.000\nOutside",
            "out-of-range timestamp",
        ),
    ],
)
def test_webvtt_ingestion_rejects_malformed_evidence(payload: str, error: str) -> None:
    with pytest.raises(ValueError, match=error):
        parse_webvtt(payload, 12)


def test_scene_expired_lease_recovery_rejects_stale_owner(monkeypatch) -> None:
    token = uuid.uuid4()
    old_owner = uuid.uuid4()
    with SessionLocal() as db:
        admin = Admin(
            email=f"scene-lease-{token}@example.com",
            password_hash=hash_password("AdministratorPass123"),
        )
        movie = Movie(
            title="Scene lease fixture",
            slug=f"scene-lease-{token}",
            short_description="Lease fixture.",
            synopsis="Lease fixture.",
            runtime_minutes=1,
            status=CatalogStatus.published,
        )
        db.add_all([admin, movie])
        db.flush()
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="scene-lease.mp4",
            media_type="video/mp4",
            size_bytes=1,
            checksum_sha256=hashlib.sha256(b"x").hexdigest(),
            storage_key=f"scene-lease/{token}.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        processing = ProcessingJob(
            asset=asset,
            state=ProcessingState.ready,
            duration_seconds=60,
            manifest_key=f"scene-lease/{token}/master.m3u8",
        )
        playback = PlaybackSource(processing_job=processing, movie_id=movie.id)
        db.add_all([asset, processing, playback])
        db.flush()
        version = SceneIntelligenceVersion(
            playback_source_id=playback.id,
            number=1,
            state=IntelligenceVersionState.draft,
            created_by_admin_id=admin.id,
        )
        job = SceneIntelligenceJob(
            version=version,
            state=EnrichmentJobState.running,
            stage="indexing",
            attempts=1,
            created_by_admin_id=admin.id,
            lease_owner=old_owner,
            lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(job)
        db.commit()
        admin_id, asset_id, movie_id, job_id = admin.id, asset.id, movie.id, job.id

    assert recover_expired_jobs() == [job_id]
    assert not update_job(
        job_id,
        expected_lease_owner=old_owner,
        state=EnrichmentJobState.completed,
    )
    with SessionLocal() as db:
        job = db.get(SceneIntelligenceJob, job_id)
        assert job.state is EnrichmentJobState.queued
        assert job.stage == "queued"
        assert job.lease_owner is None and job.lease_expires_at is None
        job.state = EnrichmentJobState.running
        job.attempts = 3
        job.lease_owner = uuid.uuid4()
        job.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()

    assert recover_expired_jobs() == []
    with SessionLocal() as db:
        job = db.get(SceneIntelligenceJob, job_id)
        assert job.state is EnrichmentJobState.failed
        assert job.stage == "lease_attempts_exhausted"
        db.execute(delete(Movie).where(Movie.id == movie_id))
        db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
