import hashlib
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, inspect, or_, select, update

from app.admin_support_schemas import (
    CustomerDeletionRequest,
    SessionRevocation,
    SupportSubscription,
    SupportSubscriptionList,
    SupportUserList,
    SupportUserSummary,
    UserStateUpdate,
)
from app.auth import DbSession, require_admin, require_trusted_origin
from app.community_models import (
    CommunityActivity,
    CommunityReport,
    ProfileFollow,
    ProfileSafetyRelation,
    Rating,
    Review,
)
from app.config import get_settings
from app.curation_models import Collection, JourneyProgress
from app.models import (
    Admin,
    AnalyticsEvent,
    AskMovieLog,
    AssetState,
    AuditLog,
    DeviceSession,
    Entitlement,
    MediaAsset,
    PaymentReference,
    Plan,
    ProcessingJob,
    Profile,
    ProfilePreference,
    SceneBookmark,
    SceneNote,
    Subscription,
    User,
    ViewingActivity,
    WatchProgress,
)
from app.object_storage import s3_client

router = APIRouter(
    prefix="/admin/support",
    tags=["administrator support"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def audit(db: DbSession, request: Request, admin: Admin, action: str, detail: dict) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="success",
            ip_address=request.client.host if request.client else None,
            detail=detail,
        )
    )


def user_or_404(db: DbSession, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Customer not found")
    return user


SENSITIVE_EXPORT_FIELDS = {
    "password_hash",
    "token_hash",
    "invite_token_hash",
    "access_token_hash",
    "provider_customer_ref",
    "provider_subscription_ref",
    "external_reference",
}


def export_row(row) -> dict:
    return {
        column.key: getattr(row, column.key)
        for column in inspect(row).mapper.column_attrs
        if column.key not in SENSITIVE_EXPORT_FIELDS
    }


def profile_export(db: DbSession, profile: Profile) -> dict:
    owned_models = (
        WatchProgress,
        ViewingActivity,
        SceneBookmark,
        SceneNote,
        AskMovieLog,
        AnalyticsEvent,
        JourneyProgress,
        Rating,
        Review,
        CommunityReport,
    )
    result = export_row(profile)
    preference = db.get(ProfilePreference, profile.id)
    result["preference"] = export_row(preference) if preference else None
    records = {}
    for model in owned_models:
        owner_column = getattr(model, "profile_id", None)
        if owner_column is None:
            owner_column = model.reporter_profile_id
        records[model.__tablename__] = [
            export_row(row) for row in db.scalars(select(model).where(owner_column == profile.id))
        ]
    records["collections"] = [
        export_row(row)
        for row in db.scalars(select(Collection).where(Collection.owner_profile_id == profile.id))
    ]
    records["follows"] = [
        export_row(row)
        for row in db.scalars(
            select(ProfileFollow).where(
                or_(
                    ProfileFollow.follower_profile_id == profile.id,
                    ProfileFollow.followed_profile_id == profile.id,
                )
            )
        )
    ]
    records["safety_relations"] = [
        export_row(row)
        for row in db.scalars(
            select(ProfileSafetyRelation).where(
                or_(
                    ProfileSafetyRelation.actor_profile_id == profile.id,
                    ProfileSafetyRelation.target_profile_id == profile.id,
                )
            )
        )
    ]
    records["community_activity"] = [
        export_row(row)
        for row in db.scalars(
            select(CommunityActivity).where(
                or_(
                    CommunityActivity.actor_profile_id == profile.id,
                    CommunityActivity.target_profile_id == profile.id,
                )
            )
        )
    ]
    result["records"] = records
    return result


def summarize_user(db: DbSession, user: User) -> SupportUserSummary:
    now = datetime.now(UTC)
    profile_count = (
        db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user.id)) or 0
    )
    session_count = (
        db.scalar(
            select(func.count())
            .select_from(DeviceSession)
            .where(
                DeviceSession.user_id == user.id,
                DeviceSession.revoked_at.is_(None),
                DeviceSession.expires_at > now,
            )
        )
        or 0
    )
    subscription = db.execute(
        select(Subscription, Plan)
        .join(Plan)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.updated_at.desc())
        .limit(1)
    ).first()
    return SupportUserSummary(
        id=user.id,
        email=user.email,
        is_active=user.is_active,
        created_at=user.created_at,
        profile_count=profile_count,
        active_session_count=session_count,
        subscription_status=subscription[0].status.value if subscription else None,
        plan_name=subscription[1].name if subscription else None,
    )


