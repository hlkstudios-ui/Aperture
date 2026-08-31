import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select

from app.auth import DbSession, require_admin, require_trusted_origin
from app.curation_models import Collection, CollectionKind, Journey
from app.curation_schemas import CollectionResponse, CollectionWrite, JourneyResponse, JourneyWrite
from app.curation_service import (
    collection_response,
    journey_response,
    load_collection,
    load_journey,
    replace_collection_items,
    replace_journey_chapters,
)
from app.models import Admin, AuditLog

router = APIRouter(
    prefix="/admin/curation",
    tags=["administrator curation"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def audit(db, request, admin, action, record):
    db.add(
        AuditLog(
            actor_type="admin",
            actor_id=admin.id,
            action=action,
            outcome="succeeded",
            ip_address=request.client.host if request.client else None,
            detail={"record_id": str(record.id)},
        )
    )


@router.get("/collections", response_model=list[CollectionResponse])
def collections(db: DbSession):
    records = db.scalars(
        select(Collection)
        .where(Collection.kind != CollectionKind.user_list)
        .order_by(Collection.updated_at.desc())
    ).all()
    return [collection_response(db, load_collection(db, record.id)) for record in records]


@router.post("/collections", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
def create_collection(
    payload: CollectionWrite, request: Request, db: DbSession, admin: AdminIdentity
):
    if payload.kind is CollectionKind.user_list:
        from fastapi import HTTPException

        raise HTTPException(422, "Administrators cannot create private user lists")
    record = Collection(**payload.model_dump(exclude={"items"}), created_by_admin_id=admin.id)
    db.add(record)
    db.flush()
    replace_collection_items(db, record, payload.items)
    audit(db, request, admin, "curation.collection.created", record)
    db.commit()
    return collection_response(db, load_collection(db, record.id))


@router.put("/collections/{collection_id}", response_model=CollectionResponse)
def update_collection(
    collection_id: uuid.UUID,
    payload: CollectionWrite,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = load_collection(db, collection_id)
    if record.kind is CollectionKind.user_list:
        from fastapi import HTTPException

        raise HTTPException(404, "Collection was not found")
    for key, value in payload.model_dump(exclude={"items"}).items():
        setattr(record, key, value)
    replace_collection_items(db, record, payload.items)
    audit(db, request, admin, "curation.collection.updated", record)
    db.commit()
    return collection_response(db, load_collection(db, record.id))


@router.get("/journeys", response_model=list[JourneyResponse])
def journeys(db: DbSession):
    return [
        journey_response(db, load_journey(db, journey_id=x.id), include_empty_chapters=True)
        for x in db.scalars(select(Journey).order_by(Journey.updated_at.desc()))
    ]


@router.post("/journeys", response_model=JourneyResponse, status_code=status.HTTP_201_CREATED)
def create_journey(payload: JourneyWrite, request: Request, db: DbSession, admin: AdminIdentity):
    record = Journey(**payload.model_dump(exclude={"chapters"}), created_by_admin_id=admin.id)
    db.add(record)
    db.flush()
    replace_journey_chapters(db, record, payload.chapters)
    audit(db, request, admin, "curation.journey.created", record)
    db.commit()
    return journey_response(
        db, load_journey(db, journey_id=record.id), include_empty_chapters=True
    )


@router.put("/journeys/{journey_id}", response_model=JourneyResponse)
def update_journey(
    journey_id: uuid.UUID,
    payload: JourneyWrite,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
):
    record = load_journey(db, journey_id=journey_id)
    for key, value in payload.model_dump(exclude={"chapters"}).items():
        setattr(record, key, value)
    replace_journey_chapters(db, record, payload.chapters)
    audit(db, request, admin, "curation.journey.updated", record)
    db.commit()
    return journey_response(
        db, load_journey(db, journey_id=record.id), include_empty_chapters=True
    )
