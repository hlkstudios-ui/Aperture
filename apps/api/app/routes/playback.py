import base64
import hashlib
import hmac
import mimetypes
import time
import uuid
from datetime import UTC, datetime
from typing import Annotated

from botocore.exceptions import ClientError
from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, or_, select, text
from sqlalchemy.orm import joinedload

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.catalog_models import CatalogStatus, Edition, Episode, Movie, Season, Series
from app.config import get_settings
from app.geo import OptionalViewerCountry
from app.models import (
    DeviceSession,
    PlaybackSource,
    ProcessingJob,
    ProfilePreference,
    ViewingActivity,
    WatchProgress,
)
from app.object_storage import s3_client
from app.playback_schemas import PlaybackConfig, ProgressResponse, ProgressUpdate
from app.scheduling import availability_clause, territory_clause
from app.stream_limits import acquire_stream_lease, refresh_stream_lease

router = APIRouter(
    prefix="/playback",
    tags=["playback"],
    dependencies=[Depends(require_trusted_origin), Depends(require_customer_session)],
)
edge_router = APIRouter(prefix="/edge-media", tags=["private media origin"])
ViewerSession = Annotated[DeviceSession, Depends(require_customer_session)]


def source_query():
    return select(PlaybackSource).options(
        joinedload(PlaybackSource.processing_job).joinedload(ProcessingJob.asset)
    )


def playable_source(
    db: DbSession, source_id: uuid.UUID, country: str | None = None
) -> PlaybackSource:
    source = db.scalar(source_query().where(PlaybackSource.id == source_id))
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playback source was not found")
    if source.movie_id:
        visible = (
            db.scalar(
                select(Movie.id).where(
                    Movie.id == source.movie_id,
                    availability_clause(Movie, country=country),
                )
            )
            is not None
        )
    else:
        visible = (
            db.scalar(
                select(Episode.id)
                .join(Season, Episode.season_id == Season.id)
                .join(Series, Season.series_id == Series.id)
                .where(
                    Episode.id == source.episode_id,
                    Episode.status == CatalogStatus.published,
                    availability_clause(Series, country=country),
                )
            )
            is not None
        )
    if not visible:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Playback source was not found")
    if source.edition_id:
        edition = db.get(Edition, source.edition_id)
        now = datetime.now(UTC)
        if (
            edition is None
            or (edition.rights_start_at and edition.rights_start_at > now)
            or (edition.rights_end_at and edition.rights_end_at <= now)
            or db.scalar(
                select(Edition.id).where(
                    Edition.id == edition.id, territory_clause(Edition, country)
                )
            )
            is None
        ):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Playback source was not found")
    return source


def active_profile_id(session: DeviceSession) -> uuid.UUID:
    if session.active_profile_id is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Select a profile before playback")
    return session.active_profile_id


def cdn_signature(
    source_id: uuid.UUID,
    expires: int,
    session_id: uuid.UUID,
    country: str | None = None,
) -> str:
    secret = (get_settings().cdn_signing_secret or "").encode()
    payload = f"{source_id}:{expires}:{session_id}:{country or 'GLOBAL'}".encode()
    return base64.urlsafe_b64encode(hmac.digest(secret, payload, "sha256")).rstrip(b"=").decode()


def cdn_media_base(source_id: uuid.UUID, session_id: uuid.UUID, country: str | None) -> str:
    settings = get_settings()
    expires = int(time.time()) + settings.cdn_token_ttl_seconds
    territory = country or "GLOBAL"
    signature = cdn_signature(source_id, expires, session_id, country)
    origin = str(settings.cdn_public_origin).rstrip("/")
    return f"{origin}/media/{source_id}/{expires}/{session_id}/{territory}/{signature}"


def lock_progress_transaction(db: DbSession, profile_id: uuid.UUID, source_id: uuid.UUID) -> None:
    """Serialize the progress row and its viewing-activity ledger as one unit."""
    lock_key = int.from_bytes(
        hashlib.blake2b(f"{profile_id}:{source_id}".encode(), digest_size=8).digest(),
        byteorder="big",
        signed=True,
    )
    db.execute(text("SELECT pg_advisory_xact_lock(:lock_key)"), {"lock_key": lock_key})


