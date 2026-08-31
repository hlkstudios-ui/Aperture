import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from app.auth import DbSession, require_admin, require_trusted_origin
from app.catalog_models import Movie, Series
from app.explore_models import ExploreEntry, ExploreEntryCard
from app.explore_schemas import (
    ExploreCardCreate,
    ExploreCardOrder,
    ExploreCardResponse,
    ExploreEntryOrder,
    ExploreEntryPublicResponse,
    ExploreEntryResponse,
    ExploreEntryWrite,
)
from app.explore_service import (
    admin_card_responses,
    admin_entry_responses,
    load_explore_entries,
    load_explore_entry,
    public_entry_responses,
)
from app.geo import OptionalViewerCountry
from app.models import Admin, AuditLog

public_router = APIRouter(prefix="/catalog/explore", tags=["customer catalog"])
admin_router = APIRouter(
    prefix="/admin/explore",
    tags=["administrator explore"],
    dependencies=[Depends(require_trusted_origin), Depends(require_admin)],
)
AdminIdentity = Annotated[Admin, Depends(require_admin)]
MAX_EXPLORE_ENTRIES = 24
MAX_EXPLORE_CARDS_PER_ENTRY = 100
RESERVED_LABELS = {"ongoing", "recent searches", "trending"}


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


def _entry(db: DbSession, entry_id: uuid.UUID) -> ExploreEntry:
    entry = load_explore_entry(db, entry_id)
    if entry is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Explore entry was not found")
    return entry


def _card(db: DbSession, card_id: uuid.UUID) -> ExploreEntryCard:
    card = db.get(ExploreEntryCard, card_id)
    if card is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Explore card was not found")
    return card


def _admin_entry_response(db: DbSession, entry: ExploreEntry) -> ExploreEntryResponse:
    return admin_entry_responses(db, [entry])[0]


def _validate_label(db: DbSession, label: str, *, exclude_id: uuid.UUID | None = None) -> None:
    normalized = label.casefold()
    if normalized in RESERVED_LABELS:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That label is reserved for a built-in Explore view",
        )
    statement = select(ExploreEntry.id).where(func.lower(ExploreEntry.label) == label.lower())
    if exclude_id is not None:
        statement = statement.where(ExploreEntry.id != exclude_id)
    if db.scalar(statement) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Explore labels must be unique")


@public_router.get("", response_model=list[ExploreEntryPublicResponse])
def public_entries(
    db: DbSession, country: OptionalViewerCountry
) -> list[ExploreEntryPublicResponse]:
    return public_entry_responses(db, country=country)


@admin_router.get("", response_model=list[ExploreEntryResponse])
def admin_entries(db: DbSession) -> list[ExploreEntryResponse]:
    return admin_entry_responses(db)


@admin_router.post("", response_model=ExploreEntryResponse, status_code=status.HTTP_201_CREATED)
def create_entry(
    payload: ExploreEntryWrite,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ExploreEntryResponse:
    if (db.scalar(select(func.count(ExploreEntry.id))) or 0) >= MAX_EXPLORE_ENTRIES:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Explore supports up to {MAX_EXPLORE_ENTRIES} custom entries",
        )
    _validate_label(db, payload.label)
    entry = ExploreEntry(
        **payload.model_dump(exclude={"criteria"}),
        criteria=payload.criteria.model_dump(exclude_none=True),
    )
    db.add(entry)
    try:
        db.flush()
        _audit(db, request, admin, "explore.entry.created", {"entry_id": str(entry.id)})
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Explore position is already in use") from exc
    db.refresh(entry)
    return _admin_entry_response(db, entry)


