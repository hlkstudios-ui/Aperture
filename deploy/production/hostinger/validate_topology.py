"""Audit a rendered Hostinger Compose model for mandatory isolation controls."""

import argparse
import json
from pathlib import Path

PUBLIC_SERVICE = "caddy"
HEALTH_REQUIRED = {"postgres", "redis", "minio", "clamav", "api", "web", "caddy"}
HARDENED = {
    "api", "web", "media-worker", "scene-worker", "migrate", "maintenance",
    "preflight", "backup", "restore", "replicate-media", "caddy",
    "node-exporter", "prometheus", "blackbox",
}
RELEASE_SERVICES = {
    "api", "web", "media-worker", "scene-worker", "migrate", "maintenance",
    "preflight", "backup", "restore",
}


def validate(model: dict) -> None:
    services = model.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("rendered Compose model has no services")
    for name, service in services.items():
        ports = service.get("ports", [])
        if ports and name != PUBLIC_SERVICE:
            raise ValueError(f"{name} unexpectedly publishes a host port")
        if not service.get("mem_limit") or not service.get("cpus") or not service.get("pids_limit"):
            raise ValueError(f"{name} lacks resource ceilings")
        logging = service.get("logging", {})
        options = logging.get("options", {})
        if logging.get("driver") != "json-file" or options.get("max-size") != "10m" or options.get("max-file") != "5":
            raise ValueError(f"{name} lacks bounded log rotation")
        if name in HARDENED:
            if not service.get("read_only") or "ALL" not in service.get("cap_drop", []):
                raise ValueError(f"{name} lacks the hardened read-only runtime")
            if "no-new-privileges:true" not in service.get("security_opt", []):
                raise ValueError(f"{name} permits privilege escalation")
    for name in HEALTH_REQUIRED:
        if not services.get(name, {}).get("healthcheck"):
            raise ValueError(f"{name} lacks a health check")
    for name in RELEASE_SERVICES:
        service = services.get(name, {})
        if "@sha256:" not in service.get("image", "") or service.get("build"):
            raise ValueError(f"{name} is not pinned to a registry digest")
    caddy_ports = {(int(item["published"]), item["protocol"]) for item in services[PUBLIC_SERVICE]["ports"]}
    if caddy_ports != {(80, "tcp"), (443, "tcp"), (443, "udp")}:
        raise ValueError("Caddy is not the exclusive 80/443 ingress")
    caddy_environment = services[PUBLIC_SERVICE].get("environment", {})
    if (
        not caddy_environment.get("ORIGIN_EDGE_SECRET")
        or not caddy_environment.get("ORIGIN_HOSTNAME")
        or not caddy_environment.get("STUDIO_EDGE_SECRET")
    ):
        raise ValueError("trusted origin-edge enforcement is missing")
    if any(services.get(name, {}).get("ports") for name in ("prometheus", "node-exporter", "blackbox")):
        raise ValueError("monitoring services must remain private")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text()))
    print("Hostinger topology hardening controls are present.")


if __name__ == "__main__":
    main()
