import uuid

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models import PlaybackSource
from app.spoiler_schemas import (
    AskEvidence,
    SpoilerContextResponse,
    WhatDidIMissResponse,
    WhoCharacter,
    WhoWasThatResponse,
)
from app.spoiler_service import spoiler_context

UNAVAILABLE_RECAP = "No approved completed-scene recap is available for that watched interval."


def who_from_context(context: SpoilerContextResponse) -> WhoWasThatResponse:
    scene_id = context.current_scene.id if context.current_scene else None
    character_facts = [
        fact
        for fact in context.facts
        if fact.kind == "character"
        and fact.scene_id == scene_id
        and fact.reveal_seconds <= context.effective_cutoff
    ]
    entity_names = {
        str(fact.id): str(fact.payload["name"])
        for fact in context.facts
        if fact.kind == "entity"
        and fact.scene_id == scene_id
        and fact.reveal_seconds <= context.effective_cutoff
    }
    relationships = []
    for fact in context.facts:
        if (
            fact.kind != "relationship"
            or fact.scene_id != scene_id
            or fact.reveal_seconds > context.effective_cutoff
        ):
            continue
        subject = entity_names.get(str(fact.payload["subject_entity_id"]))
        object_ = entity_names.get(str(fact.payload["object_entity_id"]))
        if subject and object_:
            relationships.append(f"{subject} {fact.payload['relationship']} {object_}")
    characters = [
        WhoCharacter(
            character_id=fact.payload["character_id"],
            character_name=str(fact.payload["character_name"]),
            actor_name=str(fact.payload["actor_name"]) if fact.payload.get("actor_name") else None,
            prior_appearance_seconds=[
                float(value) for value in fact.payload.get("prior_appearance_seconds", [])
            ],
            summary=str(fact.payload["summary"]),
        )
        for fact in character_facts
    ]
    return WhoWasThatResponse(
        characters=characters,
        known_relationships=relationships,
        confidence="supported" if characters else "unavailable",
        uncertainty=None
        if characters
        else (
            "No adequately verified character is available in the current scene at this timestamp."
        ),
        safety_state=context.safety_state,
    )


def missed_from_context(
    context: SpoilerContextResponse, start: float, end: float
) -> WhatDidIMissResponse:
    scenes = [
        fact
        for fact in context.facts
        if fact.kind == "scene" and start < fact.reveal_seconds <= end
    ]
    recap = " ".join(str(fact.payload["summary"]) for fact in scenes)
    return WhatDidIMissResponse(
        start_seconds=start,
        end_seconds=end,
        recap=recap or UNAVAILABLE_RECAP,
        confidence="supported" if scenes else "unavailable",
        uncertainty=None
        if scenes
        else "Only completed scenes with approved summaries can be recapped.",
        evidence=[AskEvidence(kind="scene", reveal_seconds=fact.reveal_seconds) for fact in scenes],
        safety_state=context.safety_state,
    )


def who_was_that(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    timestamp: float,
) -> WhoWasThatResponse:
    context = spoiler_context(
        db,
        playback_source=playback_source,
        profile_id=profile_id,
        timestamp=timestamp,
        mode="protected",
    )
    return who_from_context(context)


def what_did_i_miss(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    start: float,
    end: float,
    current_timestamp: float,
) -> WhatDidIMissResponse:
    if end <= start:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "Interval end must follow start")
    if end > current_timestamp:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Missed interval cannot extend beyond the current playback timestamp",
        )
    if end - start > 900:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "Missed interval cannot exceed 15 minutes"
        )
    context = spoiler_context(
        db,
        playback_source=playback_source,
        profile_id=profile_id,
        timestamp=current_timestamp,
        mode="protected",
    )
    return missed_from_context(context, start, end)
