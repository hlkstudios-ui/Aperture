import json
import logging
import mimetypes
import subprocess
import tempfile
import threading
import time
import uuid
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import redis
import sentry_sdk
from sqlalchemy import select, update
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import ProcessingJob, ProcessingState
from app.object_storage import s3_client
from app.observability import configure_observability, log_event
from app.processing_queue import PROCESSING_QUEUE

ALLOWED_VIDEO_CODECS = {"h264", "hevc", "vp8", "vp9", "av1"}
ALLOWED_SUBTITLE_CODECS = {"subrip", "ass", "ssa", "webvtt", "mov_text"}
configure_observability(get_settings())
logger = logging.getLogger("aperture.media_worker")


def command(arguments: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(arguments, check=True, capture_output=True, text=True)


def update_job(
    job_id: uuid.UUID, *, expected_lease_owner: uuid.UUID | None = None, **values: Any
) -> bool:
    with SessionLocal() as db:
        statement = select(ProcessingJob).where(ProcessingJob.id == job_id)
        if expected_lease_owner is not None:
            statement = statement.where(ProcessingJob.lease_owner == expected_lease_owner)
        job = db.scalar(statement)
        if job:
            for name, value in values.items():
                setattr(job, name, value)
            db.commit()
            return True
    return False


def renew_lease(job_id: uuid.UUID, lease_owner: uuid.UUID) -> bool:
    with SessionLocal() as db:
        result = db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id, ProcessingJob.lease_owner == lease_owner)
            .values(
                lease_expires_at=datetime.now(UTC)
                + timedelta(seconds=get_settings().media_job_lease_seconds)
            )
        )
        db.commit()
        return result.rowcount == 1


@contextmanager
def lease_heartbeat(job_id: uuid.UUID, lease_owner: uuid.UUID):
    stopped = threading.Event()

    def heartbeat() -> None:
        interval = max(10, get_settings().media_job_lease_seconds // 3)
        while not stopped.wait(interval):
            if not renew_lease(job_id, lease_owner):
                return

    thread = threading.Thread(target=heartbeat, daemon=True)
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join(timeout=2)


def recover_expired_jobs(limit: int = 25) -> list[uuid.UUID]:
    recovered: list[uuid.UUID] = []
    now = datetime.now(UTC)
    with SessionLocal() as db:
        jobs = list(
            db.scalars(
                select(ProcessingJob)
                .where(
                    ProcessingJob.state.in_(
                        [
                            ProcessingState.probing,
                            ProcessingState.processing,
                            ProcessingState.validating,
                        ]
                    ),
                    ProcessingJob.lease_expires_at < now,
                )
                .order_by(ProcessingJob.lease_expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.lease_owner = None
            job.lease_expires_at = None
            if job.attempts >= get_settings().media_job_max_attempts:
                job.state = ProcessingState.failed
                job.error_message = "Processing lease expired after maximum attempts"
                job.completed_at = now
            else:
                job.state = ProcessingState.queued
                job.progress_percent = 0
                job.error_message = "Recovered after worker lease expiry"
                recovered.append(job.id)
        db.commit()
    return recovered


def delete_prefix(prefix: str) -> None:
    client = s3_client()
    continuation = None
    while True:
        params: dict[str, Any] = {"Bucket": get_settings().s3_bucket, "Prefix": prefix}
        if continuation:
            params["ContinuationToken"] = continuation
        page = client.list_objects_v2(**params)
        objects = [{"Key": item["Key"]} for item in page.get("Contents", [])]
        if objects:
            client.delete_objects(Bucket=get_settings().s3_bucket, Delete={"Objects": objects})
        if not page.get("IsTruncated"):
            break
        continuation = page["NextContinuationToken"]


def probe(path: Path) -> dict[str, Any]:
    result = command(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
            str(path),
        ]
    )
    data = json.loads(result.stdout)
    video = next(
        (stream for stream in data.get("streams", []) if stream["codec_type"] == "video"), None
    )
    if not video or video.get("codec_name") not in ALLOWED_VIDEO_CODECS:
        raise ValueError(
            "Source must contain a supported H.264, HEVC, VP8, VP9, or AV1 video stream"
        )
    if not video.get("width") or not video.get("height"):
        raise ValueError("Source video dimensions are unavailable")
    unsupported_subtitles = [
        stream.get("codec_name")
        for stream in data.get("streams", [])
        if stream["codec_type"] == "subtitle"
        and stream.get("codec_name") not in ALLOWED_SUBTITLE_CODECS
    ]
    if unsupported_subtitles:
        raise ValueError(f"Unsupported subtitle codec: {unsupported_subtitles[0]}")
    return data


def stream_summary(stream: dict[str, Any]) -> dict[str, Any]:
    tags = stream.get("tags", {})
    return {
        "index": stream["index"],
        "codec": stream.get("codec_name"),
        "language": tags.get("language", "und"),
        "title": tags.get("title"),
        "channels": stream.get("channels"),
    }


def rendition_heights(source_height: int) -> list[int]:
    targets = [360, 480, 720, 1080]
    heights = [height for height in targets if height <= source_height]
    if not heights:
        heights = [source_height - (source_height % 2)]
    elif heights[-1] < source_height and source_height < 1080:
        heights.append(source_height - (source_height % 2))
    return sorted(set(height for height in heights if height >= 2))


def transcode_renditions(
    source: Path,
    output: Path,
    metadata: dict[str, Any],
    job_id: uuid.UUID,
    lease_owner: uuid.UUID,
) -> list[dict[str, Any]]:
    video = next(stream for stream in metadata["streams"] if stream["codec_type"] == "video")
    heights = rendition_heights(int(video["height"]))
    source_width = int(video["width"])
    source_height = int(video["height"])
    renditions: list[dict[str, Any]] = []
    bitrate = {360: 800, 480: 1400, 720: 2800, 1080: 5000}
    for index, height in enumerate(heights):
        directory = output / f"{height}p"
        directory.mkdir(parents=True)
        kbps = bitrate.get(height, max(350, round(height * 3.2)))
        width = round((source_width * height / source_height) / 2) * 2
        command(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                "0:v:0",
                "-map",
                "0:a:0?",
                "-vf",
                f"scale=-2:{height}",
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-maxrate",
                f"{kbps}k",
                "-bufsize",
                f"{kbps * 2}k",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-ac",
                "2",
                "-hls_time",
                "4",
                "-hls_playlist_type",
                "vod",
                "-hls_segment_filename",
                str(directory / "segment_%05d.ts"),
                str(directory / "index.m3u8"),
            ]
        )
        playlist = directory / "index.m3u8"
        if "#EXT-X-ENDLIST" not in playlist.read_text():
            raise ValueError(f"{height}p HLS playlist is incomplete")
        renditions.append(
            {
                "height": height,
                "width": width,
                "bandwidth": kbps * 1000,
                "state": "ready",
                "playlist": f"{height}p/index.m3u8",
            }
        )
        update_job(
            job_id,
            expected_lease_owner=lease_owner,
            progress_percent=20 + round(((index + 1) / len(heights)) * 45),
            rendition_status=renditions,
        )
    return renditions


def write_master(output: Path, renditions: list[dict[str, Any]]) -> Path:
    lines = ["#EXTM3U", "#EXT-X-VERSION:3"]
    for rendition in renditions:
        lines.extend(
            [
                f"#EXT-X-STREAM-INF:BANDWIDTH={rendition['bandwidth']},RESOLUTION={rendition['width']}x{rendition['height']}",
                rendition["playlist"],
            ]
        )
    master = output / "master.m3u8"
    master.write_text("\n".join(lines) + "\n")
    return master


def derived_images(source: Path, output: Path, duration: float) -> tuple[Path, Path]:
    thumbnail = output / "thumbnail.jpg"
    sprite = output / "preview-sprite.jpg"
    seek = str(max(0, min(duration / 2, duration - 0.1)))
    command(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            seek,
            "-i",
            str(source),
            "-frames:v",
            "1",
            "-vf",
            "scale=640:-2",
            str(thumbnail),
        ]
    )
    command(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(source),
            "-vf",
            "fps=1/5,scale=160:-2,tile=5x5:padding=2",
            "-frames:v",
            "1",
            str(sprite),
        ]
    )
    return thumbnail, sprite


