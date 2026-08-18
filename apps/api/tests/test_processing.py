import hashlib
import subprocess
import tempfile
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import delete

from app.auth import hash_password
from app.config import get_settings
from app.db import SessionLocal
from app.media_worker import delete_prefix, process_job, recover_expired_jobs, update_job
from app.models import (
    Admin,
    AssetState,
    MediaAsset,
    ProcessingJob,
    ProcessingState,
)
from app.object_storage import s3_client


def test_media_worker_builds_and_validates_adaptive_hls() -> None:
    token = uuid.uuid4()
    source_key = f"source/{token}/{token}.mp4"
    output_prefix = ""
    admin_id = None
    asset_id = None
    with tempfile.TemporaryDirectory(prefix="aperture-processing-test-") as directory:
        source = Path(directory) / "fixture.mp4"
        subprocess.run(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "testsrc2=size=640x360:rate=24",
                "-f",
                "lavfi",
                "-i",
                "sine=frequency=440:sample_rate=48000",
                "-t",
                "3",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-shortest",
                str(source),
            ],
            check=True,
        )
        content = source.read_bytes()
        checksum = hashlib.sha256(content).hexdigest()
        s3_client().upload_file(str(source), get_settings().s3_bucket, source_key)
        with SessionLocal() as db:
            admin = Admin(
                email=f"processing-{token}@example.com",
                password_hash=hash_password("AdministratorPass123"),
            )
            db.add(admin)
            db.flush()
            asset = MediaAsset(
                created_by_admin_id=admin.id,
                original_filename=f"processing-{token}.mp4",
                media_type="video/mp4",
                size_bytes=len(content),
                checksum_sha256=checksum,
                storage_key=source_key,
                state=AssetState.completed,
                completed_at=datetime.now(UTC),
            )
            db.add(asset)
            db.flush()
            job = ProcessingJob(asset=asset, state=ProcessingState.queued)
            db.add(job)
            db.commit()
            job_id = job.id
            asset_id = asset.id
            admin_id = admin.id
        process_job(job_id)
        with SessionLocal() as db:
            job = db.get(ProcessingJob, job_id)
            assert job is not None
            assert job.state is ProcessingState.ready, job.error_message
            assert job.progress_percent == 100
            assert job.duration_seconds and 2.5 < job.duration_seconds < 3.5
            assert job.source_metadata["video_codec"] == "h264"
            assert job.audio_tracks[0]["codec"] == "aac"
            assert job.rendition_status
            assert job.manifest_key and job.thumbnail_key and job.sprite_key
            output_prefix = job.manifest_key.rsplit("/", 1)[0]
            master = (
                s3_client()
                .get_object(Bucket=get_settings().s3_bucket, Key=job.manifest_key)["Body"]
                .read()
                .decode()
            )
            assert master.startswith("#EXTM3U")
            assert "360p/index.m3u8" in master
            s3_client().head_object(Bucket=get_settings().s3_bucket, Key=job.thumbnail_key)
            s3_client().head_object(Bucket=get_settings().s3_bucket, Key=job.sprite_key)

    s3_client().delete_object(Bucket=get_settings().s3_bucket, Key=source_key)
    if output_prefix:
        delete_prefix(output_prefix)
    with SessionLocal() as db:
        if asset_id:
            db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))
        if admin_id:
            db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()


def test_expired_processing_lease_recovers_and_rejects_stale_owner() -> None:
    token = uuid.uuid4()
    old_owner = uuid.uuid4()
    admin_id = asset_id = job_id = None
    with SessionLocal() as db:
        admin = Admin(
            email=f"lease-{token}@example.com",
            password_hash=hash_password("AdministratorPass123"),
        )
        db.add(admin)
        db.flush()
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename="lease.mp4",
            media_type="video/mp4",
            size_bytes=1,
            checksum_sha256=hashlib.sha256(b"x").hexdigest(),
            storage_key=f"lease/{token}.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        job = ProcessingJob(
            asset=asset,
            state=ProcessingState.processing,
            attempts=1,
            lease_owner=old_owner,
            lease_expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        db.add(job)
        db.commit()
        admin_id, asset_id, job_id = admin.id, asset.id, job.id

    assert recover_expired_jobs() == [job_id]
    assert not update_job(
        job_id,
        expected_lease_owner=old_owner,
        state=ProcessingState.ready,
        progress_percent=100,
    )
    with SessionLocal() as db:
        job = db.get(ProcessingJob, job_id)
        assert job.state is ProcessingState.queued
        assert job.progress_percent == 0
        assert job.lease_owner is None and job.lease_expires_at is None
        db.execute(delete(MediaAsset).where(MediaAsset.id == asset_id))
        db.execute(delete(Admin).where(Admin.id == admin_id))
        db.commit()
