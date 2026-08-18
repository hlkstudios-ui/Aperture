import hashlib
import re
import uuid

from sqlalchemy.orm import Session

from app.models import AskMovieLog, PlaybackSource
from app.spoiler_schemas import AskEvidence, AskMovieResponse, SpoilerFact
from app.spoiler_service import spoiler_context

WORD = re.compile(r"[a-z0-9']+")
UNAVAILABLE = (
    "Reliable information is not available from the approved scene evidence at this moment."
)


def intent_for(question: str) -> str:
    terms = set(WORD.findall(question.lower()))
    if terms & {"who", "actor", "person", "character"}:
        return "character"
    if terms & {"song", "music", "score", "composer", "track"}:
        return "music"
    if terms & {"relationship", "related", "know", "knows", "connection"}:
        return "relationship"
    if terms & {"filmed", "camera", "production", "easter", "effect", "effects"}:
        return "production"
    if terms & {"what", "happened", "miss", "recap", "explain"}:
        return "scene"
    return "entity"


def evidence_for(facts: list[SpoilerFact]) -> list[AskEvidence]:
    return [AskEvidence(kind=fact.kind, reveal_seconds=fact.reveal_seconds) for fact in facts]


def answer_from(
    intent: str, facts: list[SpoilerFact], question: str
) -> tuple[str, str, str | None, list[SpoilerFact]]:
    if intent == "character":
        matches = [fact for fact in facts if fact.kind == "character"]
        if matches:
            fact = matches[-1]
            name = str(fact.payload["character_name"])
            actor = fact.payload.get("actor_name")
            answer = f"This is {name}."
            if actor:
                answer += f" {name} is played by {actor}."
            answer += f" {fact.payload['summary']}"
            return answer, "supported", None, [fact]
    elif intent == "music":
        matches = [fact for fact in facts if fact.kind == "music_cue"]
        if matches:
            fact = matches[-1]
            answer = f"The approved cue is {fact.payload['title']}."
            if fact.payload.get("composer"):
                answer += f" It is credited to {fact.payload['composer']}."
            return answer, "supported", None, [fact]
    elif intent == "relationship":
        matches = [fact for fact in facts if fact.kind == "relationship"]
        entities = {str(fact.id): fact for fact in facts if fact.kind == "entity"}
        if matches:
            fact = matches[-1]
            subject = entities.get(str(fact.payload["subject_entity_id"]))
            object_ = entities.get(str(fact.payload["object_entity_id"]))
            if subject and object_:
                answer = (
                    f"The approved relationship is: {subject.payload['name']} "
                    f"{fact.payload['relationship']} {object_.payload['name']}."
                )
                return answer, "supported", None, [subject, object_, fact]
    elif intent == "production":
        matches = [fact for fact in facts if fact.kind == "production_note"]
        if matches:
            fact = matches[-1]
            return str(fact.payload["note"]), "supported", None, [fact]
    elif intent == "scene":
        matches = [fact for fact in facts if fact.kind == "scene"]
        if matches:
            fact = matches[-1]
            return str(fact.payload["summary"]), "supported", None, [fact]
        return (
            UNAVAILABLE,
            "unavailable",
            "The current scene summary has not reached its approved reveal boundary.",
            [],
        )
    else:
        terms = set(WORD.findall(question.lower()))
        matches = [
            fact
            for fact in facts
            if fact.kind == "entity"
            and terms & set(WORD.findall(str(fact.payload.get("name", "")).lower()))
        ]
        if matches:
            fact = matches[-1]
            description = fact.payload.get("description")
            answer = (
                str(description) if description else f"The approved name is {fact.payload['name']}."
            )
            return answer, "supported" if description else "limited", None, [fact]
    return UNAVAILABLE, "unavailable", "No approved fact supports this question.", []


def ask_movie(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    question: str,
    timestamp: float,
    mode: str,
) -> AskMovieResponse:
    context = spoiler_context(
        db,
        playback_source=playback_source,
        profile_id=profile_id,
        timestamp=timestamp,
        mode=mode,
    )
    intent = intent_for(question)
    answer, confidence, uncertainty, used = answer_from(intent, context.facts, question)
    db.add(
        AskMovieLog(
            profile_id=profile_id,
            playback_source_id=playback_source.id,
            version_id=context.version_id,
            timestamp_seconds=timestamp,
            spoiler_mode=mode,
            question_sha256=hashlib.sha256(question.strip().encode()).hexdigest(),
            intent=intent,
            outcome=confidence,
            provenance=[
                {"fact_id": str(fact.id), "kind": fact.kind, "reveal_seconds": fact.reveal_seconds}
                for fact in used
            ],
        )
    )
    db.commit()
    return AskMovieResponse(
        answer=answer,
        intent=intent,
        confidence=confidence,
        uncertainty=uncertainty,
        evidence=evidence_for(used),
        safety_state=context.safety_state,
    )
