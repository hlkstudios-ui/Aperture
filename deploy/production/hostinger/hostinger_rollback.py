"""Inspect or execute an explicit immutable-image Hostinger rollback."""

import argparse
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

from validate_config import image_reference

ROOT = Path(__file__).resolve().parent
CREDENTIALS = ROOT.parents[2] / ".env"
ROLLBACK_INPUT = ROOT.parents[2] / ".env"
PRIVATE_STUDIO_ROOT = ROOT.parent / "private-studio"
PRIVATE_STUDIO_RUNTIME = PRIVATE_STUDIO_ROOT / "runtime.local.env"
PRIVATE_STUDIO_COMPOSE = PRIVATE_STUDIO_ROOT / "compose.yml"
CADDY_COUPLING_VALIDATOR = ROOT / "validate_caddy_coupling.py"
CI_MANAGED_LAYOUT_SENTINELS = (
    Path("/opt/aperture/current"),
    Path("/opt/aperture/shared/production.env"),
    Path("/etc/aperture/production-launch-enabled"),
)
CONFIRMATION = "ROLLBACK_HOSTINGER_APPLICATION_TRAFFIC"
STORAGE_CHANGE_CONFIRMATIONS = {
    "HOSTINGER_ROLLBACK_STORAGE_COMPATIBILITY_CONFIRMATION": (
        "TARGET_STORAGE_IMAGE_DATA_FORMAT_COMPATIBILITY_VERIFIED"
    ),
    "HOSTINGER_ROLLBACK_STORAGE_SNAPSHOT_CONFIRMATION": (
        "PRE_ROLLBACK_STORAGE_SNAPSHOT_VERIFIED"
    ),
    "HOSTINGER_ROLLBACK_STORAGE_CLONE_REHEARSAL_CONFIRMATION": (
        "TARGET_STORAGE_IMAGE_CLONE_REHEARSAL_PASSED"
    ),
}
IMAGE_KEYS = {
    "api": "API_IMAGE",
    "media_worker": "MEDIA_WORKER_IMAGE",
    "web": "WEB_IMAGE",
    "backup": "BACKUP_IMAGE",
    "caddy": "CADDY_IMAGE",
    "storage": "STORAGE_IMAGE",
    "node_exporter": "NODE_EXPORTER_IMAGE",
    "blackbox": "BLACKBOX_IMAGE",
}
TARGET_KEYS = {
    "api": "HOSTINGER_ROLLBACK_API_IMAGE",
    "media_worker": "HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE",
    "web": "HOSTINGER_ROLLBACK_WEB_IMAGE",
    "backup": "HOSTINGER_ROLLBACK_BACKUP_IMAGE",
    "caddy": "HOSTINGER_ROLLBACK_CADDY_IMAGE",
    "storage": "HOSTINGER_ROLLBACK_STORAGE_IMAGE",
    "node_exporter": "HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE",
    "blackbox": "HOSTINGER_ROLLBACK_BLACKBOX_IMAGE",
}


class RollbackExecutionError(RuntimeError):
    """Describe rollback/recovery state without retaining command output or secrets."""

    def __init__(
        self,
        failed_stage: str,
        recovery_status: str,
        recovery_failure_stage: str | None = None,
    ) -> None:
        super().__init__("rollback execution failed")
        self.failed_stage = failed_stage
        self.recovery_status = recovery_status
        self.recovery_failure_stage = recovery_failure_stage


