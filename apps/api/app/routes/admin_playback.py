from typing import Annotated
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Edition, Episode, Movie
from app.config import get_settings
from app.models import Admin, AuditLog, PlaybackSource, ProcessingJob, ProcessingState
from app.playback_schemas import PlaybackSourceCreate, PlaybackSourceResponse

router = APIRouter(
    prefix="/admin/playback",
    tags=["administrator playback"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


@router.get("/sources", response_model=list[PlaybackSourceResponse])
def list_sources(db: DbSession) -> list[PlaybackSource]:
    return list(db.scalars(select(PlaybackSource).order_by(PlaybackSource.created_at.desc())))


@router.post("/sources", response_model=PlaybackSourceResponse, status_code=status.HTTP_201_CREATED)
def create_source(
    payload: PlaybackSourceCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> PlaybackSource:
    job = db.get(ProcessingJob, payload.processing_job_id) if payload.processing_job_id else None
    if payload.processing_job_id and (
        job is None or job.state is not ProcessingState.ready or not job.manifest_key
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Processing job must be Ready")
    if payload.external_manifest_url:
        configured_origins = {
            value.strip().rstrip("/")
            for value in get_settings().media_source_origins.split(",")
            if value.strip()
        }
        parsed = urlsplit(str(payload.external_manifest_url))
        source_origin = f"{parsed.scheme}://{parsed.netloc}"
        if source_origin not in configured_origins:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "CDN origin is not approved. Add it to MEDIA_SOURCE_ORIGINS and restart Studio.",
            )
    parent = db.get(Movie if payload.movie_id else Episode, payload.movie_id or payload.episode_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Assigned title was not found")
    if payload.edition_id:
        edition = db.get(Edition, payload.edition_id)
        if (
            edition is None
            or edition.movie_id != payload.movie_id
            or edition.episode_id != payload.episode_id
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Playback edition must belong to the assigned title",
            )
    duration = (job.duration_seconds if job else payload.duration_seconds) or 0
    markers = [
        payload.intro_end_seconds,
        payload.recap_end_seconds,
        payload.credits_start_seconds,
    ]
    if any(marker is not None and marker > duration for marker in markers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Skip markers exceed duration")
    values = payload.model_dump()
    if payload.external_manifest_url is not None:
        values["external_manifest_url"] = str(payload.external_manifest_url)
    elif job is not None:
        values["is_active"] = True
    source = PlaybackSource(**values)
    db.add(source)
    db.flush()
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action="playback.source.assigned",
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={
                "source_id": str(source.id),
                "origin": "processed" if job else "external_cdn",
                "processing_job_id": str(job.id) if job else None,
                "host": (
                    payload.external_manifest_url.host
                    if payload.external_manifest_url
                    else None
                ),
            },
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The job, title, or edition already has a playback source"
        ) from exc
    return source
