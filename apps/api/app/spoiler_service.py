import math
import uuid
from collections import Counter

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.catalog_models import Character, Credit, Person
from app.models import PlaybackSource, SceneBookmark, SceneNote, ViewingActivity
from app.scene_models import (
    IntelligenceVersionState,
    MusicCue,
    ProductionNote,
    Scene,
    SceneCharacter,
    SceneEntity,
    SceneIntelligenceVersion,
    SceneRelationship,
    SceneSource,
    SpoilerBoundary,
    TranscriptCue,
)
from app.spoiler_schemas import CurrentScene, SpoilerContextResponse, SpoilerFact


def finite_range(value: float, duration: float) -> bool:
    return math.isfinite(value) and 0 <= value <= duration


def record_payload(record, *fields: str) -> dict:
    return {field: getattr(record, field) for field in fields}


def safe_payload(value) -> bool:
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, dict):
        return all(safe_payload(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return all(safe_payload(item) for item in value)
    return True


def spoiler_context(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    timestamp: float,
    mode: str,
) -> SpoilerContextResponse:
    duration = float(playback_source.processing_job.duration_seconds or 0)
    if not math.isfinite(timestamp) or not finite_range(timestamp, duration):
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "Playback timestamp must be finite and within the source duration",
        )
    completion_unlock = (
        db.scalar(
            select(ViewingActivity.id).where(
                ViewingActivity.profile_id == profile_id,
                ViewingActivity.playback_source_id == playback_source.id,
                ViewingActivity.completed.is_(True),
            )
        )
        is not None
    )
    if mode == "full" and not completion_unlock:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Full-spoiler mode unlocks only after this profile completes the title",
        )
    cutoff = duration if mode == "full" else timestamp
    bookmarks = list(
        db.scalars(
            select(SceneBookmark)
            .where(
                SceneBookmark.profile_id == profile_id,
                SceneBookmark.playback_source_id == playback_source.id,
            )
            .order_by(SceneBookmark.created_at.desc())
        )
    )
    notes = list(
        db.scalars(
            select(SceneNote)
            .where(
                SceneNote.profile_id == profile_id,
                SceneNote.playback_source_id == playback_source.id,
            )
            .order_by(SceneNote.created_at.desc())
        )
    )
    version = db.scalar(
        select(SceneIntelligenceVersion).where(
            SceneIntelligenceVersion.playback_source_id == playback_source.id,
            SceneIntelligenceVersion.state == IntelligenceVersionState.published,
        )
    )
    if version is None:
        return SpoilerContextResponse(
            playback_source_id=playback_source.id,
            version_id=None,
            mode=mode,
            requested_timestamp=timestamp,
            effective_cutoff=cutoff,
            completion_unlock=completion_unlock,
            facts=[],
            bookmarks=bookmarks,
            notes=notes,
            withheld={},
            safety_state="no_published_evidence",
        )

    source_ids = set(db.scalars(select(SceneSource.id).where(SceneSource.version_id == version.id)))
    scenes = list(
        db.scalars(select(Scene).where(Scene.version_id == version.id).order_by(Scene.ordinal))
    )
    valid_scenes: dict[uuid.UUID, Scene] = {}
    malformed = False
    withheld: Counter[str] = Counter()
    facts: list[SpoilerFact] = []
    current_scene = None

    def include(kind: str, record, reveal: float, payload: dict, scene_id=None) -> None:
        nonlocal malformed
        if (
            record.source_id not in source_ids
            or not finite_range(reveal, duration)
            or not safe_payload(payload)
        ):
            malformed = True
            withheld[f"{kind}_malformed"] += 1
            return
        if reveal > cutoff:
            withheld[kind] += 1
            return
        facts.append(
            SpoilerFact(
                id=record.id,
                kind=kind,
                scene_id=scene_id,
                reveal_seconds=reveal,
                payload=payload,
            )
        )

    for scene in scenes:
        valid = (
            scene.source_id in source_ids
            and finite_range(scene.start_seconds, duration)
            and finite_range(scene.end_seconds, duration)
            and scene.end_seconds > scene.start_seconds
            and math.isfinite(scene.confidence)
            and 0 <= scene.confidence <= 1
        )
        if not valid:
            malformed = True
            withheld["scene_malformed"] += 1
            continue
        valid_scenes[scene.id] = scene
        if scene.start_seconds <= timestamp <= scene.end_seconds:
            current_scene = CurrentScene(
                id=scene.id,
                ordinal=scene.ordinal,
                title=scene.title,
                start_seconds=scene.start_seconds,
                end_seconds=scene.end_seconds,
            )
        include(
            "scene",
            scene,
            scene.end_seconds,
            record_payload(scene, "ordinal", "title", "summary", "confidence"),
            scene.id,
        )

    character_records = list(
        db.scalars(
            select(SceneCharacter)
            .join(Scene, SceneCharacter.scene_id == Scene.id)
            .where(Scene.version_id == version.id)
        )
    )
    for record in character_records:
        character = db.get(Character, record.character_id)
        credit = db.scalar(
            select(Credit).where(
                Credit.character_id == record.character_id,
                Credit.movie_id == playback_source.movie_id
                if playback_source.movie_id
                else Credit.episode_id == playback_source.episode_id,
            )
        )
        actor = db.get(Person, credit.person_id) if credit else None
        prior = sorted(
            {
                item.reveal_seconds
                for item in character_records
                if item.character_id == record.character_id
                and item.scene_id in valid_scenes
                and finite_range(item.reveal_seconds, duration)
                and item.reveal_seconds <= min(cutoff, record.reveal_seconds)
            }
        )
        if character is None or record.scene_id not in valid_scenes:
            malformed = True
            withheld["character_malformed"] += 1
            continue
        include(
            "character",
            record,
            record.reveal_seconds,
            {
                "character_id": record.character_id,
                "character_name": character.name,
                "actor_name": actor.name if actor else None,
                "prior_appearance_seconds": prior[:-1],
                "summary": f"Seen in {len(prior)} spoiler-safe scene appearance(s) so far.",
                "confidence": record.confidence,
                "manually_verified": record.manually_verified,
            },
            record.scene_id,
        )

    timed = (
        (
            "entity",
            SceneEntity,
            ("entity_type", "name", "canonical_key", "description", "confidence"),
        ),
        (
            "production_note",
            ProductionNote,
            ("category", "note"),
        ),
    )
    for kind, model, fields in timed:
        records = db.scalars(
            select(model)
            .join(Scene, model.scene_id == Scene.id)
            .where(Scene.version_id == version.id)
        )
        for record in records:
            if record.scene_id not in valid_scenes:
                malformed = True
                withheld[f"{kind}_malformed"] += 1
                continue
            include(
                kind,
                record,
                record.reveal_seconds,
                record_payload(record, *fields),
                record.scene_id,
            )

    entities = {
        item.id: item
        for item in db.scalars(
            select(SceneEntity)
            .join(Scene, SceneEntity.scene_id == Scene.id)
            .where(Scene.version_id == version.id)
        )
    }
    relationships = db.scalars(
        select(SceneRelationship)
        .join(Scene, SceneRelationship.scene_id == Scene.id)
        .where(Scene.version_id == version.id)
    )
    for record in relationships:
        subject = entities.get(record.subject_entity_id)
        object_ = entities.get(record.object_entity_id)
        valid = (
            record.scene_id in valid_scenes
            and subject is not None
            and object_ is not None
            and subject.scene_id == record.scene_id
            and object_.scene_id == record.scene_id
            and subject.source_id in source_ids
            and object_.source_id in source_ids
            and finite_range(subject.reveal_seconds, duration)
            and finite_range(object_.reveal_seconds, duration)
        )
        if not valid:
            malformed = True
            withheld["relationship_malformed"] += 1
            continue
        reveal = max(record.reveal_seconds, subject.reveal_seconds, object_.reveal_seconds)
        include(
            "relationship",
            record,
            reveal,
            {
                "subject_entity_id": record.subject_entity_id,
                "object_entity_id": record.object_entity_id,
                "relationship": record.relationship,
                "confidence": record.confidence,
            },
            record.scene_id,
        )

    for cue in db.scalars(
        select(MusicCue)
        .join(Scene, MusicCue.scene_id == Scene.id)
        .where(Scene.version_id == version.id)
    ):
        if cue.scene_id not in valid_scenes or not finite_range(cue.end_seconds, duration):
            malformed = True
            withheld["music_cue_malformed"] += 1
            continue
        include(
            "music_cue",
            cue,
            cue.start_seconds,
            record_payload(cue, "title", "composer", "performer", "end_seconds"),
            cue.scene_id,
        )

    for boundary in db.scalars(
        select(SpoilerBoundary).where(SpoilerBoundary.version_id == version.id)
    ):
        include(
            "spoiler_boundary",
            boundary,
            boundary.reveal_seconds,
            record_payload(boundary, "label", "description"),
        )

    for cue in db.scalars(select(TranscriptCue).where(TranscriptCue.version_id == version.id)):
        if cue.scene_id is not None and cue.scene_id not in valid_scenes:
            malformed = True
            withheld["transcript_cue_malformed"] += 1
            continue
        include(
            "transcript_cue",
            cue,
            cue.end_seconds,
            record_payload(cue, "text", "speaker_label", "start_seconds", "confidence"),
            cue.scene_id,
        )

    facts.sort(key=lambda item: (item.reveal_seconds, item.kind, str(item.id)))
    return SpoilerContextResponse(
        playback_source_id=playback_source.id,
        version_id=version.id,
        mode=mode,
        requested_timestamp=timestamp,
        effective_cutoff=cutoff,
        completion_unlock=completion_unlock,
        current_scene=current_scene,
        facts=facts,
        bookmarks=bookmarks,
        notes=notes,
        withheld=dict(withheld),
        safety_state="malformed_evidence_omitted" if malformed else "ok",
    )