def load(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid line {number}")
        key, value = line.split("=", 1)
        values[key] = value
    return values


def validate_image(value: str, label: str) -> str:
    image_reference(value, label)
    if "dummy" in value.lower() or value.endswith("0" * 64):
        raise ValueError(f"{label} must be a non-dummy immutable image digest")
    return value


def validate_distinct_images(images: dict[str, str], label: str) -> None:
    digests = [value.rsplit("@sha256:", 1)[1] for value in images.values()]
    if len(set(digests)) != len(digests):
        raise ValueError(f"{label} image digests must be distinct")


def validate_storage_change_confirmations(
    rollback: dict[str, str], current: dict[str, str], target: dict[str, str]
) -> None:
    if current["storage"] == target["storage"]:
        return
    if any(
        rollback.get(label) != expected
        for label, expected in STORAGE_CHANGE_CONFIRMATIONS.items()
    ):
        raise RuntimeError(
            "changing STORAGE_IMAGE requires exact compatibility, snapshot, and "
            "clone-rehearsal confirmations"
        )


def reject_ci_managed_layout() -> None:
    """Keep the legacy rollback from mutating controller-owned live state."""

    for path in CI_MANAGED_LAYOUT_SENTINELS:
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise RuntimeError(
                "cannot safely determine whether this is a CI-managed host"
            ) from error
        raise RuntimeError(
            "legacy rollback is disabled on CI-managed hosts; create and push a "
            "reviewed revert commit through the production release controller"
        )


def command_prefix() -> list[str]:
    if (
        subprocess.run(
            ["docker", "compose", "version"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        return ["docker", "compose"]
    if (
        subprocess.run(
            ["docker-compose", "version"], capture_output=True, check=False
        ).returncode
        == 0
    ):
        return ["docker-compose"]
    raise RuntimeError("Docker Compose is unavailable")


def inspect_images(images: dict[str, str]) -> None:
    command = ["docker", "image", "inspect", *images.values()]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)


def atomic_write(path: Path, content: str, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def replace_release(
    path: Path, expected: dict[str, str], replacement: dict[str, str]
) -> None:
    original = path.read_text()
    updated = original
    for component, label in IMAGE_KEYS.items():
        marker = f"{label}={expected[component]}"
        if updated.count(marker) != 1:
            raise RuntimeError(f"current {label} changed during rollback")
        updated = updated.replace(marker, f"{label}={replacement[component]}", 1)
    mode = stat.S_IMODE(path.stat().st_mode)
    atomic_write(path, updated, mode)


def private_caddy_runtime(path: Path, expected: str) -> str:
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("private Studio runtime is unavailable")
    content = path.read_text()
    assignments = [
        line.split("=", 1)[1]
        for line in content.splitlines()
        if line.startswith("CADDY_IMAGE=")
    ]
    if assignments != [expected]:
        raise RuntimeError("private Studio runtime CADDY_IMAGE does not match public runtime")
    return content


def replace_private_caddy(path: Path, expected: str, replacement: str) -> None:
    original = private_caddy_runtime(path, expected)
    updated = original.replace(
        f"CADDY_IMAGE={expected}", f"CADDY_IMAGE={replacement}", 1
    )
    atomic_write(path, updated, stat.S_IMODE(path.stat().st_mode))


def configuration(mode: str) -> tuple[dict[str, str], dict[str, str]]:
    credentials = load(CREDENTIALS)
    rollback = load(ROLLBACK_INPUT)
    current = {
        component: validate_image(credentials.get(label, ""), f"current {label}")
        for component, label in IMAGE_KEYS.items()
    }
    target = {
        component: validate_image(
            rollback.get(TARGET_KEYS[component], ""), f"rollback {component} image"
        )
        for component in IMAGE_KEYS
    }
    validate_distinct_images(current, "current")
    validate_distinct_images(target, "rollback")
    if current == target:
        raise ValueError("rollback release must differ from the current release")
    if mode == "execute":
        if rollback.get("ROLLBACK_CONFIRMATION") != CONFIRMATION:
            raise RuntimeError(
                "ROLLBACK_CONFIRMATION does not authorize traffic rollback"
            )
        validate_storage_change_confirmations(rollback, current, target)
    return current, target


def checked_command(command: list[str]) -> None:
    subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        timeout=600,
    )


def compensate(
    current: dict[str, str],
    target: dict[str, str],
    *,
    caddy_changed: bool,
    public_compose_up: list[str],
    private_compose_up: list[str] | None,
    preflight: list[str],
    caddy_coupling_check: list[str] | None,
) -> str | None:
    failures: list[str] = []
    public_environment_restored = False
    private_environment_restored = not caddy_changed

    try:
        replace_release(CREDENTIALS, target, current)
        public_environment_restored = True
    except Exception:
        failures.append("environment_restore")

    if caddy_changed:
        try:
            replace_private_caddy(
                PRIVATE_STUDIO_RUNTIME, target["caddy"], current["caddy"]
            )
            private_environment_restored = True
        except Exception:
            failures.append("private_environment_restore")

    public_redeployed = False
    if public_environment_restored:
        try:
            checked_command(public_compose_up)
            public_redeployed = True
        except Exception:
            failures.append("compensation_rollout")

    private_redeployed = not caddy_changed
    if caddy_changed and private_environment_restored:
        if private_compose_up is None:
            failures.append("private_compensation_rollout")
        else:
            try:
                checked_command(private_compose_up)
                private_redeployed = True
            except Exception:
                failures.append("private_compensation_rollout")

    recovery_preflight_passed = False
    if public_redeployed and private_redeployed:
        try:
            checked_command(preflight)
            recovery_preflight_passed = True
        except Exception:
            failures.append("compensation_preflight")

    if recovery_preflight_passed and caddy_coupling_check is not None:
        try:
            checked_command(caddy_coupling_check)
        except Exception:
            failures.append("compensation_caddy_coupling")

    return failures[0] if failures else None


def run(mode: str) -> dict[str, object]:
    if mode == "dummy":
        return {"event": "rollback.dummy_validated", "status": "pass"}
    reject_ci_managed_layout()
    current, target = configuration(mode)
    inspect_images(target)
    if mode == "inspect":
        return {
            "event": "rollback.target_inspected",
            "status": "pass",
            "current_digests": {
                key: value.rsplit("@", 1)[1] for key, value in current.items()
            },
            "target_digests": {
                key: value.rsplit("@", 1)[1] for key, value in target.items()
            },
        }

    caddy_changed = current["caddy"] != target["caddy"]
    if caddy_changed:
        private_caddy_runtime(PRIVATE_STUDIO_RUNTIME, current["caddy"])
        if PRIVATE_STUDIO_COMPOSE.is_symlink() or not PRIVATE_STUDIO_COMPOSE.is_file():
            raise RuntimeError("private Studio Compose project is unavailable")
        if CADDY_COUPLING_VALIDATOR.is_symlink() or not CADDY_COUPLING_VALIDATOR.is_file():
            raise RuntimeError("Caddy coupling validator is unavailable")

    prefix = command_prefix()
    compose = [*prefix, "--env-file", str(CREDENTIALS), "-f", str(ROOT / "compose.yml")]
    compose_up = [*compose, "up", "-d", "--no-build", "--remove-orphans"]
    preflight = [str(ROOT / "operations.sh"), "preflight"]
    private_compose_up = None
    caddy_coupling_check = None
    if caddy_changed:
        private_compose = [
            *prefix,
            "--env-file",
            str(PRIVATE_STUDIO_RUNTIME),
            "-f",
            str(PRIVATE_STUDIO_COMPOSE),
        ]
        private_compose_up = [
            *private_compose,
            "up",
            "-d",
            "--no-build",
            "--remove-orphans",
            "--wait",
            "--wait-timeout",
            "120",
        ]
        caddy_coupling_check = [
            sys.executable,
            str(CADDY_COUPLING_VALIDATOR),
            "--public-env",
            str(CREDENTIALS),
            "--private-env",
            str(PRIVATE_STUDIO_RUNTIME),
            "--public-compose",
            str(ROOT / "compose.yml"),
            "--private-compose",
            str(PRIVATE_STUDIO_COMPOSE),
            "--check-running",
        ]
        checked_command(caddy_coupling_check)
        replace_private_caddy(
            PRIVATE_STUDIO_RUNTIME, current["caddy"], target["caddy"]
        )
    try:
        replace_release(CREDENTIALS, current, target)
    except Exception:
        if caddy_changed:
            try:
                replace_private_caddy(
                    PRIVATE_STUDIO_RUNTIME, target["caddy"], current["caddy"]
                )
            except Exception:
                raise RollbackExecutionError(
                    "environment_update", "failed", "private_environment_restore"
                ) from None
        raise
    failed_stage = "target_rollout"
    try:
        checked_command(compose_up)
        if private_compose_up is not None:
            failed_stage = "target_private_rollout"
            checked_command(private_compose_up)
        failed_stage = "target_preflight"
        checked_command(preflight)
        if caddy_coupling_check is not None:
            failed_stage = "target_caddy_coupling"
            checked_command(caddy_coupling_check)
    except Exception:
        recovery_failure = compensate(
            current,
            target,
            caddy_changed=caddy_changed,
            public_compose_up=compose_up,
            private_compose_up=private_compose_up,
            preflight=preflight,
            caddy_coupling_check=caddy_coupling_check,
        )
        if recovery_failure is not None:
            raise RollbackExecutionError(
                failed_stage, "failed", recovery_failure
            ) from None
        raise RollbackExecutionError(failed_stage, "completed") from None
    return {
        "event": "rollback.completed",
        "status": "pass",
        "previous_digests": {
            key: value.rsplit("@", 1)[1] for key, value in current.items()
        },
        "active_digests": {
            key: value.rsplit("@", 1)[1] for key, value in target.items()
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("dummy", "inspect", "execute"), required=True
    )
    args = parser.parse_args()
    try:
        result = run(args.mode)
    except RollbackExecutionError as error:
        failure = {
            "event": (
                "rollback.recovery_failed"
                if error.recovery_status == "failed"
                else "rollback.failed"
            ),
            "status": "fail",
            "failed_stage": error.failed_stage,
            "recovery_status": error.recovery_status,
        }
        if error.recovery_failure_stage is not None:
            failure["recovery_failure_stage"] = error.recovery_failure_stage
        print(json.dumps(failure, sort_keys=True), file=sys.stderr)
        return 1
    except Exception:
        print(
            json.dumps({"event": "rollback.failed", "status": "fail"}), file=sys.stderr
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
