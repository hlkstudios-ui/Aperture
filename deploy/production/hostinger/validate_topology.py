"""Audit a rendered Hostinger Compose model for mandatory isolation controls."""

import argparse
import ipaddress
import json
from pathlib import Path

PUBLIC_SERVICE = "caddy"
HEALTH_REQUIRED = {"postgres", "redis", "minio", "clamav", "api", "web", "caddy"}
HARDENED = {
    "api",
    "minio",
    "web",
    "media-worker",
    "scene-worker",
    "migrate",
    "maintenance",
    "preflight",
    "backup",
    "restore",
    "replicate-media",
    "caddy",
    "node-exporter",
    "prometheus",
    "blackbox",
}
RELEASE_SERVICES = {
    "api",
    "minio",
    "web",
    "media-worker",
    "scene-worker",
    "migrate",
    "maintenance",
    "preflight",
    "backup",
    "restore",
    "caddy",
    "node-exporter",
    "blackbox",
}
ARTIFACT_IMAGE_SERVICES = {
    "api": {"api", "scene-worker", "migrate", "maintenance", "preflight"},
    "media_worker": {"media-worker"},
    "web": {"web"},
    "backup": {"backup", "restore"},
    "caddy": {"caddy"},
    "storage": {"minio"},
    "node_exporter": {"node-exporter"},
    "blackbox": {"blackbox"},
}
DISTINCT_IMAGE_SERVICES = {
    component: next(iter(service_names))
    for component, service_names in ARTIFACT_IMAGE_SERVICES.items()
}
WEB_CACHE_PATH = "/app/apps/web/.next/cache"
WEB_CACHE_REQUIRED_OPTIONS = {"size=128m", "mode=0700", "uid=65532", "gid=65532"}
UPSTREAM_RUNTIME_IMAGES = {
    "clamav": "clamav/clamav:1.5.3",
    "prometheus": "prom/prometheus:v3.14.0-distroless",
}


def _tmpfs_options(service_name: str, entry: object) -> tuple[str, set[str]]:
    if not isinstance(entry, str) or not entry.strip():
        raise ValueError(f"{service_name} has an empty or invalid tmpfs entry")
    target, separator, raw_options = entry.partition(":")
    if not target.startswith("/"):
        raise ValueError(
            f"{service_name} tmpfs target must be an absolute path: {target}"
        )
    options = {value.strip() for value in raw_options.split(",") if value.strip()}
    if separator and not options:
        raise ValueError(f"{service_name} has an empty tmpfs option list for {target}")
    return target, options


def validate_tmpfs(services: dict) -> None:
    targets_by_service: dict[str, dict[str, set[str]]] = {}
    for name in HARDENED:
        entries = services.get(name, {}).get("tmpfs", [])
        if not isinstance(entries, list):
            raise ValueError(f"{name} tmpfs configuration must be a list")
        targets: dict[str, set[str]] = {}
        for entry in entries:
            target, options = _tmpfs_options(name, entry)
            if target in targets:
                raise ValueError(f"{name} has a duplicate tmpfs target: {target}")
            targets[target] = options
        if "/tmp" not in targets:
            raise ValueError(f"{name} lacks a writable /tmp tmpfs")
        targets_by_service[name] = targets

    web_cache_options = targets_by_service["web"].get(WEB_CACHE_PATH)
    if web_cache_options is None:
        raise ValueError("web lacks a writable Next.js cache tmpfs")
    if not any(option.startswith("size=") for option in web_cache_options):
        raise ValueError("web Next.js cache tmpfs lacks a size ceiling")
    if not WEB_CACHE_REQUIRED_OPTIONS.issubset(web_cache_options):
        raise ValueError("web Next.js cache tmpfs lacks its bounded nonroot options")


def validate_upstream_runtime_images(services: dict) -> None:
    for service_name, expected_image in UPSTREAM_RUNTIME_IMAGES.items():
        actual_image = services.get(service_name, {}).get("image")
        if actual_image != expected_image:
            raise ValueError(
                f"{service_name} must use the audited upstream image {expected_image}"
            )