def config_for(
    db: DbSession,
    source: PlaybackSource,
    session: DeviceSession,
    country: str | None = None,
) -> PlaybackConfig:
    source = playable_source(db, source.id, country)
    acquire_stream_lease(db, session, country)
    job = source.processing_job
    edition = db.get(Edition, source.edition_id) if source.edition_id else None
    if source.movie_id:
        movie = db.get(Movie, source.movie_id)
        title, subtitle = movie.title, None
        original_language_code = (
            edition.original_language_code if edition else movie.original_language_code
        )
    else:
        episode = db.get(Episode, source.episode_id)
        season = db.get(Season, episode.season_id)
        series = db.get(Series, season.series_id)
        title, subtitle = episode.title, f"{series.title} · S{season.number} E{episode.number}"
        original_language_code = (
            edition.original_language_code if edition else series.original_language_code
        )
        next_episode_id = db.scalar(
            select(Episode.id)
            .join(PlaybackSource, PlaybackSource.episode_id == Episode.id)
            .where(
                Episode.season_id == season.id,
                Episode.number > episode.number,
                Episode.status == CatalogStatus.published,
            )
            .order_by(Episode.number)
            .limit(1)
        )
    profile_id = active_profile_id(session)
    preference = db.get(ProfilePreference, profile_id)
    progress = db.scalar(
        select(WatchProgress).where(
            WatchProgress.profile_id == profile_id,
            WatchProgress.playback_source_id == source.id,
        )
    )
    settings = get_settings()
    if settings.media_delivery_mode == "cdn":
        media_base = cdn_media_base(source.id, session.id, country)
    else:
        origin = str(settings.api_origin).rstrip("/")
        media_base = f"{origin}/playback/sources/{source.id}/media"
    subtitle_tracks = [
        {**track, "url": f"{media_base}/{track['key']}"}
        for track in job.subtitle_tracks
        if track.get("key")
    ]
    return PlaybackConfig(
        source_id=source.id,
        movie_id=source.movie_id,
        episode_id=source.episode_id,
        edition_id=source.edition_id,
        original_language_code=original_language_code,
        preferred_audio_language=preference.preferred_audio_language if preference else None,
        preferred_subtitle_language=preference.preferred_subtitle_language if preference else None,
        preferred_secondary_subtitle_language=(
            preference.preferred_secondary_subtitle_language if preference else None
        ),
        subtitles_enabled=preference.subtitles_enabled if preference else False,
        caption_size=preference.caption_size if preference else "medium",
        caption_background=preference.caption_background if preference else "shadow",
        caption_position=preference.caption_position if preference else "bottom",
        title=title,
        subtitle=subtitle,
        manifest_url=f"{media_base}/master.m3u8",
        duration_seconds=job.duration_seconds or 0,
        qualities=job.rendition_status,
        audio_tracks=job.audio_tracks,
        subtitle_tracks=subtitle_tracks,
        intro=(source.intro_start_seconds, source.intro_end_seconds)
        if source.intro_start_seconds is not None and source.intro_end_seconds is not None
        else None,
        recap=(source.recap_start_seconds, source.recap_end_seconds)
        if source.recap_start_seconds is not None and source.recap_end_seconds is not None
        else None,
        credits_start_seconds=source.credits_start_seconds,
        next_episode_id=next_episode_id if source.episode_id else None,
        progress=ProgressResponse.model_validate(progress) if progress else None,
    )


@router.get("/movies/{slug}", response_model=PlaybackConfig)
def movie_config(
    slug: str, db: DbSession, session: ViewerSession, country: OptionalViewerCountry
) -> PlaybackConfig:
    now = datetime.now(UTC)
    source = db.scalar(
        source_query()
        .join(Movie, PlaybackSource.movie_id == Movie.id)
        .outerjoin(Edition, PlaybackSource.edition_id == Edition.id)
        .where(
            Movie.slug == slug,
            availability_clause(Movie, country=country),
            or_(
                PlaybackSource.edition_id.is_(None),
                and_(
                    or_(Edition.rights_start_at.is_(None), Edition.rights_start_at <= now),
                    or_(Edition.rights_end_at.is_(None), Edition.rights_end_at > now),
                ),
            ),
        )
        .order_by(Edition.is_default.desc().nullslast(), PlaybackSource.created_at)
        .limit(1)
    )
    if source is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "This movie is not ready for playback")
    return config_for(db, source, session, country)


@router.get("/episodes/{episode_id}", response_model=PlaybackConfig)
def episode_config(
    episode_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
) -> PlaybackConfig:
    source = playable_source(
        db,
        db.scalar(select(PlaybackSource.id).where(PlaybackSource.episode_id == episode_id))
        or uuid.uuid4(),
        country,
    )
    return config_for(db, source, session, country)


