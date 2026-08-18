"""Validate the Hostinger VPS input file without exposing values."""

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
DEFAULT_INPUT = PROJECT_ROOT / ".env"
EXAMPLE_INPUT = ROOT / "credentials.example.env"
PERSISTENT_MEMORY_LABELS = (
    "POSTGRES_MEMORY_LIMIT", "REDIS_MEMORY_LIMIT", "MINIO_MEMORY_LIMIT",
    "CLAMAV_MEMORY_LIMIT", "API_MEMORY_LIMIT", "MEDIA_WORKER_MEMORY_LIMIT",
    "SCENE_WORKER_MEMORY_LIMIT", "WEB_MEMORY_LIMIT", "CADDY_MEMORY_LIMIT",
)
IMAGE_LABELS = ("API_IMAGE", "WEB_IMAGE", "BACKUP_IMAGE")


def image_reference(value: str, label: str) -> str:
    if "@sha256:" not in value or any(character.isspace() for character in value):
        raise ValueError(f"{label} must be an immutable registry digest reference")
    repository, digest = value.rsplit("@sha256:", 1)
    if "/" not in repository or repository.lower() != repository:
        raise ValueError(f"{label} must include a lowercase registry/repository")
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise ValueError(f"{label} must include a sha256 digest")
    return value


def memory_gib(value: str) -> float:
    suffix = value[-1:].lower()
    try:
        amount = float(value[:-1])
    except ValueError as error:
        raise ValueError("memory limits must use positive m/g units") from error
    if amount <= 0 or suffix not in {"m", "g"}:
        raise ValueError("memory limits must use positive m/g units")
    return amount if suffix == "g" else amount / 1024


def load(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid line {number}")
        key, value = line.split("=", 1)
        if not key:
            raise ValueError(f"empty label at line {number}")
        if key in values:
            raise ValueError(f"duplicate label: {key}")
        values[key] = value
    return values


def validate(values: dict[str, str], *, deploy: bool) -> None:
    required = set(load(EXAMPLE_INPUT))
    missing = sorted(required - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    empty = sorted(key for key in required if not values[key])
    if empty:
        raise ValueError("empty required labels: " + ", ".join(empty))
    if values["HOSTINGER_VPS_REGION"] != "New_York":
        raise ValueError("HOSTINGER_VPS_REGION must use the selected New_York target")
    try:
        vps_memory = int(values["HOSTINGER_VPS_MEMORY_GB"])
        vps_vcpu = int(values["HOSTINGER_VPS_VCPU"])
    except ValueError as error:
        raise ValueError("Hostinger VPS capacity must use integer values") from error
    reserved_memory = sum(memory_gib(values[label]) for label in PERSISTENT_MEMORY_LABELS)
    if vps_memory < 4 or reserved_memory > vps_memory * 0.8:
        raise ValueError("persistent memory ceilings must leave at least 20% VPS headroom")
    if vps_vcpu < 2:
        raise ValueError("HOSTINGER_VPS_VCPU must be at least 2")
    images = [image_reference(values[label], label) for label in IMAGE_LABELS]
    if len(set(images)) != len(images):
        raise ValueError("API, web, and backup images must be distinct")
    hosts = (
        values["WEB_HOSTNAME"], values["ORIGIN_HOSTNAME"],
        values["STORAGE_HOSTNAME"], values["CDN_HOSTNAME"],
    )
    if len(set(hosts)) != 4 or any("." not in host for host in hosts):
        raise ValueError("public hostnames must be distinct DNS names")
    if deploy:
        dummy = sorted(key for key, value in values.items() if "DUMMY" in value.upper())
        if dummy:
            raise ValueError("replace dummy labels before deploy: " + ", ".join(dummy))
        for key in (
            "POSTGRES_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD", "SESSION_SECRET",
            "STUDIO_EDGE_SECRET", "METRICS_BEARER_TOKEN", "CDN_SIGNING_SECRET",
            "CDN_ORIGIN_SECRET", "GEO_ASSERTION_SECRET", "BACKUP_S3_SECRET_KEY",
            "REPLICA_S3_SECRET_KEY", "ORIGIN_EDGE_SECRET",
        ):
            if len(values[key]) < 32:
                raise ValueError(f"{key} must contain at least 32 characters")
        if not values["STRIPE_SECRET_KEY"].startswith("sk_live_"):
            raise ValueError("STRIPE_SECRET_KEY must be a live key for production")
        if values["POLICY_REQUIRE_APPROVED"].lower() != "true":
            raise ValueError("POLICY_REQUIRE_APPROVED must be true for deployment")
        if any(value.endswith("0" * 64) for value in images):
            raise ValueError("production image digests must not use the dummy zero digest")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    validate(load(args.input), deploy=args.mode == "deploy")
    print("Hostinger VPS configuration is structurally valid.")


if __name__ == "__main__":
    main()
