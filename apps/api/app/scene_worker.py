import html
import logging
import re
import threading
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import redis
import sentry_sdk
from sqlalchemy import delete, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import joinedload

from app.config import get_settings
from app.db import SessionLocal
from app.models import PlaybackSource
from app.object_storage import s3_client
from app.observability import configure_observability, log_event
from app.scene_models import (
    EnrichmentJobState,
    ProvenanceKind,
    Scene,
    SceneIntelligenceJob,
    SceneSearchDocument,
    SceneSource,
    TranscriptCue,
)
from app.scene_queue import SCENE_QUEUE

TIMESTAMP = re.compile(
    r"(?:(?P<h>\d{2}):)?(?P<m>\d{2}):(?P<s>\d{2})[.,](?P<ms>\d{3})\s+-->\s+"
    r"(?:(?P<eh>\d{2}):)?(?P<em>\d{2}):(?P<es>\d{2})[.,](?P<ems>\d{3})"
)
configure_observability(get_settings())
logger = logging.getLogger("aperture.scene_worker")
TAG = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class Cue:
    start: float
    end: float
    text: str


def seconds(hours: str | None, minutes: str, value: str, milliseconds: str) -> float:
    return int(hours or 0) * 3600 + int(minutes) * 60 + int(value) + int(milliseconds) / 1000


def parse_webvtt(payload: str, duration: float) -> list[Cue]:
    if not payload.lstrip("\ufeff").startswith("WEBVTT"):
        raise ValueError("Subtitle evidence is not a WebVTT document")
    cues: list[Cue] = []
    blocks = re.split(r"\r?\n\s*\r?\n", payload.strip())
    for block in blocks[1:]:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        timing_index = next((index for index, line in enumerate(lines) if "-->" in line), None)
        if timing_index is None:
            continue
        match = TIMESTAMP.search(lines[timing_index])
        if match is None:
            raise ValueError("Subtitle evidence contains a malformed timestamp")
        start = seconds(match["h"], match["m"], match["s"], match["ms"])
        end = seconds(match["eh"], match["em"], match["es"], match["ems"])
        text = html.unescape(TAG.sub("", " ".join(lines[timing_index + 1 :])))
        text = " ".join(text.split())
        if not text:
            continue
        if start < 0 or end <= start or end > duration + 0.5:
            raise ValueError("Subtitle evidence contains an out-of-range timestamp")
        if cues and start < cues[-1].start:
            raise ValueError("Subtitle evidence timestamps are not ordered")
        cues.append(Cue(start, min(end, duration), text[:2000]))
    if not cues:
        raise ValueError("Subtitle evidence contains no usable cues")
    return cues


def boundaries(cues: list[Cue], duration: float) -> list[tuple[float, float, list[Cue]]]:
    groups: list[list[Cue]] = []
    current: list[Cue] = []
    for cue in cues:
        if current and (cue.start - current[-1].end >= 4 or cue.end - current[0].start >= 120):
            groups.append(current)
            current = []
        current.append(cue)
    if current:
        groups.append(current)
    return [
        (group[0].start, min(duration, group[-1].end), group)
        for group in groups
        if group[-1].end > group[0].start
    ]


def subtitle_key(playback: PlaybackSource, source: SceneSource) -> str | None:
    prefix = (playback.processing_job.manifest_key or "").rsplit("/", 1)[0]
    for track in playback.processing_job.subtitle_tracks:
        key = f"{prefix}/{track.get('key', '')}"
        if source.source_uri == f"storage://{key}":
            return key
    return None


def update_job(
    job_id: uuid.UUID, *, expected_lease_owner: uuid.UUID | None = None, **values
) -> bool:
    with SessionLocal() as db:
        statement = select(SceneIntelligenceJob).where(SceneIntelligenceJob.id == job_id)
        if expected_lease_owner is not None:
            statement = statement.where(SceneIntelligenceJob.lease_owner == expected_lease_owner)
        job = db.scalar(statement)
        if job is not None:
            for key, value in values.items():
                setattr(job, key, value)
            db.commit()
            return True
    return False


