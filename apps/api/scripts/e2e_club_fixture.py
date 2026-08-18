"""Create or remove an isolated playable movie for watch-party acceptance tests."""

import hashlib
import json
import sys
from datetime import UTC, date, datetime

from sqlalchemy import delete, select

from app.auth import hash_password
from app.catalog_models import CatalogStatus, Movie
from app.config import get_settings
from app.db import SessionLocal
from app.media_worker import delete_prefix
from app.models import (
    Admin,
    AssetState,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    ProcessingState,
)
from app.object_storage import s3_client

PREFIX = "e2e-club-playback-"


def main() -> None:
    payload = json.load(sys.stdin)
    slug = payload["slug"]
    if get_settings().app_env not in {"development", "test"} or not slug.startswith(PREFIX):
        raise SystemExit("Club fixture helper is restricted to prefixed E2E records")
    with SessionLocal() as db:
        movie = db.scalar(select(Movie).where(Movie.slug == slug))
        admin_email = f"{slug}@example.com"
        if payload["action"] == "delete":
            if movie:
                source = db.scalar(
                    select(PlaybackSource).where(PlaybackSource.movie_id == movie.id)
                )
                job = db.get(ProcessingJob, source.processing_job_id) if source else None
                asset = db.get(MediaAsset, job.asset_id) if job else None
                if job:
                    delete_prefix(f"processed/{asset.id}/{job.id}")
                db.execute(delete(Movie).where(Movie.id == movie.id))
                if asset:
                    db.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
                db.execute(delete(Admin).where(Admin.email == admin_email))
                db.commit()
            print(json.dumps({"deleted": bool(movie)}))
            return
        if payload["action"] != "create":
            raise SystemExit("Unknown action")
        if movie:
            print(json.dumps({"id": str(movie.id), "title": movie.title}))
            return
        admin = Admin(email=admin_email, password_hash=hash_password("E2E-Club-Fixture-123aA"))
        db.add(admin)
        movie = Movie(
            title=payload["title"],
            slug=slug,
            short_description="An isolated watch-party acceptance fixture.",
            synopsis="Generated only for deterministic synchronized-playback acceptance.",
            release_date=date.today(),
            runtime_minutes=1,
            maturity_rating="G",
            status=CatalogStatus.published,
        )
        db.add(movie)
        db.flush()
        source_body = b"e2e club fixture"
        asset = MediaAsset(
            created_by_admin_id=admin.id,
            original_filename=f"{slug}.mp4",
            media_type="video/mp4",
            size_bytes=len(source_body),
            checksum_sha256=hashlib.sha256(source_body).hexdigest(),
            storage_key=f"e2e/{slug}/source.mp4",
            state=AssetState.completed,
            completed_at=datetime.now(UTC),
        )
        db.add(asset)
        db.flush()
        job = ProcessingJob(
            asset_id=asset.id,
            state=ProcessingState.ready,
            progress_percent=100,
            duration_seconds=60,
            manifest_key=f"processed/{asset.id}/fixture/master.m3u8",
            completed_at=datetime.now(UTC),
        )
        db.add(job)
        db.flush()
        db.add(PlaybackSource(processing_job_id=job.id, movie_id=movie.id))
        db.commit()
        s3_client().put_object(
            Bucket=get_settings().s3_bucket,
            Key=job.manifest_key,
            Body=b"#EXTM3U\n#EXT-X-VERSION:3\n#EXT-X-ENDLIST\n",
            ContentType="application/vnd.apple.mpegurl",
        )
        print(json.dumps({"id": str(movie.id), "title": movie.title}))


if __name__ == "__main__":
    main()
