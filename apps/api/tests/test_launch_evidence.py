import importlib.util
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).parents[3]
SCRIPT = ROOT / "deploy/production/launch_evidence.py"
SPEC = importlib.util.spec_from_file_location("launch_evidence", SCRIPT)
assert SPEC and SPEC.loader
launch_evidence = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(launch_evidence)


def example() -> dict:
    return json.loads((ROOT / "deploy/production/launch-evidence.example.json").read_text())


def test_migration_head_matches_alembic() -> None:
    config = Config()
    config.set_main_option("script_location", str(ROOT / "apps/api/migrations"))
    heads = ScriptDirectory.from_config(config).get_heads()
    assert heads == [launch_evidence.MIGRATION_HEAD]


def production_record() -> dict:
    record = example()
    observed = (datetime.now(UTC) - timedelta(minutes=5)).isoformat()
    record["environment"] = "production"
    record["release"] = {
        "id": "release-2026-08-16.1",
        "infrastructure_version": "digitalocean-app-spec-2026-08-16.1",
        "deployed_at": observed,
        "migration_head": launch_evidence.MIGRATION_HEAD,
        "image_digests": {
            component: f"sha256:{index:064x}"
            for index, component in enumerate(
                (
                    "web",
                    "api",
                    "media_worker",
                    "backup",
                    "caddy",
                    "storage",
                    "node_exporter",
                    "blackbox",
                ),
                start=1,
            )
        },
    }
    record["release"]["image_digests"]["scene_worker"] = record["release"][
        "image_digests"
    ]["api"]
    for gate_name, required in launch_evidence.REQUIRED_GATES.items():
        record["gates"][gate_name] = {
            "status": "pass",
            "owner": f"{gate_name} owner",
            "approved_by": f"{gate_name} approver",
            "approved_at": observed,
            "evidence": [
                {"kind": kind, "reference": f"evidence/{gate_name}/{kind}", "observed_at": observed}
                for kind in sorted(required)
            ],
        }
    return record


def test_dummy_record_is_valid_but_can_never_be_launch_ready() -> None:
    result = launch_evidence.validate(example(), dummy=True)
    assert result["status"] == "no_go"
    assert result["passed_gates"] == []
    assert result["human_approval_required"] is True


def test_complete_production_evidence_still_requires_human_approval() -> None:
    result = launch_evidence.validate(production_record(), dummy=False)
    assert result["status"] == "evidence_complete"
    assert result["remaining_gates"] == []
    assert result["human_approval_required"] is True


def test_scene_worker_may_bind_to_the_ffmpeg_free_api_digest() -> None:
    record = production_record()
    record["release"]["image_digests"]["scene_worker"] = record["release"]["image_digests"]["api"]

    result = launch_evidence.validate(record, dummy=False)

    assert result["status"] == "evidence_complete"


def test_scene_worker_must_bind_to_the_api_digest() -> None:
    record = production_record()
    record["release"]["image_digests"]["scene_worker"] = "sha256:" + "f" * 64

    with pytest.raises(launch_evidence.EvidenceError, match="Scene worker"):
        launch_evidence.validate(record, dummy=False)


def test_eight_built_artifact_digests_must_be_distinct() -> None:
    record = production_record()
    record["release"]["image_digests"]["storage"] = record["release"][
        "image_digests"
    ]["caddy"]

    with pytest.raises(launch_evidence.EvidenceError, match="artifact image digests"):
        launch_evidence.validate(record, dummy=False)


def test_pass_gate_fails_when_required_evidence_is_missing() -> None:
    record = production_record()
    record["gates"]["recovery"]["evidence"] = []
    with pytest.raises(launch_evidence.EvidenceError, match="isolated_restore"):
        launch_evidence.validate(record, dummy=False)


@pytest.mark.parametrize("unsafe", ["sk_live_example", "token=owner-token", "DUMMY_REFERENCE"])
def test_production_record_rejects_secrets_and_dummy_markers(unsafe: str) -> None:
    record = production_record()
    record["gates"]["observability"]["evidence"][0]["reference"] = unsafe
    with pytest.raises(launch_evidence.EvidenceError):
        launch_evidence.validate(record, dummy=False)


def test_machine_record_cannot_claim_final_approval() -> None:
    record = production_record()
    record["decision"] = "approved"
    with pytest.raises(launch_evidence.EvidenceError, match="pending_human_approval"):
        launch_evidence.validate(record, dummy=False)
