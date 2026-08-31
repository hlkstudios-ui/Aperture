"""Fail closed unless public and private Studio use one immutable Caddy image."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

from read_env import read


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
PUBLIC_ENV = PROJECT_ROOT / ".env"
PUBLIC_COMPOSE = ROOT / "compose.yml"
PRIVATE_ROOT = ROOT.parent / "private-studio"
PRIVATE_ENV = PRIVATE_ROOT / "runtime.local.env"
PRIVATE_COMPOSE = PRIVATE_ROOT / "compose.yml"
IMMUTABLE_IMAGE = re.compile(r"^[a-z0-9.-]+(?::[0-9]+)?/.+@sha256:[0-9a-f]{64}$")


class CouplingError(ValueError):
    """The two runtime artifacts or containers do not share one Caddy digest."""


def run_command(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise CouplingError(f"command failed: {command[0]} {command[1]}")
    return completed.stdout


def artifact_image(public_env: Path, private_env: Path) -> str:
    public_image = read(public_env, "CADDY_IMAGE")
    private_image = read(private_env, "CADDY_IMAGE")
    if not IMMUTABLE_IMAGE.fullmatch(public_image):
        raise CouplingError("public CADDY_IMAGE is not an immutable registry digest")
    if not IMMUTABLE_IMAGE.fullmatch(private_image):
        raise CouplingError("private CADDY_IMAGE is not an immutable registry digest")
    if (
        "dummy" in public_image.lower()
        or public_image.endswith("0" * 64)
        or "dummy" in private_image.lower()
        or private_image.endswith("0" * 64)
    ):
        raise CouplingError("CADDY_IMAGE must be a non-dummy release digest")
    if public_image != private_image:
        raise CouplingError("public and private CADDY_IMAGE values differ")
    return public_image


def compose_container_id(
    env_file: Path, compose_file: Path, service: str
) -> str:
    ids = run_command(
        [
            "docker",
            "compose",
            "--env-file",
            str(env_file),
            "-f",
            str(compose_file),
            "ps",
            "--all",
            "--quiet",
            service,
        ]
    ).split()
    if len(ids) != 1:
        raise CouplingError(f"expected exactly one running contract for {service}")
    return ids[0]


def validate_container(
    container_id: str,
    *,
    service: str,
    expected_image: str,
    require_healthy: bool,
) -> None:
    raw = run_command(["docker", "inspect", container_id])
    try:
        records = json.loads(raw)
    except json.JSONDecodeError as error:
        raise CouplingError(f"invalid container inspection for {service}") from error
    if not isinstance(records, list) or len(records) != 1:
        raise CouplingError(f"unexpected container inspection for {service}")
    record = records[0]
    config = record.get("Config", {})
    state = record.get("State", {})
    labels = config.get("Labels", {})
    if labels.get("com.docker.compose.service") != service:
        raise CouplingError(f"container service label mismatch for {service}")
    if config.get("Image") != expected_image:
        raise CouplingError(f"running Caddy image mismatch for {service}")
    if config.get("User") not in {"nonroot", "65532", "65532:65532"}:
        raise CouplingError(f"running Caddy user mismatch for {service}")
    if state.get("Running") is not True:
        raise CouplingError(f"Caddy container is not running for {service}")
    if require_healthy and state.get("Health", {}).get("Status") != "healthy":
        raise CouplingError(f"Caddy container is not healthy for {service}")


def validate_running(
    *,
    public_env: Path,
    private_env: Path,
    public_compose: Path,
    private_compose: Path,
    expected_image: str,
) -> None:
    public_id = compose_container_id(public_env, public_compose, "caddy")
    private_id = compose_container_id(private_env, private_compose, "studio-gateway")
    validate_container(
        public_id,
        service="caddy",
        expected_image=expected_image,
        require_healthy=True,
    )
    validate_container(
        private_id,
        service="studio-gateway",
        expected_image=expected_image,
        require_healthy=False,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-env", type=Path, default=PUBLIC_ENV)
    parser.add_argument("--private-env", type=Path, default=PRIVATE_ENV)
    parser.add_argument("--public-compose", type=Path, default=PUBLIC_COMPOSE)
    parser.add_argument("--private-compose", type=Path, default=PRIVATE_COMPOSE)
    parser.add_argument("--check-running", action="store_true")
    args = parser.parse_args(argv)
    try:
        image = artifact_image(args.public_env, args.private_env)
        if args.check_running:
            validate_running(
                public_env=args.public_env,
                private_env=args.private_env,
                public_compose=args.public_compose,
                private_compose=args.private_compose,
                expected_image=image,
            )
    except (CouplingError, OSError, ValueError):
        print(
            json.dumps({"event": "caddy.coupling", "status": "fail"}),
            file=sys.stderr,
        )
        return 1
    print(
        json.dumps(
            {
                "event": "caddy.coupling",
                "runtime": "verified" if args.check_running else "not_checked",
                "status": "pass",
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
