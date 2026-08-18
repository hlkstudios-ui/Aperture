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
CONFIRMATION = "ROLLBACK_HOSTINGER_APPLICATION_TRAFFIC"
IMAGE_KEYS = {
    "api": "API_IMAGE",
    "web": "WEB_IMAGE",
    "backup": "BACKUP_IMAGE",
}
TARGET_KEYS = {
    "api": "HOSTINGER_ROLLBACK_API_IMAGE",
    "web": "HOSTINGER_ROLLBACK_WEB_IMAGE",
    "backup": "HOSTINGER_ROLLBACK_BACKUP_IMAGE",
}


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


def command_prefix() -> list[str]:
    if subprocess.run(
        ["docker", "compose", "version"], capture_output=True, check=False
    ).returncode == 0:
        return ["docker", "compose"]
    if subprocess.run(["docker-compose", "version"], capture_output=True, check=False).returncode == 0:
        return ["docker-compose"]
    raise RuntimeError("Docker Compose is unavailable")


def inspect_images(images: dict[str, str]) -> None:
    command = ["docker", "image", "inspect", *images.values()]
    subprocess.run(command, check=True, capture_output=True, text=True, timeout=30)


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
    descriptor, temporary_name = tempfile.mkstemp(prefix=".credentials-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        os.write(descriptor, updated.encode())
        os.close(descriptor)
        descriptor = -1
        os.chmod(temporary, mode)
        os.replace(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def configuration(mode: str) -> tuple[dict[str, str], dict[str, str]]:
    credentials = load(CREDENTIALS)
    rollback = load(ROLLBACK_INPUT)
    current = {
        component: validate_image(credentials.get(label, ""), f"current {label}")
        for component, label in IMAGE_KEYS.items()
    }
    target = {
        component: validate_image(rollback.get(TARGET_KEYS[component], ""), f"rollback {component} image")
        for component in IMAGE_KEYS
    }
    if current == target:
        raise ValueError("rollback release must differ from the current release")
    if mode == "execute" and rollback.get("ROLLBACK_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError("ROLLBACK_CONFIRMATION does not authorize traffic rollback")
    return current, target


def run(mode: str) -> dict[str, str]:
    if mode == "dummy":
        return {"event": "rollback.dummy_validated", "status": "pass"}
    current, target = configuration(mode)
    inspect_images(target)
    if mode == "inspect":
        return {
            "event": "rollback.target_inspected", "status": "pass",
            "current_digests": {key: value.rsplit("@", 1)[1] for key, value in current.items()},
            "target_digests": {key: value.rsplit("@", 1)[1] for key, value in target.items()},
        }

    prefix = command_prefix()
    compose = [*prefix, "--env-file", str(CREDENTIALS), "-f", str(ROOT / "compose.yml")]
    replace_release(CREDENTIALS, current, target)
    try:
        subprocess.run([*compose, "up", "-d", "--no-build", "--remove-orphans"], check=True, timeout=600)
        subprocess.run([str(ROOT / "operations.sh"), "preflight"], check=True, timeout=600)
    except Exception:
        replace_release(CREDENTIALS, target, current)
        subprocess.run([*compose, "up", "-d", "--no-build", "--remove-orphans"], check=False, timeout=600)
        raise
    return {
        "event": "rollback.completed", "status": "pass",
        "previous_digests": {key: value.rsplit("@", 1)[1] for key, value in current.items()},
        "active_digests": {key: value.rsplit("@", 1)[1] for key, value in target.items()},
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "inspect", "execute"), required=True)
    args = parser.parse_args()
    try:
        result = run(args.mode)
    except Exception:
        print(json.dumps({"event": "rollback.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
