"""Generate Aperture-owned secrets and render a least-privilege VPS dotenv file."""

import argparse
import os
import re
import secrets
import stat
import tempfile
from pathlib import Path

from validate_config import VPS_PROFILES, load, validate
from validate_host_hardening import load as load_host_hardening
from validate_host_hardening import validate as validate_host_hardening

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
DEFAULT_INPUT = PROJECT_ROOT / ".env"

# These credentials are wholly owned by Aperture. Provider-issued credentials must
# never be synthesized here.
INTERNAL_SECRET_BYTES = {
    "POSTGRES_PASSWORD": 32,
    "REDIS_PASSWORD": 32,
    "MINIO_ROOT_USER": 16,
    "MINIO_ROOT_PASSWORD": 32,
    "SESSION_SECRET": 32,
    "STUDIO_EDGE_SECRET": 32,
    "METRICS_BEARER_TOKEN": 32,
    "CDN_SIGNING_SECRET": 32,
    "CDN_ORIGIN_SECRET": 32,
    "GEO_ASSERTION_SECRET": 32,
    "ORIGIN_EDGE_SECRET": 32,
    "CUSTOM_DOMAIN_EDGE_SECRET": 32,
}

KNOWN_PLACEHOLDERS = {
    "POSTGRES_PASSWORD": {"replace_for_local_development"},
    "REDIS_PASSWORD": set(),
    "MINIO_ROOT_USER": {"replace_for_local_development"},
    "MINIO_ROOT_PASSWORD": {"replace_for_local_development"},
    "SESSION_SECRET": {"replace_with_a_long_random_local_secret"},
    "STUDIO_EDGE_SECRET": set(),
    "METRICS_BEARER_TOKEN": {"development-observability-token"},
    "CDN_SIGNING_SECRET": set(),
    "CDN_ORIGIN_SECRET": set(),
    "GEO_ASSERTION_SECRET": {"replace_with_a_long_random_local_geo_secret"},
    "ORIGIN_EDGE_SECRET": set(),
    "CUSTOM_DOMAIN_EDGE_SECRET": set(),
}

# Keep this explicit: adding a Compose credential must require a review of the VPS
# secret boundary. The focused test proves this remains an exact match for compose.yml.
COMPOSE_RUNTIME_LABELS = frozenset(
    {
        "ACME_EMAIL",
        "ADMIN_WEB_ORIGIN",
        "API_CPU_LIMIT",
        "API_IMAGE",
        "API_MEMORY_LIMIT",
        "BACKUP_IMAGE",
        "BACKUP_S3_ACCESS_KEY",
        "BACKUP_S3_BUCKET",
        "BACKUP_S3_ENDPOINT",
        "BACKUP_S3_REGION",
        "BACKUP_S3_SECRET_KEY",
        "BLACKBOX_IMAGE",
        "BRAND_AI_MODEL",
        "BRAND_AI_PROVIDER",
        "BRAND_AI_RATE_LIMIT_PER_HOUR",
        "BRAND_AI_TIMEOUT_SECONDS",
        "CADDY_IMAGE",
        "CADDY_CPU_LIMIT",
        "CADDY_MEMORY_LIMIT",
        "CAPTCHA_REQUIRED",
        "CDN_HOSTNAME",
        "CDN_ORIGIN_SECRET",
        "CDN_SIGNING_SECRET",
        "CLOUDFLARE_ACCOUNT_ID",
        "CLOUDFLARE_API_TIMEOUT_SECONDS",
        "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN",
        "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
        "CLOUDFLARE_TURNSTILE_API_TOKEN",
        "CLOUDFLARE_ZONE_ID",
        "CUSTOM_DOMAINS_ENABLED",
        "CUSTOM_DOMAIN_CNAME_TARGET",
        "CUSTOM_DOMAIN_EDGE_SECRET",
        "CUSTOM_DOMAIN_INFRASTRUCTURE_READY",
        "CUSTOM_DOMAIN_MAX_PER_SITE",
        "CUSTOM_DOMAIN_PROVIDER",
        "CLAMAV_CPU_LIMIT",
        "CLAMAV_MEMORY_LIMIT",
        "ERROR_TRACKING_DSN",
        "GEO_ASSERTION_SECRET",
        "HOSTINGER_VPS_IP",
        "HOSTINGER_VPS_IPV6",
        "MEDIA_WORKER_IMAGE",
        "MEDIA_WORKER_CPU_LIMIT",
        "MEDIA_WORKER_MEMORY_LIMIT",
        "METRICS_BEARER_TOKEN",
        "MINIO_CPU_LIMIT",
        "MINIO_MEMORY_LIMIT",
        "MINIO_ROOT_PASSWORD",
        "MINIO_ROOT_USER",
        "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
        "NODE_EXPORTER_IMAGE",
        "OAUTH_APPLE_CLIENT_ID",
        "OAUTH_APPLE_CLIENT_SECRET",
        "OAUTH_GITHUB_CLIENT_ID",
        "OAUTH_GITHUB_CLIENT_SECRET",
        "OAUTH_GOOGLE_CLIENT_ID",
        "OAUTH_GOOGLE_CLIENT_SECRET",
        "OAUTH_MICROSOFT_CLIENT_ID",
        "OAUTH_MICROSOFT_CLIENT_SECRET",
        "OPENAI_API_KEY",
        "ORIGIN_EDGE_SECRET",
        "ORIGIN_HOSTNAME",
        "POLICY_REQUIRE_APPROVED",
        "POSTGRES_CPU_LIMIT",
        "POSTGRES_DB",
        "POSTGRES_MEMORY_LIMIT",
        "POSTGRES_PASSWORD",
        "POSTGRES_USER",
        "REDIS_CPU_LIMIT",
        "REDIS_MEMORY_LIMIT",
        "REDIS_PASSWORD",
        "REPLICA_S3_ACCESS_KEY",
        "REPLICA_S3_BUCKET",
        "REPLICA_S3_ENDPOINT",
        "REPLICA_S3_SECRET_KEY",
        "S3_BUCKET",
        "SCENE_WORKER_CPU_LIMIT",
        "SCENE_WORKER_MEMORY_LIMIT",
        "SESSION_SECRET",
        "SMTP_FROM_EMAIL",
        "SMTP_HOST",
        "SMTP_PASSWORD",
        "SMTP_PORT",
        "SMTP_USERNAME",
        "STORAGE_IMAGE",
        "STORAGE_HOSTNAME",
        "STUDIO_EDGE_SECRET",
        "TMDB_API_READ_ACCESS_TOKEN",
        "TURNSTILE_SECRET_KEY",
        "TURNSTILE_HOSTNAME_LIMIT",
        "WEB_CPU_LIMIT",
        "WEB_HOSTNAME",
        "WEB_IMAGE",
        "WEB_MEMORY_LIMIT",
    }
)

