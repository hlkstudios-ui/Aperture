"""Validate a secret-free production launch evidence record without approving launch."""

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

MIGRATION_HEAD = "20260830_0032"
RECORD_VERSION = 2
IMAGE_DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
REQUIRED_GATES = {
    "production_admin": {"admin_mfa_enrollment", "recovery_login", "admin_acceptance"},
    "infrastructure_cdn": {
        "provider_resources", "dns_tls", "public_edge", "cdn_authorization",
        "authenticated_media_acceptance", "billing_acceptance", "smtp_acceptance",
        "customer_data_acceptance", "browser_matrix",
    },
    "recovery": {"backup_job", "isolated_restore", "rpo_rto"},
    "rollback": {"deployment_active", "traffic_rollback", "post_rollback_acceptance"},
    "observability": {"error_tracking", "alert_delivery", "on_call"},
    "content_legal": {"catalog_rights", "catalog_workflow", "policy_approval"},
}
SECRET_MARKERS = re.compile(
    r"(?i)(sk_(?:live|test)_|whsec_|bearer\s+|password\s*[=:]|token\s*[=:]|secret\s*[=:])"
)


class EvidenceError(ValueError):
    pass


def mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be an object")
    return value


def text(value: Any, label: str, *, dummy: bool) -> str:
    if not isinstance(value, str) or not value.strip():
        raise EvidenceError(f"{label} must be a non-empty string")
    result = value.strip()
    if SECRET_MARKERS.search(result):
        raise EvidenceError(f"{label} appears to contain a secret")
    if not dummy and "DUMMY" in result.upper():
        raise EvidenceError(f"{label} contains a dummy marker")
    return result


def timestamp(value: Any, label: str, *, dummy: bool) -> datetime:
    raw = text(value, label, dummy=dummy)
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as error:
        raise EvidenceError(f"{label} must be an ISO-8601 timestamp") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EvidenceError(f"{label} must include a timezone")
    if not dummy and parsed.astimezone(UTC) > datetime.now(UTC):
        raise EvidenceError(f"{label} must not be in the future")
    return parsed


def validate_release(record: dict[str, Any], *, dummy: bool) -> None:
    release = mapping(record.get("release"), "release")
    text(release.get("id"), "release.id", dummy=dummy)
    text(release.get("infrastructure_version"), "release.infrastructure_version", dummy=dummy)
    timestamp(release.get("deployed_at"), "release.deployed_at", dummy=dummy)
    if release.get("migration_head") != MIGRATION_HEAD:
        raise EvidenceError(f"release.migration_head must equal {MIGRATION_HEAD}")
    digests = mapping(release.get("image_digests"), "release.image_digests")
    components = {
        "web",
        "api",
        "media_worker",
        "scene_worker",
        "backup",
        "caddy",
        "storage",
        "node_exporter",
        "blackbox",
    }
    if set(digests) != components:
        raise EvidenceError("release.image_digests must match the complete release component set")
    for component in sorted(components):
        digest = text(digests.get(component), f"release.image_digests.{component}", dummy=dummy)
        if not dummy and not IMAGE_DIGEST.fullmatch(digest):
            raise EvidenceError(f"release.image_digests.{component} must be a sha256 digest")
    if digests["scene_worker"] != digests["api"]:
        raise EvidenceError("release Scene worker must bind to the API image digest")
    artifacts = (
        "api",
        "media_worker",
        "web",
        "backup",
        "caddy",
        "storage",
        "node_exporter",
        "blackbox",
    )
    if len({digests[component] for component in artifacts}) != len(artifacts):
        raise EvidenceError("release artifact image digests must be distinct")


def validate_gate(name: str, gate: Any, *, dummy: bool) -> bool:
    value = mapping(gate, f"gates.{name}")
    status = value.get("status")
    if status not in {"pending", "pass"}:
        raise EvidenceError(f"gates.{name}.status must be pending or pass")
    text(value.get("owner"), f"gates.{name}.owner", dummy=dummy)
    evidence = value.get("evidence")
    if not isinstance(evidence, list):
        raise EvidenceError(f"gates.{name}.evidence must be an array")
    kinds: set[str] = set()
    for index, item in enumerate(evidence):
        entry = mapping(item, f"gates.{name}.evidence[{index}]")
        kind = text(entry.get("kind"), f"gates.{name}.evidence[{index}].kind", dummy=dummy)
        if kind in kinds:
            raise EvidenceError(f"gates.{name} contains duplicate evidence kind {kind}")
        kinds.add(kind)
        text(entry.get("reference"), f"gates.{name}.evidence[{index}].reference", dummy=dummy)
        timestamp(entry.get("observed_at"), f"gates.{name}.evidence[{index}].observed_at", dummy=dummy)
    if status == "pass":
        missing = sorted(REQUIRED_GATES[name] - kinds)
        if missing:
            raise EvidenceError(f"gates.{name} is pass but lacks: {', '.join(missing)}")
        text(value.get("approved_by"), f"gates.{name}.approved_by", dummy=dummy)
        timestamp(value.get("approved_at"), f"gates.{name}.approved_at", dummy=dummy)
    return status == "pass"


def validate(record: Any, *, dummy: bool) -> dict[str, Any]:
    root = mapping(record, "record")
    if root.get("record_version") != RECORD_VERSION:
        raise EvidenceError(f"record_version must equal {RECORD_VERSION}")
    expected_environment = "dummy" if dummy else "production"
    if root.get("environment") != expected_environment:
        raise EvidenceError(f"environment must equal {expected_environment}")
    if root.get("decision") != "pending_human_approval":
        raise EvidenceError("decision must remain pending_human_approval")
    validate_release(root, dummy=dummy)
    gates = mapping(root.get("gates"), "gates")
    if set(gates) != set(REQUIRED_GATES):
        missing = sorted(set(REQUIRED_GATES) - set(gates))
        extra = sorted(set(gates) - set(REQUIRED_GATES))
        raise EvidenceError(f"gates must match contract; missing={missing}, extra={extra}")
    passed = sorted(name for name in REQUIRED_GATES if validate_gate(name, gates[name], dummy=dummy))
    complete = not dummy and len(passed) == len(REQUIRED_GATES)
    return {
        "event": "launch_evidence.validated",
        "status": "evidence_complete" if complete else "no_go",
        "passed_gates": passed,
        "remaining_gates": sorted(set(REQUIRED_GATES) - set(passed)),
        "human_approval_required": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "verify"), required=True)
    parser.add_argument("--record", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = validate(json.loads(args.record.read_text()), dummy=args.mode == "dummy")
    except Exception:
        print(json.dumps({"event": "launch_evidence.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0 if args.mode == "dummy" or result["status"] == "evidence_complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
