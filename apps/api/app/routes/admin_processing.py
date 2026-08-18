import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import joinedload

from app.auth import DbSession, require_admin, require_trusted_origin
from app.models import (
    Admin,
    AssetState,
    AuditLog,
    MediaAsset,
    PlaybackSource,
    ProcessingJob,
    ProcessingState,
)
from app.processing_queue import enqueue_processing_job
from app.processing_schemas import ProcessingJobDetail, ProcessingJobResponse

router = APIRouter(
    prefix="/admin/processing",
    tags=["administrator processing"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def serialize(db: DbSession, job: ProcessingJob) -> ProcessingJobDetail:
    playback_source_id = db.scalar(
        select(PlaybackSource.id).where(PlaybackSource.processing_job_id == job.id)
    )
    return ProcessingJobDetail(
        **ProcessingJobResponse.model_validate(job).model_dump(),
        original_filename=job.asset.original_filename,
        playback_source_id=playback_source_id,
    )


def audit(db: DbSession, request: Request, admin: Admin, action: str, job: ProcessingJob) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"job_id": str(job.id), "asset_id": str(job.asset_id)},
        )
    )


@router.get("", response_model=list[ProcessingJobDetail])
def list_jobs(db: DbSession) -> list[ProcessingJobDetail]:
    jobs = db.scalars(
        select(ProcessingJob)
        .options(joinedload(ProcessingJob.asset))
        .order_by(ProcessingJob.created_at.desc())
    )
    return [serialize(db, job) for job in jobs]


@router.post("/{asset_id}", response_model=ProcessingJobDetail, status_code=status.HTTP_201_CREATED)
def start_processing(
    asset_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> ProcessingJobDetail:
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Media asset not found")
    if asset.state is not AssetState.completed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only completed uploads can be processed")
    existing = db.scalar(
        select(ProcessingJob)
        .options(joinedload(ProcessingJob.asset))
        .where(ProcessingJob.asset_id == asset_id)
    )
    if existing:
        raise HTTPException(status.HTTP_409_CONFLICT, "A processing job already exists")
    job = ProcessingJob(asset=asset, state=ProcessingState.queued)
    db.add(job)
    db.flush()
    audit(db, request, admin, "processing.queued", job)
    db.commit()
    enqueue_processing_job(str(job.id))
    return serialize(db, job)


@router.post("/{job_id}/retry", response_model=ProcessingJobDetail)
def retry_processing(
    job_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity
) -> ProcessingJobDetail:
    job = db.scalar(
        select(ProcessingJob)
        .options(joinedload(ProcessingJob.asset))
        .where(ProcessingJob.id == job_id)
    )
    if job is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Processing job not found")
    if job.state is not ProcessingState.failed:
        raise HTTPException(status.HTTP_409_CONFLICT, "Only failed jobs can be retried")
    job.state = ProcessingState.queued
    job.progress_percent = 0
    job.error_message = None
    job.completed_at = None
    audit(db, request, admin, "processing.retried", job)
    db.commit()
    enqueue_processing_job(str(job.id))
    return serialize(db, job)