def renew_lease(job_id: uuid.UUID, lease_owner: uuid.UUID) -> bool:
    with SessionLocal() as db:
        result = db.execute(
            update(SceneIntelligenceJob)
            .where(
                SceneIntelligenceJob.id == job_id,
                SceneIntelligenceJob.lease_owner == lease_owner,
            )
            .values(
                lease_expires_at=datetime.now(UTC)
                + timedelta(seconds=get_settings().scene_job_lease_seconds)
            )
        )
        db.commit()
        return result.rowcount == 1


@contextmanager
def lease_heartbeat(job_id: uuid.UUID, lease_owner: uuid.UUID):
    stopped = threading.Event()

    def heartbeat() -> None:
        interval = max(10, get_settings().scene_job_lease_seconds // 3)
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
                select(SceneIntelligenceJob)
                .where(
                    SceneIntelligenceJob.state == EnrichmentJobState.running,
                    SceneIntelligenceJob.lease_expires_at < now,
                )
                .order_by(SceneIntelligenceJob.lease_expires_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        )
        for job in jobs:
            job.lease_owner = None
            job.lease_expires_at = None
            if job.attempts >= get_settings().scene_job_max_attempts:
                job.state = EnrichmentJobState.failed
                job.stage = "lease_attempts_exhausted"
                job.error_message = "Scene enrichment lease expired after maximum attempts"
                job.completed_at = now
            else:
                job.state = EnrichmentJobState.queued
                job.stage = "queued"
                job.progress_percent = 0
                job.error_message = "Recovered after worker lease expiry"
                recovered.append(job.id)
        db.commit()
    return recovered


def process_scene_job(job_id: uuid.UUID) -> None:
    started = time.perf_counter()
    lease_owner = uuid.uuid4()
    log_event(logger, "scene.processing.started", job_id=str(job_id))
    with SessionLocal() as db:
        job = db.scalar(
            select(SceneIntelligenceJob)
            .options(joinedload(SceneIntelligenceJob.version))
            .where(SceneIntelligenceJob.id == job_id)
            .with_for_update(of=SceneIntelligenceJob, skip_locked=True)
        )
        if job is None or job.state is not EnrichmentJobState.queued:
            return
        version = job.version
        playback = db.scalar(
            select(PlaybackSource)
            .options(joinedload(PlaybackSource.processing_job))
            .where(PlaybackSource.id == version.playback_source_id)
        )
        sources = list(db.scalars(select(SceneSource).where(SceneSource.version_id == version.id)))
        subtitle_sources = [
            (source, subtitle_key(playback, source))
            for source in sources
            if source.kind in {ProvenanceKind.subtitle, ProvenanceKind.transcript}
        ]
        subtitle_sources = [(source, key) for source, key in subtitle_sources if key]
        if not subtitle_sources:
            job.state = EnrichmentJobState.failed
            job.stage = "evidence_required"
            job.error_message = (
                "No licensed subtitle/transcript provenance matches an extracted playback track"
            )
            job.attempts += 1
            job.completed_at = datetime.now(UTC)
            db.commit()
            return
        source, key = subtitle_sources[0]
        duration = float(playback.processing_job.duration_seconds or 0)
        job.state = EnrichmentJobState.running
        job.stage = "ingesting_subtitles"
        job.progress_percent = 10
        job.attempts += 1
        job.started_at = datetime.now(UTC)
        job.error_message = None
        job.lease_owner = lease_owner
        job.lease_expires_at = datetime.now(UTC) + timedelta(
            seconds=get_settings().scene_job_lease_seconds
        )
        db.commit()
        version_id, source_id = version.id, source.id
    try:
        with lease_heartbeat(job_id, lease_owner):
            response = s3_client().get_object(Bucket=get_settings().s3_bucket, Key=key)
            raw = response["Body"].read()
            if len(raw) > 5 * 1024 * 1024:
                raise ValueError("Subtitle evidence exceeds the 5 MiB ingestion limit")
            cues = parse_webvtt(raw.decode("utf-8-sig"), duration)
            update_job(
                job_id,
                expected_lease_owner=lease_owner,
                stage="aligning_timestamps",
                progress_percent=35,
            )
            with SessionLocal() as db:
                owned_job = db.scalar(
                    select(SceneIntelligenceJob)
                    .where(
                        SceneIntelligenceJob.id == job_id,
                        SceneIntelligenceJob.lease_owner == lease_owner,
                    )
                    .with_for_update()
                )
                if owned_job is None:
                    return
                scenes = list(
                    db.scalars(
                        select(Scene).where(Scene.version_id == version_id).order_by(Scene.ordinal)
                    )
                )
                if not scenes:
                    for ordinal, (start, end, group) in enumerate(boundaries(cues, duration), 1):
                        summary = " ".join(cue.text for cue in group)[:1000]
                        db.add(
                            Scene(
                                version_id=version_id,
                                source_id=source_id,
                                ordinal=ordinal,
                                title=f"Scene {ordinal}",
                                summary=summary,
                                start_seconds=start,
                                end_seconds=end,
                                confidence=0.65,
                                manually_verified=False,
                            )
                        )
                    db.flush()
                    scenes = list(
                        db.scalars(
                            select(Scene)
                            .where(Scene.version_id == version_id)
                            .order_by(Scene.ordinal)
                        )
                    )
                db.execute(delete(TranscriptCue).where(TranscriptCue.version_id == version_id))
                db.execute(
                    delete(SceneSearchDocument).where(SceneSearchDocument.version_id == version_id)
                )
                scene_cues: dict[uuid.UUID, list[str]] = {scene.id: [] for scene in scenes}
                for cue in cues:
                    scene = next(
                        (
                            candidate
                            for candidate in scenes
                            if cue.start < candidate.end_seconds
                            and cue.end > candidate.start_seconds
                        ),
                        None,
                    )
                    db.add(
                        TranscriptCue(
                            version_id=version_id,
                            source_id=source_id,
                            scene_id=scene.id if scene else None,
                            start_seconds=cue.start,
                            end_seconds=cue.end,
                            text=cue.text,
                            speaker_label=None,
                            confidence=1,
                        )
                    )
                    if scene:
                        scene_cues[scene.id].append(cue.text)
                for scene in scenes:
                    text = " ".join([scene.title, scene.summary, *scene_cues[scene.id]])[:20000]
                    db.execute(
                        insert(SceneSearchDocument)
                        .values(scene_id=scene.id, version_id=version_id, searchable_text=text)
                        .on_conflict_do_update(
                            index_elements=[SceneSearchDocument.scene_id],
                            set_={
                                "version_id": version_id,
                                "searchable_text": text,
                                "updated_at": datetime.now(UTC),
                            },
                        )
                    )
                db.commit()
            update_job(
                job_id,
                expected_lease_owner=lease_owner,
                state=EnrichmentJobState.completed,
                stage="indexed",
                progress_percent=100,
                completed_at=datetime.now(UTC),
                lease_owner=None,
                lease_expires_at=None,
            )
            log_event(
                logger,
                "scene.processing.completed",
                job_id=str(job_id),
                duration_seconds=round(time.perf_counter() - started, 3),
            )
    except Exception as exc:
        sentry_sdk.capture_exception(exc)
        logger.exception(
            "scene.processing.failed",
            extra={
                "structured": {
                    "event": "scene.processing.failed",
                    "job_id": str(job_id),
                    "duration_seconds": round(time.perf_counter() - started, 3),
                }
            },
        )
        update_job(
            job_id,
            expected_lease_owner=lease_owner,
            state=EnrichmentJobState.failed,
            stage="failed",
            error_message=str(exc)[:1000],
            completed_at=datetime.now(UTC),
            lease_owner=None,
            lease_expires_at=None,
        )


def run_scene_worker(once: bool = False) -> None:
    client = redis.from_url(get_settings().redis_url)
    try:
        while True:
            for recovered_id in recover_expired_jobs():
                client.lpush(SCENE_QUEUE, str(recovered_id))
            item = client.brpop(SCENE_QUEUE, timeout=1 if once else 5)
            if item:
                process_scene_job(uuid.UUID(item[1].decode()))
            if once:
                return
    finally:
        client.close()


if __name__ == "__main__":
    run_scene_worker()
