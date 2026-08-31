import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, select

from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.curation_models import (
    Collection,
    CollectionKind,
    CurationStatus,
    Journey,
    JourneyProgress,
)
from app.curation_schemas import CollectionResponse, JourneyResponse, ProgressWrite, UserListWrite
from app.curation_service import (
    collection_response,
    journey_response,
    load_collection,
    load_journey,
    replace_collection_items,
)
from app.geo import OptionalViewerCountry
from app.models import DeviceSession
from app.rate_limit import enforce_rate_limit
from app.routes.recommendations import active_profile

router = APIRouter(
    prefix="/curation", tags=["curation"], dependencies=[Depends(require_trusted_origin)]
)
CurrentSession = Annotated[DeviceSession, Depends(require_customer_session)]


@router.get("/collections", response_model=list[CollectionResponse])
def collections(db: DbSession, country: OptionalViewerCountry):
    records = db.scalars(
        select(Collection)
        .where(
            Collection.status == CurationStatus.published,
            Collection.kind != CollectionKind.user_list,
        )
        .order_by(Collection.updated_at.desc())
    ).all()
    responses = [collection_response(db, load_collection(db, x.id), country) for x in records]
    return [response for response in responses if response.items]


@router.get("/collections/{slug}", response_model=CollectionResponse)
def collection(slug: str, db: DbSession, country: OptionalViewerCountry):
    record = db.scalar(
        select(Collection).where(
            Collection.slug == slug,
            Collection.status == CurationStatus.published,
            Collection.kind != CollectionKind.user_list,
        )
    )
    if not record:
        raise HTTPException(404, "Collection was not found")
    response = collection_response(db, load_collection(db, record.id), country)
    if not response.items:
        raise HTTPException(404, "Collection was not found")
    return response


@router.get("/journeys", response_model=list[JourneyResponse])
def journeys(db: DbSession, country: OptionalViewerCountry):
    responses = [
        journey_response(db, load_journey(db, journey_id=x.id), country=country)
        for x in db.scalars(
            select(Journey)
            .where(Journey.status == CurationStatus.published)
            .order_by(Journey.updated_at.desc())
        )
    ]
    return [response for response in responses if response.total_items]


@router.get("/journeys/{slug}", response_model=JourneyResponse)
def journey(slug: str, db: DbSession, country: OptionalViewerCountry):
    record = load_journey(db, slug=slug)
    if record.status is not CurationStatus.published:
        raise HTTPException(404, "Journey was not found")
    response = journey_response(db, record, country=country)
    if not response.total_items:
        raise HTTPException(404, "Journey was not found")
    return response


@router.get("/my-lists", response_model=list[CollectionResponse])
def my_lists(db: DbSession, session: CurrentSession, country: OptionalViewerCountry):
    profile = active_profile(db, session)
    records = db.scalars(
        select(Collection)
        .where(
            Collection.owner_profile_id == profile.id, Collection.kind == CollectionKind.user_list
        )
        .order_by(Collection.updated_at.desc())
    ).all()
    return [collection_response(db, load_collection(db, x.id), country) for x in records]


@router.post("/my-lists", response_model=CollectionResponse, status_code=status.HTTP_201_CREATED)
async def create_my_list(
    payload: UserListWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
):
    profile = active_profile(db, session)
    await enforce_rate_limit(f"community:list:{profile.id}", limit=10, window_seconds=3600)
    stem = re.sub(r"[^a-z0-9]+", "-", payload.title.lower()).strip("-")[:150] or "list"
    record = Collection(
        slug=f"{stem}-{uuid.uuid4().hex[:10]}",
        title=payload.title,
        description=payload.description,
        kind=CollectionKind.user_list,
        status=CurationStatus.draft,
        owner_profile_id=profile.id,
        visibility=payload.visibility,
        moderation_status="pending",
    )
    db.add(record)
    db.flush()
    replace_collection_items(db, record, payload.items)
    db.commit()
    return collection_response(db, load_collection(db, record.id), country)


@router.put("/my-lists/{collection_id}", response_model=CollectionResponse)
async def update_my_list(
    collection_id: uuid.UUID,
    payload: UserListWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
):
    profile = active_profile(db, session)
    await enforce_rate_limit(f"community:list:{profile.id}", limit=20, window_seconds=3600)
    record = load_collection(db, collection_id)
    if record.owner_profile_id != profile.id or record.kind is not CollectionKind.user_list:
        raise HTTPException(404, "List was not found")
    record.title, record.description, record.visibility = (
        payload.title,
        payload.description,
        payload.visibility,
    )
    record.moderation_status = "pending"
    replace_collection_items(db, record, payload.items)
    db.commit()
    return collection_response(db, load_collection(db, record.id), country)


@router.get("/journeys/{slug}/progress", response_model=JourneyResponse)
def journey_progress(
    slug: str,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
):
    profile = active_profile(db, session)
    record = load_journey(db, slug=slug)
    if record.status is not CurationStatus.published:
        raise HTTPException(404, "Journey was not found")
    response = journey_response(db, record, profile.id, country)
    if not response.total_items:
        raise HTTPException(404, "Journey was not found")
    return response


@router.put("/journeys/{slug}/progress", response_model=JourneyResponse)
def set_journey_progress(
    slug: str,
    payload: ProgressWrite,
    db: DbSession,
    session: CurrentSession,
    country: OptionalViewerCountry,
):
    profile = active_profile(db, session)
    record = load_journey(db, slug=slug)
    response = journey_response(db, record, profile.id, country)
    visible_item_ids = {
        item.item_id for chapter in response.chapters for item in chapter.items
    }
    if (
        record.status is not CurationStatus.published
        or payload.journey_item_id not in visible_item_ids
    ):
        raise HTTPException(404, "Journey item was not found")
    db.execute(
        delete(JourneyProgress).where(
            JourneyProgress.profile_id == profile.id,
            JourneyProgress.journey_item_id == payload.journey_item_id,
        )
    )
    if payload.completed:
        db.add(JourneyProgress(profile_id=profile.id, journey_item_id=payload.journey_item_id))
    db.commit()
    return journey_response(db, load_journey(db, journey_id=record.id), profile.id, country)
