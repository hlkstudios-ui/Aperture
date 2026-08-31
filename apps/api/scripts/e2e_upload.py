"""Restricted upload inspection/cleanup for local Playwright acceptance tests."""

import json
import sys

from e2e_guard import require_e2e_test_environment
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.media_worker import delete_prefix
from app.models import MediaAsset, ProcessingJob
from app.object_storage import s3_client

PREFIX = "e2e-upload-"


def main() -> None:
    settings = require_e2e_test_environment()
    payload = json.load(sys.stdin)
    filename = payload["filename"]
    if not filename.startswith(PREFIX):
        raise SystemExit("E2E upload helper is restricted to prefixed browser-test fixtures")
    with SessionLocal() as db:
        asset = db.scalar(select(MediaAsset).where(MediaAsset.original_filename == filename))
        if payload["action"] == "inspect":
            if asset is None:
                raise SystemExit("Asset was not found")
            head = s3_client().head_object(Bucket=settings.s3_bucket, Key=asset.storage_key)
            print(
                json.dumps(
                    {
                        "id": str(asset.id),
                        "state": asset.state.value,
                        "size_bytes": asset.size_bytes,
                        "checksum_sha256": asset.checksum_sha256,
                        "storage_key": asset.storage_key,
                        "object_size": head["ContentLength"],
                        "object_checksum": head.get("Metadata", {}).get("sha256"),
                    }
                )
            )
            return
        if payload["action"] == "inspect_processing":
            if asset is None:
                raise SystemExit("Asset was not found")
            job = db.scalar(select(ProcessingJob).where(ProcessingJob.asset_id == asset.id))
            if job is None:
                raise SystemExit("Processing job was not found")
            manifest = None
            if job.manifest_key:
                manifest = (
                    s3_client()
                    .get_object(Bucket=settings.s3_bucket, Key=job.manifest_key)["Body"]
                    .read()
                    .decode()
                )
            print(
                json.dumps(
                    {
                        "state": job.state.value,
                        "progress_percent": job.progress_percent,
                        "duration_seconds": job.duration_seconds,
                        "source_metadata": job.source_metadata,
                        "rendition_status": job.rendition_status,
                        "audio_tracks": job.audio_tracks,
                        "subtitle_tracks": job.subtitle_tracks,
                        "manifest_key": job.manifest_key,
                        "manifest": manifest,
                        "thumbnail_key": job.thumbnail_key,
                        "sprite_key": job.sprite_key,
                        "error_message": job.error_message,
                    }
                )
            )
            return
        if payload["action"] == "delete":
            if asset:
                job = db.scalar(select(ProcessingJob).where(ProcessingJob.asset_id == asset.id))
                if job:
                    delete_prefix(f"processed/{asset.id}/{job.id}")
                s3_client().delete_object(Bucket=settings.s3_bucket, Key=asset.storage_key)
                db.execute(delete(MediaAsset).where(MediaAsset.id == asset.id))
                db.commit()
            print(json.dumps({"deleted": bool(asset)}))
            return
    raise SystemExit("Unknown action")


if __name__ == "__main__":
    main()
