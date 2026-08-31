import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.models import Admin, AuditLog, Plan, ViewerPaymentConnection
from app.site_brand_service import get_or_claim_configuration
from app.viewer_plan_schemas import ViewerPlanAdminResponse, ViewerPlanArchive, ViewerPlanCreate

router = APIRouter(
    prefix="/admin/viewer-plans",
    tags=["administrator viewer subscription plans"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
PRIVATE_NO_STORE_HEADERS = {
    "Cache-Control": "private, no-store, max-age=0, must-revalidate",
    "Pragma": "no-cache",
    "Expires": "0",
    "Vary": "Cookie",
}


def _private_no_store(response: Response) -> None:
    response.headers.update(PRIVATE_NO_STORE_HEADERS)


def _audit(
    db: DbSession,
    request: Request,
    admin: Admin,
    action: str,
    detail: dict[str, Any],
) -> None:
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail=detail,
        )
    )


def _require_owner(db: DbSession, request: Request, admin: Admin) -> None:
    _, claimed = get_or_claim_configuration(db, admin)
    if claimed:
        _audit(
            db,
            request,
            admin,
            "site_brand.owner.claimed",
            {"schema_version": 1},
        )
        db.commit()


def _plan_not_found() -> HTTPException:
    return HTTPException(status.HTTP_404_NOT_FOUND, "Viewer subscription plan was not found")


@router.get("", response_model=list[ViewerPlanAdminResponse])
def list_viewer_plans(
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> list[Plan]:
    _private_no_store(response)
    _require_owner(db, request, admin)
    return list(
        db.scalars(
            select(Plan).order_by(
                Plan.is_active.desc(),
                Plan.price_cents,
                Plan.code,
                Plan.id,
            )
        )
    )


@router.post(
    "",
    response_model=ViewerPlanAdminResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_viewer_plan(
    payload: ViewerPlanCreate,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> Plan:
    _private_no_store(response)
    _require_owner(db, request, admin)
    plan = Plan(**payload.model_dump(), is_active=True)
    db.add(plan)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "A viewer subscription plan with this code already exists",
        ) from None
    _audit(
        db,
        request,
        admin,
        "viewer_plan.created",
        {
            "schema_version": 1,
            "plan_id": str(plan.id),
            "code": plan.code,
            "price_cents": plan.price_cents,
            "currency": plan.currency,
            "interval": plan.interval.value,
            "max_streams": plan.max_streams,
            "max_resolution": plan.max_resolution,
        },
    )
    db.commit()
    db.refresh(plan)
    return plan


@router.post("/{plan_id}/archive", response_model=ViewerPlanAdminResponse)
def archive_viewer_plan(
    plan_id: uuid.UUID,
    payload: ViewerPlanArchive,
    request: Request,
    response: Response,
    db: DbSession,
    admin: AdminIdentity,
) -> Plan:
    _private_no_store(response)
    _require_owner(db, request, admin)

    # Lock monetization mode before the active plan set. Concurrent archive requests then
    # serialize and cannot both observe a different plan as the remaining active plan.
    connection = db.scalar(
        select(ViewerPaymentConnection).where(ViewerPaymentConnection.id == 1).with_for_update()
    )
    if connection is not None and connection.owner_admin_id != admin.id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only the site owner can manage viewer subscription plans",
        )

    active_plans = list(
        db.scalars(select(Plan).where(Plan.is_active.is_(True)).order_by(Plan.id).with_for_update())
    )
    plan = next((candidate for candidate in active_plans if candidate.id == plan_id), None)
    if plan is None:
        plan = db.get(Plan, plan_id)
        if plan is None:
            raise _plan_not_found()
    if payload.confirmation_code != plan.code:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Confirmation code does not match the viewer plan code",
        )
    if not plan.is_active:
        return plan

    if (
        connection is not None
        and connection.access_mode == "subscription_required"
        and len(active_plans) == 1
    ):
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "Create another active plan before archiving the final plan while subscription "
            "access is required",
        )

    plan.is_active = False
    _audit(
        db,
        request,
        admin,
        "viewer_plan.archived",
        {
            "schema_version": 1,
            "plan_id": str(plan.id),
            "code": plan.code,
        },
    )
    db.commit()
    db.refresh(plan)
    return plan