@router.get("/sources/{source_id}/media/{object_path:path}")
def media(
    source_id: uuid.UUID,
    object_path: str,
    db: DbSession,
    session: ViewerSession,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    country = refresh_stream_lease(session)
    source = playable_source(db, source_id, country)
    if not object_path or ".." in object_path.split("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid media path")
    prefix = source.processing_job.manifest_key.rsplit("/", 1)[0]
    key = f"{prefix}/{object_path}"
    params = {"Bucket": get_settings().s3_bucket, "Key": key}
    if range_header:
        params["Range"] = range_header
    try:
        response = s3_client().get_object(**params)
    except ClientError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media object was not found") from exc
    headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=30"}
    if response.get("ContentRange"):
        headers["Content-Range"] = response["ContentRange"]
    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(response["ContentLength"])
    return StreamingResponse(
        response["Body"].iter_chunks(chunk_size=1024 * 1024),
        status_code=status.HTTP_206_PARTIAL_CONTENT if range_header else status.HTTP_200_OK,
        media_type=mimetypes.guess_type(object_path)[0] or "application/octet-stream",
        headers=headers,
    )


@edge_router.get("/{source_id}/{expires}/{session_id}/{country}/{signature}/{object_path:path}")
def edge_media_origin(
    source_id: uuid.UUID,
    expires: int,
    session_id: uuid.UUID,
    country: str,
    signature: str,
    object_path: str,
    db: DbSession,
    origin_secret: Annotated[str | None, Header(alias="X-Aperture-Origin-Secret")] = None,
    range_header: Annotated[str | None, Header(alias="Range")] = None,
) -> StreamingResponse:
    settings = get_settings()
    if not hmac.compare_digest(origin_secret or "", settings.cdn_origin_secret or ""):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media object was not found")
    if expires < int(time.time()) or expires > int(time.time()) + settings.cdn_token_ttl_seconds:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Media grant expired")
    lease_country = None if country == "GLOBAL" else country
    if not hmac.compare_digest(
        signature, cdn_signature(source_id, expires, session_id, lease_country)
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Media grant is invalid")
    session = db.get(DeviceSession, session_id)
    now = datetime.now(UTC)
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or session.active_profile_id is None
    ):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Media grant is inactive")
    current_country = refresh_stream_lease(session)
    if current_country != lease_country:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Media grant region changed")
    source = playable_source(db, source_id, current_country)
    if not object_path or ".." in object_path.split("/"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid media path")
    prefix = source.processing_job.manifest_key.rsplit("/", 1)[0]
    params = {"Bucket": settings.s3_bucket, "Key": f"{prefix}/{object_path}"}
    if range_header:
        params["Range"] = range_header
    try:
        response = s3_client().get_object(**params)
    except ClientError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media object was not found") from exc
    headers = {
        "Accept-Ranges": "bytes",
        "Cache-Control": "public, max-age=31536000, immutable",
    }
    if response.get("ContentRange"):
        headers["Content-Range"] = response["ContentRange"]
    if response.get("ContentLength") is not None:
        headers["Content-Length"] = str(response["ContentLength"])
    return StreamingResponse(
        response["Body"].iter_chunks(chunk_size=1024 * 1024),
        status_code=206 if range_header else 200,
        media_type=mimetypes.guess_type(object_path)[0] or "application/octet-stream",
        headers=headers,
    )


@router.put("/sources/{source_id}/progress", response_model=ProgressResponse)
def update_progress(
    source_id: uuid.UUID,
    payload: ProgressUpdate,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
) -> WatchProgress:
    source = playable_source(db, source_id, country)
    profile_id = active_profile_id(session)
    lock_progress_transaction(db, profile_id, source_id)
    duration = source.processing_job.duration_seconds or payload.duration_seconds
    reported_duration = min(max(payload.duration_seconds, duration * 0.9), duration * 1.1)
    position = min(payload.position_seconds, reported_duration)
    percentage = min(100.0, position / reported_duration * 100)
    progress = db.scalar(
        select(WatchProgress).where(
            WatchProgress.profile_id == profile_id,
            WatchProgress.playback_source_id == source_id,
        )
    )
    previous_position = progress.position_seconds if progress else 0.0
    previous_completed = progress.completed if progress else False
    if progress is None:
        progress = WatchProgress(profile_id=profile_id, playback_source_id=source_id)
        db.add(progress)
    progress.position_seconds = position
    progress.duration_seconds = reported_duration
    progress.percentage = percentage
    progress.completed = percentage >= 90
    now = datetime.now(UTC)
    latest_activity = db.scalar(
        select(ViewingActivity)
        .where(
            ViewingActivity.profile_id == profile_id,
            ViewingActivity.playback_source_id == source_id,
        )
        .order_by(ViewingActivity.activity_number.desc())
        .limit(1)
    )
    starting_rewatch = bool(
        latest_activity and latest_activity.completed and previous_completed and percentage < 20
    )
    if latest_activity is None or starting_rewatch:
        activity_number = (latest_activity.activity_number + 1) if latest_activity else 1
        latest_activity = ViewingActivity(
            profile_id=profile_id,
            playback_source_id=source_id,
            activity_number=activity_number,
            is_rewatch=activity_number > 1,
            watched_seconds=0,
            completed=False,
            started_at=now,
            last_watched_at=now,
        )
        db.add(latest_activity)
    observed_delta = (
        payload.watched_seconds_delta
        if payload.watched_seconds_delta is not None
        else max(0.0, min(60.0, position - previous_position))
    )
    latest_activity.watched_seconds = min(
        reported_duration, latest_activity.watched_seconds + observed_delta
    )
    latest_activity.last_watched_at = now
    if percentage >= 90 and not latest_activity.completed:
        latest_activity.completed = True
        latest_activity.completed_at = now
    progress.last_watched_at = now
    db.commit()
    return progress
