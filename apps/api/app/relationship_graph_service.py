import uuid

from sqlalchemy.orm import Session

from app.models import PlaybackSource
from app.spoiler_schemas import (
    RelationshipEdge,
    RelationshipGraphResponse,
    RelationshipNode,
    SpoilerContextResponse,
)
from app.spoiler_service import spoiler_context


def graph_from_context(context: SpoilerContextResponse) -> RelationshipGraphResponse:
    entity_keys: dict[str, str] = {}
    nodes: dict[str, RelationshipNode] = {}
    current_names = {
        str(fact.payload["character_name"]).casefold()
        for fact in context.facts
        if fact.kind == "character"
        and fact.scene_id == (context.current_scene.id if context.current_scene else None)
        and fact.reveal_seconds <= context.effective_cutoff
    }
    for fact in context.facts:
        if fact.kind != "entity" or fact.reveal_seconds > context.effective_cutoff:
            continue
        key = str(fact.payload.get("canonical_key") or fact.id)
        label = str(fact.payload["name"])
        entity_keys[str(fact.id)] = key
        previous = nodes.get(key)
        nodes[key] = RelationshipNode(
            id=key,
            label=label,
            entity_type=str(fact.payload["entity_type"]),
            current_character=label.casefold() in current_names
            or bool(previous and previous.current_character),
            first_reveal_seconds=min(
                fact.reveal_seconds,
                previous.first_reveal_seconds if previous else fact.reveal_seconds,
            ),
        )
    edges = []
    for fact in context.facts:
        if fact.kind != "relationship" or fact.reveal_seconds > context.effective_cutoff:
            continue
        source = entity_keys.get(str(fact.payload["subject_entity_id"]))
        target = entity_keys.get(str(fact.payload["object_entity_id"]))
        if source and target:
            edges.append(
                RelationshipEdge(
                    id=fact.id,
                    source=source,
                    target=target,
                    label=str(fact.payload["relationship"]),
                    reveal_seconds=fact.reveal_seconds,
                )
            )
    used = {edge.source for edge in edges} | {edge.target for edge in edges}
    return RelationshipGraphResponse(
        nodes=sorted(
            (node for key, node in nodes.items() if key in used or node.current_character),
            key=lambda node: (not node.current_character, node.label.casefold(), node.id),
        ),
        edges=sorted(edges, key=lambda edge: (edge.reveal_seconds, str(edge.id))),
        effective_cutoff=context.effective_cutoff,
        safety_state=context.safety_state,
    )


def relationship_graph(
    db: Session,
    *,
    playback_source: PlaybackSource,
    profile_id: uuid.UUID,
    timestamp: float,
) -> RelationshipGraphResponse:
    context = spoiler_context(
        db,
        playback_source=playback_source,
        profile_id=profile_id,
        timestamp=timestamp,
        mode="protected",
    )
    return graph_from_context(context)