def extract_subtitles(
    source: Path, output: Path, streams: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    records = []
    subtitle_dir = output / "subtitles"
    for ordinal, stream in enumerate(streams):
        subtitle_dir.mkdir(exist_ok=True)
        target = subtitle_dir / f"track-{ordinal}.vtt"
        command(
            [
                "ffmpeg",
                "-y",
                "-v",
                "error",
                "-i",
                str(source),
                "-map",
                f"0:{stream['index']}",
                "-c:s",
                "webvtt",
                str(target),
            ]
        )
        records.append(
            {**stream_summary(stream), "state": "ready", "key": f"subtitles/{target.name}"}
        )
    return records


def upload_outputs(output: Path, prefix: str) -> None:
    client = s3_client()
    for path in output.rglob("*"):
        if path.is_file():
            key = f"{prefix}/{path.relative_to(output).as_posix()}"
            media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            client.upload_file(
                str(path), get_settings().s3_bucket, key, ExtraArgs={"ContentType": media_type}
            )


def validate_outputs(output: Path, renditions: list[dict[str, Any]]) -> None:
    master = output / "master.m3u8"
    if not master.exists() or not master.read_text().startswith("#EXTM3U"):
        raise ValueError("Adaptive master manifest is invalid")
    for rendition in renditions:
        playlist = output / rendition["playlist"]
        segments = [
            line for line in playlist.read_text().splitlines() if line and not line.startswith("#")
        ]
        if not segments or not all((playlist.parent / segment).is_file() for segment in segments):
            raise ValueError(f"{rendition['height']}p rendition is missing segments")
    playback_probe = command(
        [
            "ffprobe",
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_streams",
            str(master),
        ]
    )
    streams = json.loads(playback_probe.stdout).get("streams", [])
    if not any(stream.get("codec_type") == "video" for stream in streams):
        raise ValueError("Adaptive manifest did not expose a playable video stream")


def process_job(job_id: uuid.UUID) -> None:
    started = time.perf_counter()
    lease_owner = uuid.uuid4()
    with SessionLocal() as db:
        job = db.scalar(
            select(ProcessingJob)
            .options(joinedload(ProcessingJob.asset))
            .where(ProcessingJob.id == job_id)
            .with_for_update(of=ProcessingJob, skip_locked=True)
        )
        if job is None or job.state is not ProcessingState.queued:
            return
        job.state = ProcessingState.probing
        job.progress_percent = 5
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error_message = None
        job.lease_owner = lease_owner
        job.lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=get_settings().media_job_lease_seconds
        )
        db.commit()
        asset_key = job.asset.storage_key
        asset_id = job.asset_id
    log_event(logger, "media.processing.started", job_id=str(job_id), asset_id=str(asset_id))
    prefix = f"processed/{asset_id}/{job_id}"
    try:
        with lease_heartbeat(job_id, lease_owner):
            delete_prefix(prefix)
            with tempfile.TemporaryDirectory(prefix="aperture-media-") as directory:
                root = Path(directory)
                source = root / "source"
                output = root / "output"
                output.mkdir()
                s3_client().download_file(get_settings().s3_bucket, asset_key, str(source))
                metadata = probe(source)
                video = next(
                    stream for stream in metadata["streams"] if stream["codec_type"] == "video"
                )
                duration = float(metadata["format"].get("duration") or video.get("duration") or 0)
                if duration <= 0:
                    raise ValueError("Source duration must be positive")
                audio = [
                    stream_summary(stream)
                    for stream in metadata["streams"]
                    if stream["codec_type"] == "audio"
                ]
                subtitle_streams = [
                    stream for stream in metadata["streams"] if stream["codec_type"] == "subtitle"
                ]
                chapters = [
                    {
                        "start": float(item["start_time"]),
                        "end": float(item["end_time"]),
                        "title": item.get("tags", {}).get("title"),
                    }
                    for item in metadata.get("chapters", [])
                ]
                summary = {
                    "format": metadata["format"].get("format_name"),
                    "video_codec": video.get("codec_name"),
                    "width": video["width"],
                    "height": video["height"],
                    "frame_rate": video.get("avg_frame_rate"),
                    "bit_rate": metadata["format"].get("bit_rate"),
                }
                update_job(
                    job_id,
                    expected_lease_owner=lease_owner,
                    state=ProcessingState.processing,
                    progress_percent=15,
                    source_metadata=summary,
                    audio_tracks=audio,
                    chapters=chapters,
                    duration_seconds=duration,
                )
                renditions = transcode_renditions(source, output, metadata, job_id, lease_owner)
                write_master(output, renditions)
                thumbnail, sprite = derived_images(source, output, duration)
                subtitles = extract_subtitles(source, output, subtitle_streams)
                update_job(
                    job_id,
                    expected_lease_owner=lease_owner,
                    state=ProcessingState.validating,
                    progress_percent=85,
                    subtitle_tracks=subtitles,
                )
                validate_outputs(output, renditions)
                upload_outputs(output, prefix)
                update_job(
                    job_id,
                    expected_lease_owner=lease_owner,
                    state=ProcessingState.ready,
                    progress_percent=100,
                    manifest_key=f"{prefix}/master.m3u8",
                    thumbnail_key=f"{prefix}/{thumbnail.name}",
                    sprite_key=f"{prefix}/{sprite.name}",
                    completed_at=datetime.now(UTC),
                    lease_owner=None,
                    lease_expires_at=None,
                )
                log_event(
                    logger,
                    "media.processing.completed",
                    job_id=str(job_id),
                    asset_id=str(asset_id),
                    duration_seconds=round(time.perf_counter() - started, 3),
                    rendition_count=len(renditions),
                )
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.exception(
            "media.processing.failed",
            extra={
                "structured": {
                    "event": "media.processing.failed",
                    "job_id": str(job_id),
                    "asset_id": str(asset_id),
                    "duration_seconds": round(time.perf_counter() - started, 3),
                }
            },
        )
        update_job(
            job_id,
            expected_lease_owner=lease_owner,
            state=ProcessingState.failed,
            error_message=str(exc)[:1000],
            completed_at=datetime.now(UTC),
            lease_owner=None,
            lease_expires_at=None,
        )


def run_worker(once: bool = False) -> None:
    client = redis.from_url(get_settings().redis_url)
    try:
        while True:
            for recovered_id in recover_expired_jobs():
                client.lpush(PROCESSING_QUEUE, str(recovered_id))
            item = client.brpop(PROCESSING_QUEUE, timeout=2 if once else 10)
            if item:
                process_job(uuid.UUID(item[1].decode()))
            if once:
                return
    finally:
        client.close()


if __name__ == "__main__":
    run_worker()
