import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.community_models import (
    CommunityActivity,
    CommunityActivityKind,
    CommunityReport,
    ModerationAction,
    ModerationStatus,
    ReportStatus,
    Review,
)
from app.community_schemas import (
    ModerationDecision,
    ModerationQueueResponse,
    ReportDecision,
    ReportResponse,
)
from app.curation_models import Collection, CollectionKind
from app.curation_service import collection_response, load_collection
from app.models import Admin, AuditLog
from app.routes.community import review_response

router = APIRouter(
    prefix="/admin/community",
    tags=["administrator community moderation"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def audit(db, request: Request, admin: Admin, action: str, target_id: uuid.UUID):
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"target_id": str(target_id)},
        )
    )


@router.get("/queue", response_model=ModerationQueueResponse)
def moderation_queue(db: DbSession) -> ModerationQueueResponse:
    reviews = list(
        db.scalars(
            select(Review)
            .where(Review.status == ModerationStatus.pending)
            .order_by(Review.created_at)
        )
    )
    reports = list(
        db.scalars(
            select(CommunityReport)
            .where(CommunityReport.status.in_([ReportStatus.open, ReportStatus.reviewing]))
            .order_by(CommunityReport.created_at)
        )
    )
    return ModerationQueueResponse(
        reviews=[review_response(db, review) for review in reviews],
        lists=[
            collection_response(db, load_collection(db, collection.id))
            for collection in db.scalars(
                select(Collection)
                .where(
                    Collection.kind == CollectionKind.user_list,
                    Collection.visibility.in_(["unlisted", "public"]),
                    Collection.moderation_status == "pending",
                )
                .order_by(Collection.updated_at)
            )
        ],
        reports=[ReportResponse.model_validate(report, from_attributes=True) for report in reports],
    )


@router.post("/reviews/{review_id}/decision", response_model=ModerationQueueResponse)
def decide_review(
    review_id: uuid.UUID,
    payload: ModerationDecision,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ModerationQueueResponse:
    review = db.get(Review, review_id)
    if review is None:
        raise HTTPException(404, "Review was not found")
    if payload.status == ModerationStatus.pending:
        raise HTTPException(422, "A moderation decision cannot return content to pending")
    was_approved = review.status == ModerationStatus.approved
    review.status = payload.status
    review.moderation_note = payload.reason
    review.published_at = datetime.now(UTC) if payload.status == ModerationStatus.approved else None
    if payload.status == ModerationStatus.approved and not was_approved:
        db.add(
            CommunityActivity(
                actor_profile_id=review.profile_id,
                kind=CommunityActivityKind.review_published,
                review_id=review.id,
            )
        )
    db.add(
        ModerationAction(
            admin_id=admin.id,
            review_id=review.id,
            action=payload.status.value,
            reason=payload.reason,
        )
    )
    audit(db, request, admin, "community.review.moderated", review.id)
    db.commit()
    return moderation_queue(db)


@router.post("/lists/{collection_id}/decision", response_model=ModerationQueueResponse)
def decide_list(
    collection_id: uuid.UUID,
    payload: ModerationDecision,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ModerationQueueResponse:
    collection = db.get(Collection, collection_id)
    if collection is None or collection.kind != CollectionKind.user_list:
        raise HTTPException(404, "List was not found")
    if payload.status == ModerationStatus.pending:
        raise HTTPException(422, "A moderation decision cannot return content to pending")
    was_approved = collection.moderation_status == ModerationStatus.approved.value
    collection.moderation_status = payload.status.value
    if payload.status == ModerationStatus.approved and not was_approved:
        db.add(
            CommunityActivity(
                actor_profile_id=collection.owner_profile_id,
                kind=CommunityActivityKind.list_published,
                collection_id=collection.id,
            )
        )
    db.add(
        ModerationAction(
            admin_id=admin.id,
            collection_id=collection.id,
            action=payload.status.value,
            reason=payload.reason,
        )
    )
    audit(db, request, admin, "community.list.moderated", collection.id)
    db.commit()
    return moderation_queue(db)


@router.post("/reports/{report_id}/decision", response_model=ModerationQueueResponse)
def decide_report(
    report_id: uuid.UUID,
    payload: ReportDecision,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ModerationQueueResponse:
    report = db.get(CommunityReport, report_id)
    if report is None:
        raise HTTPException(404, "Report was not found")
    if payload.status not in {ReportStatus.resolved, ReportStatus.dismissed}:
        raise HTTPException(422, "Choose a terminal report decision")
    report.status = payload.status
    report.resolved_at = datetime.now(UTC)
    db.add(
        ModerationAction(
            admin_id=admin.id,
            report_id=report.id,
            action=payload.status.value,
            reason=payload.reason,
        )
    )
    audit(db, request, admin, "community.report.moderated", report.id)
    db.commit()
    return moderation_queue(db)
