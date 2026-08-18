import uuid

from app.moment_service import missed_from_context, who_from_context
from app.relationship_graph_service import graph_from_context
from app.spoiler_schemas import CurrentScene, SpoilerContextResponse, SpoilerFact


def dense_ensemble_context() -> SpoilerContextResponse:
    source_id, version_id, scene_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    entities = [(uuid.uuid4(), name) for name in ("Mara", "Ivo", "Sable", "Niko")]
    facts = []
    for index, (entity_id, name) in enumerate(entities):
        facts.append(
            SpoilerFact(
                id=entity_id,
                kind="entity",
                scene_id=scene_id,
                reveal_seconds=42 + index,
                payload={
                    "name": name,
                    "canonical_key": name.casefold(),
                    "entity_type": "character",
                },
            )
        )
        facts.append(
            SpoilerFact(
                id=uuid.uuid4(),
                kind="character",
                scene_id=scene_id,
                reveal_seconds=42 + index,
                payload={
                    "character_id": uuid.uuid4(),
                    "character_name": name,
                    "actor_name": f"Actor {index + 1}",
                    "prior_appearance_seconds": [5.0, 18.0] if index == 0 else [],
                    "summary": (
                        f"Seen in {3 if index == 0 else 1} spoiler-safe scene appearance(s) so far."
                    ),
                },
            )
        )
    facts.append(
        SpoilerFact(
            id=uuid.uuid4(),
            kind="relationship",
            scene_id=scene_id,
            reveal_seconds=45,
            payload={
                "subject_entity_id": entities[0][0],
                "object_entity_id": entities[1][0],
                "relationship": "distrusts",
            },
        )
    )
    facts.append(
        SpoilerFact(
            id=uuid.uuid4(),
            kind="relationship",
            scene_id=scene_id,
            reveal_seconds=75,
            payload={
                "subject_entity_id": entities[2][0],
                "object_entity_id": entities[3][0],
                "relationship": "secretly protects",
            },
        )
    )
    for reveal, summary in (
        (20, "The first clue is recovered."),
        (50, "The group reaches the archive."),
        (70, "A later reveal."),
    ):
        facts.append(
            SpoilerFact(
                id=uuid.uuid4(),
                kind="scene",
                scene_id=uuid.uuid4(),
                reveal_seconds=reveal,
                payload={"summary": summary},
            )
        )
    return SpoilerContextResponse(
        playback_source_id=source_id,
        version_id=version_id,
        mode="protected",
        requested_timestamp=60,
        effective_cutoff=60,
        completion_unlock=False,
        current_scene=CurrentScene(
            id=scene_id, ordinal=3, title="The archive", start_seconds=40, end_seconds=60
        ),
        facts=facts,
        withheld={"scene": 1},
        safety_state="ok",
    )


def test_who_was_that_handles_dense_ensemble_without_future_relationships() -> None:
    result = who_from_context(dense_ensemble_context())
    assert [item.character_name for item in result.characters] == ["Mara", "Ivo", "Sable", "Niko"]
    assert result.characters[0].actor_name == "Actor 1"
    assert result.characters[0].prior_appearance_seconds == [5, 18]
    assert result.known_relationships == ["Mara distrusts Ivo"]


def test_what_did_i_miss_uses_only_completed_scenes_inside_interval() -> None:
    result = missed_from_context(dense_ensemble_context(), 10, 60)
    assert result.recap == "The first clue is recovered. The group reaches the archive."
    assert [item.reveal_seconds for item in result.evidence] == [20, 50]
    assert "later reveal" not in result.recap.lower()


def test_relationship_graph_emphasizes_current_cast_without_future_edges() -> None:
    result = graph_from_context(dense_ensemble_context())
    assert [(node.label, node.current_character) for node in result.nodes] == [
        ("Ivo", True),
        ("Mara", True),
        ("Niko", True),
        ("Sable", True),
    ]
    assert [(edge.source, edge.label, edge.target) for edge in result.edges] == [
        ("mara", "distrusts", "ivo")
    ]
    assert all(edge.reveal_seconds <= result.effective_cutoff for edge in result.edges)