HOST_AUDIT_RUNTIME_LABELS = frozenset(
    {
        "EXPECTED_HOSTNAME",
        "HOSTINGER_VPS_PROFILE",
        "HOST_HARDENING_CONFIRMATION",
        "HOST_MIN_DISK_GB",
        "HOST_MIN_FREE_DISK_GB",
        "HOST_MIN_MEMORY_GB",
        "SSH_ALLOWED_CIDR",
    }
)

VPS_RUNTIME_LABELS = COMPOSE_RUNTIME_LABELS | HOST_AUDIT_RUNTIME_LABELS

# These source-only fields are validated on the owner workstation and are never
# written to the VPS. Runtime validation supplies inert structural values so it can
# reuse the production contract without possessing a real control-plane credential.
SOURCE_ONLY_VALIDATION_LABELS = frozenset(
    {
        "DNS_ZONE",
        "CLOUDFLARE_API_TOKEN",
        "CLOUDFLARE_CDN_SCRIPT_NAME",
        "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
        "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME",
        "CUSTOM_DOMAIN_FALLBACK_ORIGIN",
        "HOSTINGER_API_TOKEN",
        "HOSTINGER_VPS_MEMORY_GB",
        "HOSTINGER_VPS_REGION",
        "HOSTINGER_VPS_VCPU",
        # This production release hardcodes billing disabled in Compose. Keep any
        # future Stripe credentials on the owner workstation until a reviewed
        # billing-enabled release explicitly adds them back to the runtime boundary.
        "STRIPE_SECRET_KEY",
        "STRIPE_WEBHOOK_SECRET",
    }
)

HOSTINGER_TOKEN_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?HOSTINGER_API_TOKEN[ \t]*=)[^\r\n]*(?P<ending>\r?\n?)$"
)
CLOUDFLARE_DNS_TOKEN_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?CLOUDFLARE_API_TOKEN[ \t]*=)[^\r\n]*(?P<ending>\r?\n?)$"
)
CLOUDFLARE_PREFLIGHT_TOKEN_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN[ \t]*=)[^\r\n]*(?P<ending>\r?\n?)$"
)
TAILSCALE_AUTH_KEY_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?TAILSCALE_AUTH_KEY[ \t]*=)[^\r\n]*(?P<ending>\r?\n?)$"
)
TAILSCALE_API_KEY_ASSIGNMENT = re.compile(
    r"^(?P<prefix>[ \t]*(?:export[ \t]+)?TAILSCALE_API_KEY[ \t]*=)[^\r\n]*(?P<ending>\r?\n?)$"
)


def is_placeholder(label: str, value: str) -> bool:
    return not value or "DUMMY" in value.upper() or value in KNOWN_PLACEHOLDERS[label]


