import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select

from app.ask_movie_service import ask_movie
from app.auth import DbSession, require_customer_session, require_trusted_origin
from app.feature_flags import require_ask_movie
from app.geo import OptionalViewerCountry
from app.models import DeviceSession, SceneBookmark, SceneNote
from app.moment_service import what_did_i_miss, who_was_that
from app.rate_limit import enforce_rate_limit
from app.relationship_graph_service import relationship_graph
from app.routes.playback import active_profile_id, playable_source
from app.scene_models import Scene, SceneIntelligenceVersion
from app.spoiler_schemas import (
    AskMovieRequest,
    AskMovieResponse,
    LensBookmarkCreate,
    LensBookmarkResponse,
    LensNoteCreate,
    LensNoteResponse,
    MissedIntervalRequest,
    RelationshipGraphResponse,
    SpoilerContextResponse,
    WhatDidIMissResponse,
    WhoWasThatResponse,
)
from app.spoiler_service import spoiler_context

router = APIRouter(
    prefix="/scene-intelligence",
    tags=["spoiler-safe scene intelligence"],
    dependencies=[Depends(require_trusted_origin), Depends(require_customer_session)],
)
ViewerSession = Annotated[DeviceSession, Depends(require_customer_session)]


@router.get("/sources/{source_id}/context", response_model=SpoilerContextResponse)
def context(
    source_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
    timestamp: float = Query(ge=0),
    mode: Literal["protected", "full"] = "protected",
) -> SpoilerContextResponse:
    return spoiler_context(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=active_profile_id(session),
        timestamp=timestamp,
        mode=mode,
    )


@router.post(
    "/sources/{source_id}/ask",
    response_model=AskMovieResponse,
    dependencies=[Depends(require_ask_movie)],
)
async def ask(
    source_id: uuid.UUID,
    payload: AskMovieRequest,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
) -> AskMovieResponse:
    profile_id = active_profile_id(session)
    await enforce_rate_limit(f"ask-movie:{profile_id}", limit=30, window_seconds=300)
    return ask_movie(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=profile_id,
        question=payload.question,
        timestamp=payload.timestamp_seconds,
        mode=payload.mode,
    )


@router.get("/sources/{source_id}/who-was-that", response_model=WhoWasThatResponse)
def who(
    source_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
    timestamp: float = Query(ge=0),
) -> WhoWasThatResponse:
    return who_was_that(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=active_profile_id(session),
        timestamp=timestamp,
    )


@router.get(
    "/sources/{source_id}/relationship-graph",
    response_model=RelationshipGraphResponse,
)
def graph(
    source_id: uuid.UUID,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
    timestamp: float = Query(ge=0),
) -> RelationshipGraphResponse:
    return relationship_graph(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=active_profile_id(session),
        timestamp=timestamp,
    )


@router.post("/sources/{source_id}/what-did-i-miss", response_model=WhatDidIMissResponse)
def missed(
    source_id: uuid.UUID,
    payload: MissedIntervalRequest,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
) -> WhatDidIMissResponse:
    return what_did_i_miss(
        db,
        playback_source=playable_source(db, source_id, country),
        profile_id=active_profile_id(session),
        start=payload.start_seconds,
        end=payload.end_seconds,
        current_timestamp=payload.current_timestamp,
    )


def validate_lens_item(
    db: DbSession,
    source_id: uuid.UUID,
    scene_id: uuid.UUID | None,
    at: float,
    country: str | None,
):
    source = playable_source(db, source_id, country)
    duration = float(source.processing_job.duration_seconds or 0)
    if not 0 <= at <= duration:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Timestamp exceeds playback")
    if scene_id is not None:
        scene = db.scalar(
            select(Scene)
            .join(SceneIntelligenceVersion, SceneIntelligenceVersion.id == Scene.version_id)
            .where(
                Scene.id == scene_id,
                SceneIntelligenceVersion.playback_source_id == source.id,
                Scene.start_seconds <= at,
                Scene.end_seconds >= at,
            )
        )
        if scene is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "Scene does not contain this timestamp for the playback source",
            )
    return source


@router.post(
    "/sources/{source_id}/bookmarks",
    response_model=LensBookmarkResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_bookmark(
    source_id: uuid.UUID,
    payload: LensBookmarkCreate,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
):
    validate_lens_item(db, source_id, payload.scene_id, payload.timestamp_seconds, country)
    item = SceneBookmark(
        profile_id=active_profile_id(session), playback_source_id=source_id, **payload.model_dump()
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.post(
    "/sources/{source_id}/notes",
    response_model=LensNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_note(
    source_id: uuid.UUID,
    payload: LensNoteCreate,
    db: DbSession,
    session: ViewerSession,
    country: OptionalViewerCountry,
):
    validate_lens_item(db, source_id, payload.scene_id, payload.timestamp_seconds, country)
    item = SceneNote(
        profile_id=active_profile_id(session), playback_source_id=source_id, **payload.model_dump()
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


@router.delete("/bookmarks/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookmark(item_id: uuid.UUID, db: DbSession, session: ViewerSession) -> Response:
    item = db.scalar(
        select(SceneBookmark).where(
            SceneBookmark.id == item_id,
            SceneBookmark.profile_id == active_profile_id(session),
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Bookmark was not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/notes/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_note(item_id: uuid.UUID, db: DbSession, session: ViewerSession) -> Response:
    item = db.scalar(
        select(SceneNote).where(
            SceneNote.id == item_id,
            SceneNote.profile_id == active_profile_id(session),
        )
    )
    if item is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Note was not found")
    db.delete(item)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
