from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Edition, Episode, Movie
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
    job = db.get(ProcessingJob, payload.processing_job_id)
    if job is None or job.state is not ProcessingState.ready or not job.manifest_key:
        raise HTTPException(status.HTTP_409_CONFLICT, "Processing job must be Ready")
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
    duration = job.duration_seconds or 0
    markers = [
        payload.intro_end_seconds,
        payload.recap_end_seconds,
        payload.credits_start_seconds,
    ]
    if any(marker is not None and marker > duration for marker in markers):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Skip markers exceed duration")
    source = PlaybackSource(**payload.model_dump())
    db.add(source)
    db.flush()
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action="playback.source.assigned",
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"source_id": str(source.id), "processing_job_id": str(job.id)},
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "The job or title already has a playback source"
        ) from exc
    return source