def validate_release_images(services: dict) -> None:
    for name in RELEASE_SERVICES:
        service = services.get(name, {})
        if "@sha256:" not in service.get("image", "") or service.get("build"):
            raise ValueError(f"{name} is not pinned to a registry digest")
    for component, service_names in ARTIFACT_IMAGE_SERVICES.items():
        images = {services[name]["image"] for name in service_names}
        if len(images) != 1:
            raise ValueError(
                f"{component} services must share their audited release image"
            )
    image_digests = [
        services[service_name]["image"].rsplit("@sha256:", 1)[1]
        for service_name in DISTINCT_IMAGE_SERVICES.values()
    ]
    if len(set(image_digests)) != len(image_digests):
        raise ValueError(
            "API, media worker, web, backup, Caddy, storage, node exporter, "
            "and Blackbox image digests must be distinct"
        )


def validate_caddy_ports(ports: object) -> None:
    if not isinstance(ports, list):
        raise ValueError("Caddy ports must be an explicit list")
    bindings: set[tuple[str, int, int, str]] = set()
    addresses: dict[int, set[str]] = {4: set(), 6: set()}
    for item in ports:
        if not isinstance(item, dict):
            raise ValueError("Caddy ports must use long-form address bindings")
        host_ip = item.get("host_ip")
        try:
            address = ipaddress.ip_address(host_ip)
            published = int(item["published"])
            target = int(item["target"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError("Caddy has an invalid address-bound port") from error
        if address.is_unspecified:
            raise ValueError("Caddy must not bind a wildcard host address")
        protocol = item.get("protocol")
        if protocol not in {"tcp", "udp"}:
            raise ValueError("Caddy has an invalid ingress protocol")
        addresses[address.version].add(str(address))
        bindings.add((str(address), published, target, protocol))

    if any(len(values) != 1 for values in addresses.values()):
        raise ValueError("Caddy requires one explicit public IPv4 and IPv6 address")
    public_ipv4 = next(iter(addresses[4]))
    public_ipv6 = next(iter(addresses[6]))
    expected = {
        (address, published, target, protocol)
        for address in (public_ipv4, public_ipv6)
        for published, target, protocol in (
            (80, 8080, "tcp"),
            (443, 8443, "tcp"),
            (443, 8443, "udp"),
        )
    }
    if bindings != expected or len(ports) != len(expected):
        raise ValueError("Caddy is not bound to both public addresses on 80/443")


def validate(model: dict) -> None:
    services = model.get("services")
    if not isinstance(services, dict) or not services:
        raise ValueError("rendered Compose model has no services")
    for name, service in services.items():
        ports = service.get("ports", [])
        if ports and name != PUBLIC_SERVICE:
            raise ValueError(f"{name} unexpectedly publishes a host port")
        if (
            not service.get("mem_limit")
            or not service.get("cpus")
            or not service.get("pids_limit")
        ):
            raise ValueError(f"{name} lacks resource ceilings")
        logging = service.get("logging", {})
        options = logging.get("options", {})
        if (
            logging.get("driver") != "json-file"
            or options.get("max-size") != "10m"
            or options.get("max-file") != "5"
        ):
            raise ValueError(f"{name} lacks bounded log rotation")
        if name in HARDENED:
            if not service.get("read_only") or "ALL" not in service.get("cap_drop", []):
                raise ValueError(f"{name} lacks the hardened read-only runtime")
            if "no-new-privileges:true" not in service.get("security_opt", []):
                raise ValueError(f"{name} permits privilege escalation")
    validate_tmpfs(services)
    validate_upstream_runtime_images(services)
    for name in HEALTH_REQUIRED:
        if not services.get(name, {}).get("healthcheck"):
            raise ValueError(f"{name} lacks a health check")
    validate_release_images(services)
    validate_caddy_ports(services[PUBLIC_SERVICE].get("ports"))
    caddy_environment = services[PUBLIC_SERVICE].get("environment", {})
    if (
        not caddy_environment.get("ORIGIN_EDGE_SECRET")
        or not caddy_environment.get("ORIGIN_HOSTNAME")
        or not caddy_environment.get("STUDIO_EDGE_SECRET")
    ):
        raise ValueError("trusted origin-edge enforcement is missing")
    if any(
        services.get(name, {}).get("ports")
        for name in ("prometheus", "node-exporter", "blackbox")
    ):
        raise ValueError("monitoring services must remain private")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(json.loads(args.input.read_text()))
    print("Hostinger topology hardening controls are present.")


if __name__ == "__main__":
    main()
