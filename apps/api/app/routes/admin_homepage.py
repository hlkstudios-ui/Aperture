import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Movie, Series
from app.homepage_schemas import (
    HeroUpdate,
    HomepageDraftResponse,
    HomepagePublicResponse,
    ItemCreate,
    ItemResponse,
    OrderedIds,
    RailCreate,
    RailResponse,
    RailUpdate,
)
from app.homepage_service import draft_snapshot, get_configuration, render_homepage
from app.models import Admin, AuditLog, HomepageItem, HomepageRail

router = APIRouter(
    prefix="/admin/homepage",
    tags=["administrator homepage"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]


def _audit(db: DbSession, request: Request, admin: Admin, action: str, detail: dict) -> None:
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


def _draft(db: DbSession) -> HomepageDraftResponse:
    config = get_configuration(db)
    return HomepageDraftResponse(
        id=config.id,
        hero_movie_id=config.draft_hero_movie_id,
        hero_series_id=config.draft_hero_series_id,
        rails=config.rails,
        published_at=config.published_at,
    )


@router.get("", response_model=HomepageDraftResponse)
def get_draft(db: DbSession) -> HomepageDraftResponse:
    return _draft(db)


@router.put("/hero", response_model=HomepageDraftResponse)
def set_hero(
    payload: HeroUpdate, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageDraftResponse:
    if payload.movie_id and db.get(Movie, payload.movie_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Movie was not found")
    if payload.series_id and db.get(Series, payload.series_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Series was not found")
    config = get_configuration(db)
    config.draft_hero_movie_id = payload.movie_id
    config.draft_hero_series_id = payload.series_id
    _audit(
        db,
        request,
        admin,
        "homepage.hero.updated",
        {
            "movie_id": str(payload.movie_id) if payload.movie_id else None,
            "series_id": str(payload.series_id) if payload.series_id else None,
        },
    )
    db.commit()
    return _draft(db)


@router.post("/rails", response_model=RailResponse, status_code=status.HTTP_201_CREATED)
def create_rail(
    payload: RailCreate, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageRail:
    config = get_configuration(db)
    rail = HomepageRail(configuration_id=config.id, **payload.model_dump())
    db.add(rail)
    _audit(db, request, admin, "homepage.rail.created", {"rail_id": str(rail.id)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Rail position is already in use") from exc
    db.refresh(rail)
    return rail


def _rail(db: DbSession, rail_id: uuid.UUID) -> HomepageRail:
    rail = db.get(HomepageRail, rail_id)
    if rail is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Homepage rail was not found")
    return rail


@router.put("/rails/{rail_id}", response_model=RailResponse)
def update_rail(
    rail_id: uuid.UUID, payload: RailUpdate, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageRail:
    rail = _rail(db, rail_id)
    for key, value in payload.model_dump().items():
        setattr(rail, key, value)
    _audit(db, request, admin, "homepage.rail.updated", {"rail_id": str(rail.id)})
    db.commit()
    db.refresh(rail)
    return rail


@router.delete("/rails/{rail_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_rail(rail_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity) -> None:
    rail = _rail(db, rail_id)
    _audit(db, request, admin, "homepage.rail.deleted", {"rail_id": str(rail.id)})
    db.delete(rail)
    db.commit()


@router.post(
    "/rails/{rail_id}/items", response_model=ItemResponse, status_code=status.HTTP_201_CREATED
)
def add_item(
    rail_id: uuid.UUID, payload: ItemCreate, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageItem:
    _rail(db, rail_id)
    parent = db.get(Movie if payload.movie_id else Series, payload.movie_id or payload.series_id)
    if parent is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pinned title was not found")
    item = HomepageItem(rail_id=rail_id, **payload.model_dump())
    db.add(item)
    _audit(db, request, admin, "homepage.item.pinned", {"rail_id": str(rail_id)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "Title or position is already pinned"
        ) from exc
    db.refresh(item)
    return item


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_item(item_id: uuid.UUID, request: Request, db: DbSession, admin: AdminIdentity) -> None:
    item = db.get(HomepageItem, item_id)
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Homepage item was not found")
    _audit(db, request, admin, "homepage.item.unpinned", {"item_id": str(item.id)})
    db.delete(item)
    db.commit()


def _reorder(
    db: DbSession, records: list[HomepageRail] | list[HomepageItem], ids: list[uuid.UUID]
) -> None:
    if {record.id for record in records} != set(ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Ordering must include every record exactly once"
        )
    for index, record in enumerate(records):
        record.position = 10_000 + index
    db.flush()
    for index, record_id in enumerate(ids):
        next(record for record in records if record.id == record_id).position = index


@router.put("/rails-order", response_model=HomepageDraftResponse)
def reorder_rails(
    payload: OrderedIds, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageDraftResponse:
    config = get_configuration(db)
    _reorder(db, config.rails, payload.ids)
    _audit(
        db,
        request,
        admin,
        "homepage.rails.reordered",
        {"ids": [str(value) for value in payload.ids]},
    )
    db.commit()
    return _draft(db)


@router.put("/rails/{rail_id}/items-order", response_model=RailResponse)
def reorder_items(
    rail_id: uuid.UUID, payload: OrderedIds, request: Request, db: DbSession, admin: AdminIdentity
) -> HomepageRail:
    rail = _rail(db, rail_id)
    _reorder(db, rail.items, payload.ids)
    _audit(db, request, admin, "homepage.items.reordered", {"rail_id": str(rail.id)})
    db.commit()
    db.refresh(rail)
    return rail


@router.get("/preview", response_model=HomepagePublicResponse)
def preview(db: DbSession) -> HomepagePublicResponse:
    config = get_configuration(db)
    return render_homepage(
        db, draft_snapshot(config), preview=True, published_at=config.published_at
    )


@router.post("/publish", response_model=HomepagePublicResponse)
def publish(request: Request, db: DbSession, admin: AdminIdentity) -> HomepagePublicResponse:
    config = get_configuration(db)
    snapshot = draft_snapshot(config)
    config.published_snapshot = snapshot
    config.published_at = datetime.now(UTC)
    _audit(db, request, admin, "homepage.published", {"rail_count": len(config.rails)})
    db.commit()
    return render_homepage(db, snapshot, preview=True, published_at=config.published_at)