@admin_router.put("/order", response_model=list[ExploreEntryResponse])
def reorder_entries(
    payload: ExploreEntryOrder,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> list[ExploreEntryResponse]:
    entries = load_explore_entries(db)
    if {entry.id for entry in entries} != set(payload.ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Ordering must include every Explore entry exactly once",
        )
    for index, entry in enumerate(entries):
        entry.position = 10_000 + index
    db.flush()
    by_id = {entry.id: entry for entry in entries}
    for index, entry_id in enumerate(payload.ids):
        by_id[entry_id].position = index
    _audit(
        db,
        request,
        admin,
        "explore.entries.reordered",
        {"ids": [str(entry_id) for entry_id in payload.ids]},
    )
    db.commit()
    return admin_entry_responses(db, sorted(entries, key=lambda entry: entry.position))


@admin_router.post(
    "/{entry_id}/cards",
    response_model=ExploreCardResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_card(
    entry_id: uuid.UUID,
    payload: ExploreCardCreate,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ExploreCardResponse:
    _entry(db, entry_id)
    if (
        db.scalar(
            select(func.count(ExploreEntryCard.id)).where(ExploreEntryCard.entry_id == entry_id)
        )
        or 0
    ) >= MAX_EXPLORE_CARDS_PER_ENTRY:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"An Explore entry supports up to {MAX_EXPLORE_CARDS_PER_ENTRY} cards",
        )
    model = Movie if payload.movie_id is not None else Series
    title_id = payload.movie_id or payload.series_id
    if db.get(model, title_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Pinned title was not found")
    card = ExploreEntryCard(entry_id=entry_id, **payload.model_dump())
    db.add(card)
    try:
        db.flush()
        _audit(
            db,
            request,
            admin,
            "explore.card.added",
            {
                "entry_id": str(entry_id),
                "card_id": str(card.id),
                "movie_id": str(card.movie_id) if card.movie_id else None,
                "series_id": str(card.series_id) if card.series_id else None,
            },
        )
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "That title or position is already pinned to this Explore entry",
        ) from exc
    db.refresh(card)
    return admin_card_responses(db, [card])[0]


@admin_router.put(
    "/{entry_id}/cards/order",
    response_model=list[ExploreCardResponse],
)
def reorder_cards(
    entry_id: uuid.UUID,
    payload: ExploreCardOrder,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> list[ExploreCardResponse]:
    entry = _entry(db, entry_id)
    cards = list(entry.cards)
    if {card.id for card in cards} != set(payload.ids):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Ordering must include every card owned by this Explore entry exactly once",
        )
    for index, card in enumerate(cards):
        card.position = 10_000 + index
    db.flush()
    by_id = {card.id: card for card in cards}
    for index, card_id in enumerate(payload.ids):
        by_id[card_id].position = index
    _audit(
        db,
        request,
        admin,
        "explore.cards.reordered",
        {
            "entry_id": str(entry.id),
            "ids": [str(card_id) for card_id in payload.ids],
        },
    )
    db.commit()
    return admin_card_responses(db, cards)


@admin_router.delete("/cards/{card_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_card(
    card_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> None:
    card = _card(db, card_id)
    _audit(
        db,
        request,
        admin,
        "explore.card.removed",
        {
            "entry_id": str(card.entry_id),
            "card_id": str(card.id),
            "movie_id": str(card.movie_id) if card.movie_id else None,
            "series_id": str(card.series_id) if card.series_id else None,
        },
    )
    db.delete(card)
    db.commit()


@admin_router.put("/{entry_id}", response_model=ExploreEntryResponse)
def update_entry(
    entry_id: uuid.UUID,
    payload: ExploreEntryWrite,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> ExploreEntryResponse:
    entry = _entry(db, entry_id)
    _validate_label(db, payload.label, exclude_id=entry.id)
    for key, value in payload.model_dump(exclude={"criteria"}).items():
        setattr(entry, key, value)
    entry.criteria = payload.criteria.model_dump(exclude_none=True)
    _audit(db, request, admin, "explore.entry.updated", {"entry_id": str(entry.id)})
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Explore position is already in use") from exc
    db.refresh(entry)
    return _admin_entry_response(db, entry)


@admin_router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_entry(
    entry_id: uuid.UUID,
    request: Request,
    db: DbSession,
    admin: AdminIdentity,
) -> None:
    entry = _entry(db, entry_id)
    _audit(db, request, admin, "explore.entry.deleted", {"entry_id": str(entry.id)})
    db.delete(entry)
    db.commit()
