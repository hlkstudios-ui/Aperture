import uuid

from fastapi import HTTPException, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.catalog_models import Movie, Series
from app.catalog_visibility import public_title_conditions
from app.curation_models import (
    Collection,
    CollectionItem,
    Journey,
    JourneyChapter,
    JourneyItem,
    JourneyProgress,
)
from app.curation_schemas import (
    CollectionResponse,
    JourneyChapterResponse,
    JourneyResponse,
    TitleCard,
)
from app.models import Profile


def title_card(
    db: Session,
    item,
    completed: set[uuid.UUID] | None = None,
    country: str | None = None,
) -> TitleCard | None:
    model, title_id, kind = (
        (Movie, item.movie_id, "movie") if item.movie_id else (Series, item.series_id, "series")
    )
    record = db.scalar(
        select(model).where(model.id == title_id, *public_title_conditions(model, country=country))
    )
    if record is None:
        return None
    return TitleCard(
        item_id=item.id,
        title_id=record.id,
        kind=kind,
        slug=record.slug,
        title=record.title,
        short_description=record.short_description,
        position=item.position,
        note=getattr(item, "note", None) or getattr(item, "introduction", None),
        completed=item.id in (completed or set()),
    )


def collection_response(
    db: Session, collection: Collection, country: str | None = None
) -> CollectionResponse:
    cards = [card for item in collection.items if (card := title_card(db, item, country=country))]
    return CollectionResponse(
        id=collection.id,
        slug=collection.slug,
        title=collection.title,
        description=collection.description,
        kind=collection.kind,
        status=collection.status,
        owner_profile_id=collection.owner_profile_id,
        owner_profile_name=(
            db.scalar(select(Profile.name).where(Profile.id == collection.owner_profile_id))
            if collection.owner_profile_id
            else None
        ),
        visibility=collection.visibility,
        moderation_status=collection.moderation_status,
        items=cards,
    )


def journey_response(
    db: Session,
    journey: Journey,
    profile_id: uuid.UUID | None = None,
    country: str | None = None,
    *,
    include_empty_chapters: bool = False,
) -> JourneyResponse:
    item_ids = [item.id for chapter in journey.chapters for item in chapter.items]
    completed = (
        set(
            db.scalars(
                select(JourneyProgress.journey_item_id).where(
                    JourneyProgress.profile_id == profile_id,
                    JourneyProgress.journey_item_id.in_(item_ids),
                )
            )
        )
        if profile_id and item_ids
        else set()
    )
    chapters = []
    for chapter in journey.chapters:
        cards = [
            card for item in chapter.items if (card := title_card(db, item, completed, country))
        ]
        if cards or include_empty_chapters:
            chapters.append(
                JourneyChapterResponse(
                    title=chapter.title,
                    introduction=chapter.introduction,
                    position=chapter.position,
                    items=cards,
                )
            )
    visible_ids = {
        item.id
        for chapter in journey.chapters
        for item in chapter.items
        if title_card(db, item, country=country)
    }
    done = len(completed & visible_ids)
    return JourneyResponse(
        id=journey.id,
        slug=journey.slug,
        title=journey.title,
        description=journey.description,
        status=journey.status,
        chapters=chapters,
        completed_items=done,
        total_items=len(visible_ids),
        completed=bool(visible_ids) and done == len(visible_ids),
    )


def replace_collection_items(db: Session, collection: Collection, items) -> None:
    db.execute(delete(CollectionItem).where(CollectionItem.collection_id == collection.id))
    for position, item in enumerate(items):
        db.add(CollectionItem(collection_id=collection.id, position=position, **item.model_dump()))


def replace_journey_chapters(db: Session, journey: Journey, chapters) -> None:
    db.execute(delete(JourneyChapter).where(JourneyChapter.journey_id == journey.id))
    db.flush()
    for chapter_position, payload in enumerate(chapters):
        chapter = JourneyChapter(
            journey_id=journey.id,
            position=chapter_position,
            title=payload.title,
            introduction=payload.introduction,
        )
        db.add(chapter)
        db.flush()
        for position, item in enumerate(payload.items):
            values = item.model_dump()
            values["introduction"] = values.pop("note")
            db.add(JourneyItem(chapter_id=chapter.id, position=position, **values))


def load_collection(db: Session, collection_id: uuid.UUID) -> Collection:
    record = db.scalar(
        select(Collection)
        .options(selectinload(Collection.items))
        .where(Collection.id == collection_id)
    )
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Collection was not found")
    return record


def load_journey(db: Session, *, journey_id=None, slug=None) -> Journey:
    condition = Journey.id == journey_id if journey_id else Journey.slug == slug
    record = db.scalar(
        select(Journey)
        .options(selectinload(Journey.chapters).selectinload(JourneyChapter.items))
        .where(condition)
    )
    if not record:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Journey was not found")
    return record
