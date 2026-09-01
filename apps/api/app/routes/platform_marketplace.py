import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy import select

from app.auth import DbSession
from app.platform_marketplace_service import (
    create_rental_intent,
    reconcile_expired_rental_intents,
    rental_response,
    template_response,
)
from app.platform_models import PlatformTemplate, TemplateRental
from app.platform_schemas import (
    PlatformTemplateCollection,
    PlatformTemplateDetail,
    RentalIntentCreate,
    TemplateRentalCollection,
    TemplateRentalResponse,
)
from app.platform_security import (
    PlatformIdentity,
    VerifiedPlatformIdentity,
    require_platform_origin,
)

router = APIRouter(
    prefix="/platform",
    tags=["platform marketplace"],
    dependencies=[Depends(require_platform_origin)],
)


@router.get("/templates", response_model=PlatformTemplateCollection)
def list_templates(db: DbSession) -> PlatformTemplateCollection:
    templates = list(
        db.scalars(
            select(PlatformTemplate)
            .where(PlatformTemplate.status.in_(["preview", "published"]))
            .order_by(PlatformTemplate.name, PlatformTemplate.id)
        )
    )
    return PlatformTemplateCollection(
        items=[template_response(db, template, detail=False) for template in templates]
    )


@router.get("/templates/{slug}", response_model=PlatformTemplateDetail)
def get_template(slug: str, db: DbSession) -> PlatformTemplateDetail:
    template = db.scalar(
        select(PlatformTemplate).where(
            PlatformTemplate.slug == slug.strip().lower(),
            PlatformTemplate.status.in_(["preview", "published"]),
        )
    )
    if template is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Template was not found")
    response = template_response(db, template, detail=True)
    if not isinstance(response, PlatformTemplateDetail):
        raise RuntimeError("Platform template detail could not be rendered")
    return response


@router.post(
    "/rental-intents",
    response_model=TemplateRentalResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_intent(
    payload: RentalIntentCreate,
    request: Request,
    response: Response,
    db: DbSession,
    account: VerifiedPlatformIdentity,
    idempotency_key: Annotated[uuid.UUID, Header(alias="Idempotency-Key")],
) -> TemplateRentalResponse:
    result, replayed = create_rental_intent(
        db,
        request,
        account,
        idempotency_key,
        payload,
    )
    response.headers["Location"] = f"/platform/rentals/{result.id}"
    if replayed:
        response.headers["Idempotency-Replayed"] = "true"
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/rentals", response_model=TemplateRentalCollection)
def list_rentals(db: DbSession, account: PlatformIdentity) -> TemplateRentalCollection:
    expired = reconcile_expired_rental_intents(
        db,
        account_id=account.id,
        limit=500,
        skip_locked=False,
    )
    if expired:
        db.commit()
    rentals = list(
        db.scalars(
            select(TemplateRental)
            .where(TemplateRental.account_id == account.id)
            .order_by(TemplateRental.created_at.desc(), TemplateRental.id)
        )
    )
    return TemplateRentalCollection(rentals=[rental_response(db, rental) for rental in rentals])


@router.get("/rentals/{rental_id}", response_model=TemplateRentalResponse)
def get_rental(
    rental_id: uuid.UUID,
    db: DbSession,
    account: PlatformIdentity,
) -> TemplateRentalResponse:
    expired = reconcile_expired_rental_intents(
        db,
        account_id=account.id,
        limit=500,
        skip_locked=False,
    )
    if expired:
        db.commit()
    rental = db.scalar(
        select(TemplateRental).where(
            TemplateRental.id == rental_id,
            TemplateRental.account_id == account.id,
        )
    )
    if rental is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rental was not found")
    return rental_response(db, rental)