def atomic_write(path: Path, content: str, *, mode: int) -> None:
    if not path.parent.is_dir():
        raise ValueError("output parent directory does not exist")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent
    )
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


def generate_internal(path: Path) -> tuple[int, int]:
    values = load(path)
    missing = sorted(INTERNAL_SECRET_BYTES.keys() - values.keys())
    if missing:
        raise ValueError("missing internal secret labels: " + ", ".join(missing))

    replacements = {
        label: secrets.token_hex(size)
        for label, size in INTERNAL_SECRET_BYTES.items()
        if is_placeholder(label, values[label])
    }
    if not replacements:
        return 0, len(INTERNAL_SECRET_BYTES)

    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    positions: dict[str, int] = {}
    for index, raw in enumerate(lines):
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key = line.split("=", 1)[0]
            positions[key] = index

    for label, replacement in replacements.items():
        raw = lines[positions[label]]
        body = raw.rstrip("\r\n")
        ending = raw[len(body) :]
        lines[positions[label]] = f"{label}={replacement}{ending}"

    mode = stat.S_IMODE(path.stat().st_mode)
    atomic_write(path, "".join(lines), mode=mode)
    return len(replacements), len(INTERNAL_SECRET_BYTES) - len(replacements)


def clear_source_credential(
    path: Path, assignment: re.Pattern[str], label: str
) -> bool:
    """Atomically empty every active assignment for one source-only credential."""
    with path.open("r", encoding="utf-8", newline="") as handle:
        lines = handle.readlines()

    found = False
    changed = False
    rendered: list[str] = []
    for raw in lines:
        match = assignment.fullmatch(raw)
        if match is None:
            rendered.append(raw)
            continue
        found = True
        replacement = f"{match.group('prefix')}{match.group('ending')}"
        rendered.append(replacement)
        changed = changed or replacement != raw

    if not found:
        raise ValueError(f"{label} assignment is missing")
    if not changed:
        return False

    mode = stat.S_IMODE(path.stat().st_mode)
    atomic_write(path, "".join(rendered), mode=mode)
    return True


def clear_hostinger_api_token(path: Path) -> bool:
    """Atomically empty every active HOSTINGER_API_TOKEN assignment."""
    return clear_source_credential(
        path, HOSTINGER_TOKEN_ASSIGNMENT, "HOSTINGER_API_TOKEN"
    )


def clear_cloudflare_dns_token(path: Path) -> bool:
    """Atomically empty every active one-shot Cloudflare DNS token assignment."""
    return clear_source_credential(
        path, CLOUDFLARE_DNS_TOKEN_ASSIGNMENT, "CLOUDFLARE_API_TOKEN"
    )


def clear_cloudflare_preflight_token(path: Path) -> bool:
    """Atomically empty every active Cloudflare topology token assignment."""
    return clear_source_credential(
        path,
        CLOUDFLARE_PREFLIGHT_TOKEN_ASSIGNMENT,
        "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
    )


def clear_tailscale_auth_key(path: Path) -> bool:
    """Atomically empty every active TAILSCALE_AUTH_KEY assignment."""
    return clear_source_credential(
        path, TAILSCALE_AUTH_KEY_ASSIGNMENT, "TAILSCALE_AUTH_KEY"
    )


def clear_tailscale_api_key(path: Path) -> bool:
    """Atomically empty every active TAILSCALE_API_KEY assignment."""
    return clear_source_credential(
        path, TAILSCALE_API_KEY_ASSIGNMENT, "TAILSCALE_API_KEY"
    )