@router.get("/users", response_model=SupportUserList)
def list_users(
    db: DbSession,
    _: AdminIdentity,
    q: str = Query(default="", max_length=320),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    filters = [User.email.ilike(f"%{q.strip()}%")] if q.strip() else []
    total = db.scalar(select(func.count()).select_from(User).where(*filters)) or 0
    users = db.scalars(
        select(User).where(*filters).order_by(User.created_at.desc()).offset(offset).limit(limit)
    ).all()
    return SupportUserList(items=[summarize_user(db, user) for user in users], total=total)


@router.get("/users/{user_id}")
def get_user(user_id: uuid.UUID, db: DbSession, _: AdminIdentity):
    user = user_or_404(db, user_id)
    summary = summarize_user(db, user).model_dump(mode="json")
    profiles = db.scalars(
        select(Profile).where(Profile.user_id == user.id).order_by(Profile.created_at)
    ).all()
    sessions = db.scalars(
        select(DeviceSession)
        .where(DeviceSession.user_id == user.id)
        .order_by(DeviceSession.last_seen_at.desc())
    ).all()
    subscriptions = db.execute(
        select(Subscription, Plan)
        .join(Plan)
        .where(Subscription.user_id == user.id)
        .order_by(Subscription.created_at.desc())
    ).all()
    entitlements = db.scalars(
        select(Entitlement)
        .where(Entitlement.user_id == user.id)
        .order_by(Entitlement.created_at.desc())
    ).all()
    return {
        **summary,
        "profiles": [
            {
                "id": str(p.id),
                "name": p.name,
                "is_kids": p.is_kids,
                "language": p.language,
                "created_at": p.created_at,
            }
            for p in profiles
        ],
        "sessions": [
            {
                "id": str(s.id),
                "active_profile_id": str(s.active_profile_id) if s.active_profile_id else None,
                "user_agent": s.user_agent,
                "ip_address": s.ip_address,
                "last_seen_at": s.last_seen_at,
                "expires_at": s.expires_at,
                "revoked_at": s.revoked_at,
            }
            for s in sessions
        ],
        "subscriptions": [
            {
                "id": str(s.id),
                "plan": p.name,
                "status": s.status.value,
                "provider": s.provider,
                "current_period_end": s.current_period_end,
                "cancel_at_period_end": s.cancel_at_period_end,
            }
            for s, p in subscriptions
        ],
        "entitlements": [
            {
                "key": e.key,
                "value": e.value,
                "source": e.source,
                "starts_at": e.starts_at,
                "ends_at": e.ends_at,
            }
            for e in entitlements
        ],
    }


@router.patch("/users/{user_id}/state")
def update_user_state(
    user_id: uuid.UUID,
    payload: UserStateUpdate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    user = user_or_404(db, user_id)
    previous = user.is_active
    user.is_active = payload.is_active
    revoked = 0
    if not payload.is_active:
        result = db.execute(
            update(DeviceSession)
            .where(DeviceSession.user_id == user.id, DeviceSession.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
        revoked = result.rowcount
    audit(
        db,
        request,
        admin,
        "support.customer.state_updated",
        {
            "user_id": str(user.id),
            "previous": previous,
            "is_active": payload.is_active,
            "reason": payload.reason,
            "sessions_revoked": revoked,
        },
    )
    db.commit()
    return {"id": user.id, "is_active": user.is_active, "sessions_revoked": revoked}


@router.post("/users/{user_id}/revoke-sessions")
def revoke_user_sessions(
    user_id: uuid.UUID,
    payload: SessionRevocation,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    user = user_or_404(db, user_id)
    result = db.execute(
        update(DeviceSession)
        .where(DeviceSession.user_id == user.id, DeviceSession.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    audit(
        db,
        request,
        admin,
        "support.customer.sessions_revoked",
        {"user_id": str(user.id), "reason": payload.reason, "sessions_revoked": result.rowcount},
    )
    db.commit()
    return {"id": user.id, "sessions_revoked": result.rowcount}


@router.get("/users/{user_id}/export")
def export_user(user_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity):
    user = user_or_404(db, user_id)
    profiles = db.scalars(select(Profile).where(Profile.user_id == user.id)).all()
    sessions = db.scalars(select(DeviceSession).where(DeviceSession.user_id == user.id)).all()
    subscriptions = db.scalars(select(Subscription).where(Subscription.user_id == user.id)).all()
    entitlements = db.scalars(select(Entitlement).where(Entitlement.user_id == user.id)).all()
    payments = (
        db.scalars(
            select(PaymentReference).where(
                PaymentReference.subscription_id.in_([item.id for item in subscriptions])
            )
        ).all()
        if subscriptions
        else []
    )
    result = {
        "id": user.id,
        "email": user.email,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "profiles": [profile_export(db, profile) for profile in profiles],
        "sessions": [export_row(item) for item in sessions],
        "subscriptions": [export_row(item) for item in subscriptions],
        "entitlements": [export_row(item) for item in entitlements],
        "payment_history": [export_row(item) for item in payments],
    }
    audit(
        db,
        request,
        admin,
        "support.customer.exported",
        {"user_id": str(user_id), "scope": "portable_customer_record_v1"},
    )
    db.commit()
    return {
        "exported_at": datetime.now(UTC),
        "customer": result,
        "format": "aperture-portable-customer-record-v1",
        "notice": (
            "Authentication secrets, invitation credentials, and provider references are "
            "intentionally excluded."
        ),
    }


@router.delete("/users/{user_id}")
def delete_user(
    user_id: uuid.UUID,
    payload: CustomerDeletionRequest,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    user = user_or_404(db, user_id)
    if payload.confirmation_email.lower() != user.email.lower():
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirmation email does not match")
    if payload.confirmation_phrase != "DELETE CUSTOMER":
        raise HTTPException(status.HTTP_409_CONFLICT, "Confirmation phrase is incorrect")
    profile_count = (
        db.scalar(select(func.count()).select_from(Profile).where(Profile.user_id == user.id)) or 0
    )
    email_digest = hashlib.sha256(user.email.lower().encode()).hexdigest()
    audit(
        db,
        request,
        admin,
        "support.customer.deleted",
        {
            "deleted_user_id": str(user.id),
            "email_sha256": email_digest,
            "profile_count": profile_count,
            "reason": payload.reason,
            "authorization_reference": payload.authorization_reference,
            "retained": "non-identifying administrator audit tombstone",
        },
    )
    db.delete(user)
    db.commit()
    return {
        "deleted_user_id": user_id,
        "deleted_profiles": profile_count,
        "retained": "non-identifying administrator audit tombstone",
    }


@router.get("/subscriptions", response_model=SupportSubscriptionList)
def list_subscriptions(
    db: DbSession,
    _: AdminIdentity,
    q: str = Query(default="", max_length=320),
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(default=100, ge=1, le=200),
):
    query = (
        select(Subscription, User, Plan)
        .join(User, User.id == Subscription.user_id)
        .join(Plan, Plan.id == Subscription.plan_id)
    )
    filters = []
    if q.strip():
        filters.append(or_(User.email.ilike(f"%{q.strip()}%"), Plan.name.ilike(f"%{q.strip()}%")))
    if status_filter:
        filters.append(Subscription.status == status_filter)
    total = db.scalar(select(func.count()).select_from(query.where(*filters).subquery())) or 0
    rows = db.execute(
        query.where(*filters).order_by(Subscription.updated_at.desc()).limit(limit)
    ).all()
    return SupportSubscriptionList(
        total=total,
        items=[
            SupportSubscription(
                id=s.id,
                user_id=u.id,
                email=u.email,
                plan_name=p.name,
                plan_code=p.code,
                status=s.status.value,
                provider=s.provider,
                current_period_end=s.current_period_end,
                cancel_at_period_end=s.cancel_at_period_end,
                updated_at=s.updated_at,
            )
            for s, u, p in rows
        ],
    )


@router.get("/storage")
def storage_inventory(db: DbSession, _: AdminIdentity):
    settings = get_settings()
    states = {
        state.value: count
        for state, count in db.execute(
            select(MediaAsset.state, func.count()).group_by(MediaAsset.state)
        ).all()
    }
    registered_bytes = db.scalar(select(func.coalesce(func.sum(MediaAsset.size_bytes), 0))) or 0
    recent_failures = (
        db.execute(
            select(MediaAsset)
            .where(MediaAsset.state == AssetState.failed)
            .order_by(MediaAsset.updated_at.desc())
            .limit(10)
        )
        .scalars()
        .all()
    )
    available, versioning = True, "unknown"
    try:
        client = s3_client()
        client.head_bucket(Bucket=settings.s3_bucket)
        versioning = (
            client.get_bucket_versioning(Bucket=settings.s3_bucket)
            .get("Status", "disabled")
            .lower()
        )
    except Exception:
        available = False
    return {
        "bucket": settings.s3_bucket,
        "available": available,
        "versioning": versioning,
        "registered_bytes": registered_bytes,
        "asset_states": states,
        "processing_jobs": db.scalar(select(func.count()).select_from(ProcessingJob)) or 0,
        "recent_failures": [
            {
                "id": str(a.id),
                "filename": a.original_filename,
                "reason": a.failure_reason,
                "updated_at": a.updated_at,
            }
            for a in recent_failures
        ],
    }
