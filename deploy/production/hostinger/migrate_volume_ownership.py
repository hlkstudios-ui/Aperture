"""Audit and migrate legacy Caddy/MinIO named-volume ownership safely."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parent
DEFAULT_ENV = ROOT.parents[2] / ".env"
DEFAULT_COMPOSE = ROOT / "compose.yml"

EXPECTED_PROJECT = "aperture-production"
EXPECTED_UID = 65532
EXPECTED_GID = 65532
TARGET_VOLUMES = {
    "caddy-config": "aperture-production_caddy-config",
    "caddy-data": "aperture-production_caddy-data",
    "minio-data": "aperture-production_minio-data",
}
SERVICE_VOLUMES = {
    "caddy": {
        "/config": TARGET_VOLUMES["caddy-config"],
        "/data": TARGET_VOLUMES["caddy-data"],
    },
    "minio": {"/data": TARGET_VOLUMES["minio-data"]},
}

# A tag is intentionally insufficient here. Pull this exact manifest before the
# maintenance window; every helper run below uses --pull=never.
HELPER_IMAGE = (
    "docker.io/library/busybox@sha256:"
    "8d7b1636e974e0adfd8d945955fca609304f0a56c18799dfd032d6e661382d84"
)
MAX_SNAPSHOT_AGE = timedelta(hours=24)
MAX_FUTURE_SKEW = timedelta(minutes=5)
CONFIRMATION = "MIGRATE_APERTURE_CADDY_MINIO_VOLUMES_TO_UID_65532"
IMAGE_DIGEST = re.compile(r"^.+@sha256:[0-9a-f]{64}$")


class MigrationError(ValueError):
    """An expected safety condition was not met."""


def is_placeholder(value: str) -> bool:
    normalized = value.upper()
    return any(marker in normalized for marker in ("DUMMY", "PLACEHOLDER", "REPLACE"))


def run_command(command: list[str], *, check: bool = True) -> str:
    """Run a local Docker command without echoing captured output or secrets."""
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if check and completed.returncode != 0:
        raise MigrationError(f"command failed: {command[0]} {command[1]}")
    return completed.stdout


def compose_command(env_file: Path, compose_file: Path) -> list[str]:
    return [
        "docker",
        "compose",
        "--env-file",
        str(env_file),
        "-f",
        str(compose_file),
    ]


def load_compose_model(env_file: Path, compose_file: Path) -> dict[str, Any]:
    raw = run_command(
        compose_command(env_file, compose_file) + ["config", "--format", "json"]
    )
    try:
        model = json.loads(raw)
    except json.JSONDecodeError as error:
        raise MigrationError("Docker Compose did not return valid JSON") from error
    if not isinstance(model, dict):
        raise MigrationError("Docker Compose returned an invalid model")
    validate_compose_targets(model)
    return model


def validate_compose_targets(model: dict[str, Any]) -> None:
    if model.get("name") != EXPECTED_PROJECT:
        raise MigrationError(f"Compose project must be exactly {EXPECTED_PROJECT}")
    volumes = model.get("volumes")
    if not isinstance(volumes, dict):
        raise MigrationError("Compose model has no named volumes")
    for logical_name, exact_name in TARGET_VOLUMES.items():
        declaration = volumes.get(logical_name)
        if not isinstance(declaration, dict) or declaration.get("name") != exact_name:
            raise MigrationError(
                f"Compose volume {logical_name} must resolve to {exact_name}"
            )


def existing_target_volumes() -> set[str]:
    names = {
        line.strip()
        for line in run_command(["docker", "volume", "ls", "--format", "{{.Name}}"])
        .splitlines()
        if line.strip()
    }
    expected = set(TARGET_VOLUMES.values())
    existing = expected & names
    if existing and existing != expected:
        missing = sorted(expected - existing)
        raise MigrationError(
            "partial managed volume set; refusing migration (missing: "
            + ", ".join(missing)
            + ")"
        )
    return existing


def ensure_project_stopped() -> None:
    running = run_command(
        [
            "docker",
            "ps",
            "--quiet",
            "--filter",
            f"label=com.docker.compose.project={EXPECTED_PROJECT}",
        ]
    )
    if running.strip():
        raise MigrationError("the aperture-production Compose project must be stopped")


def inspect_and_validate_volumes(*, require_unmounted: bool = True) -> None:
    for logical_name, exact_name in TARGET_VOLUMES.items():
        raw = run_command(["docker", "volume", "inspect", exact_name])
        try:
            records = json.loads(raw)
        except json.JSONDecodeError as error:
            raise MigrationError(f"invalid Docker inspection for {logical_name}") from error
        if not isinstance(records, list) or len(records) != 1:
            raise MigrationError(f"unexpected Docker inspection for {logical_name}")
        record = records[0]
        labels = record.get("Labels") if isinstance(record, dict) else None
        if record.get("Name") != exact_name or not isinstance(labels, dict):
            raise MigrationError(f"volume identity mismatch for {logical_name}")
        if labels.get("com.docker.compose.project") != EXPECTED_PROJECT:
            raise MigrationError(f"volume project label mismatch for {logical_name}")
        if labels.get("com.docker.compose.volume") != logical_name:
            raise MigrationError(f"volume logical label mismatch for {logical_name}")
        if require_unmounted:
            mounted_by = run_command(
                ["docker", "ps", "--quiet", "--filter", f"volume={exact_name}"]
            )
            if mounted_by.strip():
                raise MigrationError(
                    f"volume is still mounted by a container: {logical_name}"
                )


def ensure_helper_present() -> None:
    if not IMAGE_DIGEST.fullmatch(HELPER_IMAGE):
        raise MigrationError("ownership helper is not pinned by sha256 digest")
    run_command(["docker", "image", "inspect", HELPER_IMAGE])


def helper_run(
    volume_name: str,
    shell: str,
    *,
    read_only_volume: bool,
    user: str | None = None,
    mutation_capabilities: bool = False,
) -> None:
    mount = f"type=volume,src={volume_name},dst=/volume"
    if read_only_volume:
        mount += ",readonly"
    command = [
        "docker",
        "run",
        "--rm",
        "--pull=never",
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
    ]
    if mutation_capabilities:
        command.extend(
            ["--cap-add=CHOWN", "--cap-add=DAC_OVERRIDE", "--cap-add=FOWNER"]
        )
    if user is not None:
        command.extend(["--user", user])
    command.extend(["--mount", mount, HELPER_IMAGE, "sh", "-ec", shell])
    run_command(command)


def ownership_is_correct(volume_name: str) -> bool:
    try:
        helper_run(
            volume_name,
            (
                'test "$(stat -c %u:%g /volume)" = "65532:65532"; '
                "test -z \"$(find /volume -xdev "
                "\\( ! -user 65532 -o ! -group 65532 \\) -print -quit)\""
            ),
            read_only_volume=True,
        )
    except MigrationError:
        return False
    return True


def audit_ownership() -> list[str]:
    return [
        logical_name
        for logical_name, volume_name in TARGET_VOLUMES.items()
        if not ownership_is_correct(volume_name)
    ]


def read_literal_env(path: Path, label: str) -> str:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise MigrationError(f"invalid runtime environment line {number}")
        key, value = line.split("=", 1)
        if key in values:
            raise MigrationError(f"duplicate runtime label: {key}")
        values[key] = value
    value = values.get(label, "")
    if not value:
        raise MigrationError(f"missing runtime label: {label}")
    return value


def parse_utc(value: object) -> datetime:
    if not isinstance(value, str):
        raise MigrationError("snapshot verified_at must be an RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise MigrationError("snapshot verified_at must be an RFC3339 timestamp") from error
    if parsed.tzinfo is None:
        raise MigrationError("snapshot verified_at must include a timezone")
    return parsed.astimezone(timezone.utc)


def validate_snapshot_evidence(
    path: Path,
    *,
    expected_hostname: str,
    now: datetime | None = None,
) -> None:
    if path.is_symlink() or not path.is_file():
        raise MigrationError("snapshot evidence must be a regular non-symlink file")
    metadata = path.stat()
    if os.name != "nt":
        if metadata.st_uid != 0:
            raise MigrationError("snapshot evidence must be owned by root")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MigrationError("snapshot evidence must not be group/world accessible")
    try:
        evidence = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise MigrationError("snapshot evidence is not valid JSON") from error
    if not isinstance(evidence, dict):
        raise MigrationError("snapshot evidence must be a JSON object")
    expected = {
        "schema_version": 1,
        "provider": "hostinger",
        "status": "ready",
        "hostname": expected_hostname,
        "compose_project": EXPECTED_PROJECT,
        "volumes": sorted(TARGET_VOLUMES.values()),
    }
    for label, value in expected.items():
        if evidence.get(label) != value:
            raise MigrationError(f"snapshot evidence mismatch: {label}")
    snapshot_id = evidence.get("snapshot_id")
    verified_by = evidence.get("verified_by")
    if (
        not isinstance(snapshot_id, str)
        or len(snapshot_id.strip()) < 8
        or is_placeholder(snapshot_id)
    ):
        raise MigrationError("snapshot evidence requires a non-placeholder snapshot_id")
    if (
        not isinstance(verified_by, str)
        or len(verified_by.strip()) < 3
        or is_placeholder(verified_by)
    ):
        raise MigrationError("snapshot evidence requires a non-placeholder verified_by")
    checked_at = parse_utc(evidence.get("verified_at"))
    current = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if checked_at > current + MAX_FUTURE_SKEW:
        raise MigrationError("snapshot verification timestamp is in the future")
    if current - checked_at > MAX_SNAPSHOT_AGE:
        raise MigrationError("snapshot verification is older than 24 hours")


def migrate_ownership() -> None:
    for volume_name in TARGET_VOLUMES.values():
        helper_run(
            volume_name,
            "chown -R 65532:65532 /volume && sync",
            read_only_volume=False,
            mutation_capabilities=True,
        )
    incorrect = audit_ownership()
    if incorrect:
        raise MigrationError(
            "post-migration ownership audit failed: " + ", ".join(incorrect)
        )
    for volume_name in TARGET_VOLUMES.values():
        helper_run(
            volume_name,
            (
                "probe=/volume/.aperture-uid-65532-write-probe; umask 077; "
                ': > "$probe"; '
                'test "$(stat -c %u:%g "$probe")" = "65532:65532"; '
                'rm -f -- "$probe"'
            ),
            read_only_volume=False,
            user="65532:65532",
        )


def verify_started_services(
    env_file: Path, compose_file: Path, model: dict[str, Any]
) -> None:
    for service, expected_mounts in SERVICE_VOLUMES.items():
        ids = run_command(
            compose_command(env_file, compose_file)
            + ["ps", "--all", "--quiet", service]
        ).split()
        if len(ids) != 1:
            raise MigrationError(f"expected exactly one {service} container")
        raw = run_command(["docker", "inspect", ids[0]])
        try:
            records = json.loads(raw)
        except json.JSONDecodeError as error:
            raise MigrationError(f"invalid container inspection for {service}") from error
        if not isinstance(records, list) or len(records) != 1:
            raise MigrationError(f"unexpected container inspection for {service}")
        record = records[0]
        config = record.get("Config", {})
        state = record.get("State", {})
        labels = config.get("Labels", {})
        health = state.get("Health", {})
        if labels.get("com.docker.compose.project") != EXPECTED_PROJECT:
            raise MigrationError(f"{service} project label mismatch")
        if labels.get("com.docker.compose.service") != service:
            raise MigrationError(f"{service} service label mismatch")
        if config.get("Image") != model["services"][service]["image"]:
            raise MigrationError(f"{service} image does not match rendered Compose")
        if config.get("User") not in {"nonroot", "65532", "65532:65532"}:
            raise MigrationError(f"{service} is not configured for UID 65532")
        if state.get("Running") is not True or health.get("Status") != "healthy":
            raise MigrationError(f"{service} is not running and healthy")
        actual_mounts = {
            mount.get("Destination"): mount.get("Name")
            for mount in record.get("Mounts", [])
            if mount.get("Type") == "volume" and mount.get("RW") is True
        }
        if actual_mounts != expected_mounts:
            raise MigrationError(f"{service} volume mounts do not match the contract")


def emit(action: str, status: str) -> None:
    print(json.dumps({"action": action, "status": status}, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "action", choices=("helper-image", "audit", "migrate", "verify-start")
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--compose-file", type=Path, default=DEFAULT_COMPOSE)
    parser.add_argument("--snapshot-evidence", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args(argv)

    if args.action == "helper-image":
        print(HELPER_IMAGE)
        return 0

    try:
        model = load_compose_model(args.input, args.compose_file)
        existing = existing_target_volumes()
        if args.action in {"audit", "migrate"}:
            ensure_project_stopped()
        if not existing:
            if args.action == "verify-start":
                raise MigrationError("managed volume set is absent")
            emit(args.action, "no_op_fresh_volume_set_absent")
            return 0

        inspect_and_validate_volumes(require_unmounted=args.action != "verify-start")
        if args.action == "verify-start":
            verify_started_services(args.input, args.compose_file, model)
            emit(args.action, "healthy_nonroot_services")
            return 0

        ensure_helper_present()
        incorrect = audit_ownership()
        if args.action == "audit":
            if incorrect:
                raise MigrationError(
                    "ownership audit failed for: " + ", ".join(incorrect)
                )
            emit(args.action, "uid_65532")
            return 0

        if not incorrect:
            emit(args.action, "no_op_already_uid_65532")
            return 0
        if os.name != "nt" and os.geteuid() != 0:
            raise MigrationError("migration must run as root")
        if args.confirm != CONFIRMATION:
            raise MigrationError("exact migration confirmation is required")
        if args.snapshot_evidence is None:
            raise MigrationError("snapshot evidence is required")
        validate_snapshot_evidence(
            args.snapshot_evidence,
            expected_hostname=read_literal_env(args.input, "EXPECTED_HOSTNAME"),
        )
        migrate_ownership()
        emit(args.action, "migrated_and_nonroot_write_verified")
        return 0
    except (MigrationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