def runtime_values(values: dict[str, str]) -> dict[str, str]:
    selected = {label: values[label] for label in VPS_RUNTIME_LABELS}
    if values["CAPTCHA_REQUIRED"] == "false":
        selected["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = ""
        selected["TURNSTILE_SECRET_KEY"] = ""
    if not (
        values["CAPTCHA_REQUIRED"] == "true"
        and values["CUSTOM_DOMAINS_ENABLED"] == "true"
    ):
        selected["CLOUDFLARE_TURNSTILE_API_TOKEN"] = ""
        selected["TURNSTILE_HOSTNAME_LIMIT"] = "10"
    if values["BRAND_AI_PROVIDER"] == "disabled":
        selected["OPENAI_API_KEY"] = ""
    if values["CUSTOM_DOMAINS_ENABLED"] == "false":
        selected["CUSTOM_DOMAIN_PROVIDER"] = "disabled"
        selected["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] = "false"
        for label in (
            "CUSTOM_DOMAIN_CNAME_TARGET",
            "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN",
            "CLOUDFLARE_ZONE_ID",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
        ):
            selected[label] = ""
    return selected


def validate_runtime_values(values: dict[str, str]) -> None:
    labels = set(values)
    missing = sorted(VPS_RUNTIME_LABELS - labels)
    if missing:
        raise ValueError("missing VPS runtime labels: " + ", ".join(missing))
    unexpected = sorted(labels - VPS_RUNTIME_LABELS)
    if unexpected:
        raise ValueError("unexpected VPS runtime labels: " + ", ".join(unexpected))

    profile_name = values["HOSTINGER_VPS_PROFILE"]
    profile = VPS_PROFILES.get(profile_name, {"memory_gb": 0, "vcpu": 0})
    projected = dict(values)
    projected.update(
        {
            "DNS_ZONE": "runtime-validation.invalid",
            "CLOUDFLARE_API_TOKEN": "",
            "CLOUDFLARE_CDN_SCRIPT_NAME": "aperture-protected-media",
            "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN": "",
            "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME": "aperture-production-geo-edge",
            "CUSTOM_DOMAIN_FALLBACK_ORIGIN": (
                values["ORIGIN_HOSTNAME"]
                if values["CUSTOM_DOMAIN_PROVIDER"] == "cloudflare"
                else ""
            ),
            "HOSTINGER_API_TOKEN": "source-control-credential-intentionally-absent",
            "HOSTINGER_VPS_MEMORY_GB": str(profile["memory_gb"]),
            "HOSTINGER_VPS_REGION": "Boston_2",
            "HOSTINGER_VPS_VCPU": str(profile["vcpu"]),
            "STRIPE_SECRET_KEY": "",
            "STRIPE_WEBHOOK_SECRET": "",
        }
    )
    validate(projected, deploy=True)
    validate_host_hardening(
        {label: values[label] for label in HOST_AUDIT_RUNTIME_LABELS}, apply=True
    )


def validate_runtime_file(path: Path) -> None:
    validate_runtime_values(load(path))


def render_vps(input_path: Path, output_path: Path) -> None:
    if input_path.resolve() == output_path.resolve():
        raise ValueError("render output must differ from the owner credential file")

    values = load(input_path)
    validate(values, deploy=True)
    host_values = load_host_hardening(input_path)
    validate_host_hardening(host_values, apply=True)

    selected = runtime_values(values)
    validate_runtime_values(selected)
    content = "".join(
        f"{label}={selected[label]}\n" for label in sorted(VPS_RUNTIME_LABELS)
    )
    atomic_write(output_path, content, mode=0o600)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    clear_parser = subparsers.add_parser("clear-hostinger-token")
    clear_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    clear_cloudflare_dns_parser = subparsers.add_parser(
        "clear-cloudflare-dns-token"
    )
    clear_cloudflare_dns_parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT
    )

    clear_cloudflare_preflight_parser = subparsers.add_parser(
        "clear-cloudflare-preflight-token"
    )
    clear_cloudflare_preflight_parser.add_argument(
        "--input", type=Path, default=DEFAULT_INPUT
    )

    clear_tailscale_parser = subparsers.add_parser("clear-tailscale-auth-key")
    clear_tailscale_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    clear_tailscale_api_parser = subparsers.add_parser("clear-tailscale-api-key")
    clear_tailscale_api_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    render_parser = subparsers.add_parser("render")
    render_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    render_parser.add_argument("--output", type=Path, required=True)

    validate_parser = subparsers.add_parser("validate-runtime")
    validate_parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)

    args = parser.parse_args(argv)
    if args.action == "generate":
        generated, preserved = generate_internal(args.input)
        print(
            f"Internal Aperture secrets prepared: {generated} generated, {preserved} preserved."
        )
        return
    if args.action == "clear-hostinger-token":
        changed = clear_hostinger_api_token(args.input)
        state = "cleared" if changed else "already empty"
        print(f"Hostinger source credential is {state}.")
        return
    if args.action == "clear-cloudflare-dns-token":
        changed = clear_cloudflare_dns_token(args.input)
        state = "cleared" if changed else "already empty"
        print(f"Cloudflare DNS source credential is {state}.")
        return
    if args.action == "clear-cloudflare-preflight-token":
        changed = clear_cloudflare_preflight_token(args.input)
        state = "cleared" if changed else "already empty"
        print(f"Cloudflare preflight source credential is {state}.")
        return
    if args.action == "clear-tailscale-auth-key":
        changed = clear_tailscale_auth_key(args.input)
        state = "cleared" if changed else "already empty"
        print(f"Tailscale enrollment credential is {state}.")
        return
    if args.action == "clear-tailscale-api-key":
        changed = clear_tailscale_api_key(args.input)
        state = "cleared" if changed else "already empty"
        print(f"Tailscale API credential is {state}.")
        return
    if args.action == "render":
        render_vps(args.input, args.output)
        print("Sanitized VPS environment rendered.")
        return
    validate_runtime_file(args.input)
    print("Sanitized VPS environment is structurally valid.")


if __name__ == "__main__":
    main()
