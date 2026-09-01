"""Validate the Hostinger VPS input file without exposing values."""

import argparse
import ipaddress
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
DEFAULT_INPUT = PROJECT_ROOT / ".env"
EXAMPLE_INPUT = ROOT / "credentials.example.env"
PERSISTENT_MEMORY_LABELS = (
    "POSTGRES_MEMORY_LIMIT",
    "REDIS_MEMORY_LIMIT",
    "MINIO_MEMORY_LIMIT",
    "CLAMAV_MEMORY_LIMIT",
    "API_MEMORY_LIMIT",
    "MEDIA_WORKER_MEMORY_LIMIT",
    "SCENE_WORKER_MEMORY_LIMIT",
    "WEB_MEMORY_LIMIT",
    "CADDY_MEMORY_LIMIT",
)
IMAGE_LABELS = (
    "API_IMAGE",
    "MEDIA_WORKER_IMAGE",
    "WEB_IMAGE",
    "BACKUP_IMAGE",
    "CADDY_IMAGE",
    "STORAGE_IMAGE",
    "NODE_EXPORTER_IMAGE",
    "BLACKBOX_IMAGE",
)
VPS_PROFILES = {
    "compact": {"memory_gb": 16, "vcpu": 4, "reserved_memory_ratio": 0.65},
    "full": {"memory_gb": 32, "vcpu": 8, "reserved_memory_ratio": 0.80},
}
OAUTH_PAIRS = (
    ("OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET"),
    ("OAUTH_MICROSOFT_CLIENT_ID", "OAUTH_MICROSOFT_CLIENT_SECRET"),
    ("OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET"),
    ("OAUTH_APPLE_CLIENT_ID", "OAUTH_APPLE_CLIENT_SECRET"),
)
CUSTOM_DOMAIN_PROVIDER_LABELS = {
    "CUSTOM_DOMAIN_CNAME_TARGET",
    "CUSTOM_DOMAIN_FALLBACK_ORIGIN",
    "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN",
    "CLOUDFLARE_ZONE_ID",
    "CLOUDFLARE_ACCOUNT_ID",
    "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
    "CLOUDFLARE_GEO_EDGE_SCRIPT_NAME",
    "CLOUDFLARE_CDN_SCRIPT_NAME",
}
CONDITIONAL_LABELS = {
    "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "CLOUDFLARE_TURNSTILE_API_TOKEN",
    "TURNSTILE_HOSTNAME_LIMIT",
    "OPENAI_API_KEY",
    # The approved Hostinger release is explicitly non-commercial. These labels remain in the
    # runtime allowlist for a future reviewed Stripe release, but must stay empty for this one.
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    *CUSTOM_DOMAIN_PROVIDER_LABELS,
    *(label for pair in OAUTH_PAIRS for label in pair),
}
POST_PROVISION_OPTIONAL_LABELS = {
    "HOSTINGER_API_TOKEN",
    "CLOUDFLARE_API_TOKEN",
    "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
}
OPTIONAL_LABELS = CONDITIONAL_LABELS | POST_PROVISION_OPTIONAL_LABELS


def active_conditional_labels(values: dict[str, str]) -> set[str]:
    """Return optional credential labels that are enabled for this deployment."""
    active: set[str] = set()
    if values["CAPTCHA_REQUIRED"] == "true":
        active.update(("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY"))
        if values["CUSTOM_DOMAINS_ENABLED"] == "true":
            active.update(
                ("CLOUDFLARE_TURNSTILE_API_TOKEN", "TURNSTILE_HOSTNAME_LIMIT")
            )
    if values["BRAND_AI_PROVIDER"] == "openai":
        active.add("OPENAI_API_KEY")
    if (
        values["CUSTOM_DOMAINS_ENABLED"] == "true"
        or values["CUSTOM_DOMAIN_PROVIDER"] == "cloudflare"
    ):
        active.update(CUSTOM_DOMAIN_PROVIDER_LABELS)
    for client_id, client_secret in OAUTH_PAIRS:
        if values[client_id] or values[client_secret]:
            active.update((client_id, client_secret))
    return active


def require_hostinger_api_token(values: dict[str, str]) -> None:
    """Fail closed before a caller performs a Hostinger control-plane request."""
    token = values.get("HOSTINGER_API_TOKEN", "").strip()
    if not token or "DUMMY" in token.upper():
        raise ValueError(
            "HOSTINGER_API_TOKEN is required for Hostinger API operations; "
            "configure a short-lived token locally"
        )


def image_reference(value: str, label: str) -> str:
    if "@sha256:" not in value or any(character.isspace() for character in value):
        raise ValueError(f"{label} must be an immutable registry digest reference")
    repository, digest = value.rsplit("@sha256:", 1)
    if "/" not in repository or repository.lower() != repository:
        raise ValueError(f"{label} must include a lowercase registry/repository")
    if len(digest) != 64 or any(
        character not in "0123456789abcdef" for character in digest
    ):
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


def require_https_origin(value: str, label: str) -> None:
    try:
        parsed = urlsplit(value)
        parsed.port
    except ValueError as error:
        raise ValueError(f"{label} must be an HTTPS origin") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError(f"{label} must be an HTTPS origin")


def require_ip_address(
    value: str, label: str, *, version: int
) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        address = ipaddress.ip_address(value)
    except ValueError as error:
        raise ValueError(f"{label} must be an IPv{version} address") from error
    if address.version != version:
        raise ValueError(f"{label} must be an IPv{version} address")
    return address


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


def validate(
    values: dict[str, str], *, deploy: bool, require_hostinger_token: bool = False
) -> None:
    labels = set(load(EXAMPLE_INPUT))
    missing = sorted(labels - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    if require_hostinger_token:
        require_hostinger_api_token(values)
    empty = sorted(key for key in labels - OPTIONAL_LABELS if not values[key])
    if empty:
        raise ValueError("empty required labels: " + ", ".join(empty))
    if values["CAPTCHA_REQUIRED"] not in {"true", "false"}:
        raise ValueError("CAPTCHA_REQUIRED must be true or false")
    if values["CAPTCHA_REQUIRED"] == "true" and not all(
        values[key]
        for key in ("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY")
    ):
        raise ValueError(
            "CAPTCHA_REQUIRED requires both NEXT_PUBLIC_TURNSTILE_SITE_KEY "
            "and TURNSTILE_SECRET_KEY"
        )
    for client_id, client_secret in OAUTH_PAIRS:
        if bool(values[client_id]) != bool(values[client_secret]):
            raise ValueError(
                f"{client_id} and {client_secret} must be configured together"
            )
    if values["BRAND_AI_PROVIDER"] not in {"disabled", "openai"}:
        raise ValueError("BRAND_AI_PROVIDER must be disabled or openai")
    if values["BRAND_AI_PROVIDER"] == "openai" and not values["OPENAI_API_KEY"]:
        raise ValueError("BRAND_AI_PROVIDER=openai requires OPENAI_API_KEY")
    if values["BRAND_AI_MODEL"].startswith("ft:"):
        raise ValueError("BRAND_AI_MODEL must not use a fine-tuned model")
    if values["CUSTOM_DOMAINS_ENABLED"] not in {"true", "false"}:
        raise ValueError("CUSTOM_DOMAINS_ENABLED must be true or false")
    if values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] not in {"true", "false"}:
        raise ValueError("CUSTOM_DOMAIN_INFRASTRUCTURE_READY must be true or false")
    if values["CUSTOM_DOMAIN_PROVIDER"] not in {"disabled", "cloudflare"}:
        raise ValueError("CUSTOM_DOMAIN_PROVIDER must be disabled or cloudflare")
    if (
        values["CUSTOM_DOMAINS_ENABLED"] == "true"
        and values["CUSTOM_DOMAIN_PROVIDER"] != "cloudflare"
    ):
        raise ValueError(
            "CUSTOM_DOMAINS_ENABLED=true requires CUSTOM_DOMAIN_PROVIDER=cloudflare"
        )
    if (
        values["CUSTOM_DOMAINS_ENABLED"] == "true"
        and values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] != "true"
    ):
        raise ValueError(
            "CUSTOM_DOMAINS_ENABLED=true requires "
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY=true"
        )
    if (
        values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] == "true"
        and values["CUSTOM_DOMAIN_PROVIDER"] != "cloudflare"
    ):
        raise ValueError(
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY=true requires "
            "CUSTOM_DOMAIN_PROVIDER=cloudflare"
        )
    if (
        not values["CUSTOM_DOMAIN_MAX_PER_SITE"].isdigit()
        or not 1 <= int(values["CUSTOM_DOMAIN_MAX_PER_SITE"]) <= 100
    ):
        raise ValueError("CUSTOM_DOMAIN_MAX_PER_SITE must be between 1 and 100")
    turnstile_custom_domains_active = (
        values["CAPTCHA_REQUIRED"] == "true"
        and values["CUSTOM_DOMAINS_ENABLED"] == "true"
    )
    if turnstile_custom_domains_active:
        token = values["CLOUDFLARE_TURNSTILE_API_TOKEN"]
        if not token:
            raise ValueError(
                "CAPTCHA with custom domains requires "
                "CLOUDFLARE_TURNSTILE_API_TOKEN"
            )
        if len(token) < 20 or any(character.isspace() for character in token):
            raise ValueError("CLOUDFLARE_TURNSTILE_API_TOKEN is malformed")
        if not re.fullmatch(
            r"[A-Za-z0-9_-]{10,32}", values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"]
        ):
            raise ValueError("NEXT_PUBLIC_TURNSTILE_SITE_KEY is malformed")
        try:
            turnstile_hostname_limit = int(values["TURNSTILE_HOSTNAME_LIMIT"])
        except ValueError as error:
            raise ValueError(
                "TURNSTILE_HOSTNAME_LIMIT must be between 2 and 10"
            ) from error
        if not 2 <= turnstile_hostname_limit <= 10:
            raise ValueError("TURNSTILE_HOSTNAME_LIMIT must be between 2 and 10")
    if (
        turnstile_custom_domains_active
        and int(values["CUSTOM_DOMAIN_MAX_PER_SITE"])
        > turnstile_hostname_limit - 1
    ):
        raise ValueError(
            "CUSTOM_DOMAIN_MAX_PER_SITE must reserve one Turnstile hostname slot "
            "for WEB_HOSTNAME"
        )
    try:
        custom_domain_timeout = float(values["CLOUDFLARE_API_TIMEOUT_SECONDS"])
    except ValueError as error:
        raise ValueError(
            "CLOUDFLARE_API_TIMEOUT_SECONDS must be between 2 and 15"
        ) from error
    if not 2 <= custom_domain_timeout <= 15:
        raise ValueError("CLOUDFLARE_API_TIMEOUT_SECONDS must be between 2 and 15")
    custom_domain_provider_active = (
        values["CUSTOM_DOMAINS_ENABLED"] == "true"
        or values["CUSTOM_DOMAIN_PROVIDER"] == "cloudflare"
        or values["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"] == "true"
    )
    cloudflare_identifier = re.compile(r"^[0-9a-fA-F]{32}$")
    if custom_domain_provider_active:
        for label in (
            "CLOUDFLARE_ZONE_ID",
            "CLOUDFLARE_ACCOUNT_ID",
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID",
        ):
            if values[label] and not cloudflare_identifier.fullmatch(values[label]):
                raise ValueError(
                    f"{label} must be a 32-character Cloudflare identifier"
                )
    def require_hostname(value: str, label: str) -> None:
        hostname_labels = value.split(".")
        if (
            value != value.strip().rstrip(".")
            or len(value) > 253
            or len(hostname_labels) < 2
            or any(
                not re.fullmatch(
                    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", hostname_label
                )
                for hostname_label in hostname_labels
            )
        ):
            raise ValueError(f"{label} must be a hostname")

    cname_target = values["CUSTOM_DOMAIN_CNAME_TARGET"]
    fallback_origin = values["CUSTOM_DOMAIN_FALLBACK_ORIGIN"]
    if custom_domain_provider_active:
        missing_custom_domain_labels = sorted(
            label for label in CUSTOM_DOMAIN_PROVIDER_LABELS if not values[label]
        )
        if missing_custom_domain_labels:
            raise ValueError(
                "Cloudflare custom domains require: "
                + ", ".join(missing_custom_domain_labels)
            )
        require_hostname(cname_target, "CUSTOM_DOMAIN_CNAME_TARGET")
        require_hostname(fallback_origin, "CUSTOM_DOMAIN_FALLBACK_ORIGIN")
        if (
            fallback_origin != values["ORIGIN_HOSTNAME"]
            or cname_target == fallback_origin
        ):
            raise ValueError(
                "CUSTOM_DOMAIN_FALLBACK_ORIGIN must equal ORIGIN_HOSTNAME and "
                "differ from CUSTOM_DOMAIN_CNAME_TARGET"
            )
        script_name = re.compile(
            r"^[a-z0-9](?:[a-z0-9_-]{0,62}[a-z0-9])?$"
        )
        geo_script = values["CLOUDFLARE_GEO_EDGE_SCRIPT_NAME"]
        cdn_script = values["CLOUDFLARE_CDN_SCRIPT_NAME"]
        if (
            not script_name.fullmatch(geo_script)
            or not script_name.fullmatch(cdn_script)
            or geo_script == cdn_script
        ):
            raise ValueError(
                "Cloudflare Worker script names must be valid and distinct"
            )
        token = values["CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN"]
        if len(token) < 20 or any(character.isspace() for character in token):
            raise ValueError("CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN is malformed")
        if (
            turnstile_custom_domains_active
            and token == values["CLOUDFLARE_TURNSTILE_API_TOKEN"]
        ):
            raise ValueError(
                "Cloudflare Custom Hostnames and Turnstile must use distinct tokens"
            )
    if (
        not values["BRAND_AI_TIMEOUT_SECONDS"].isdigit()
        or not 3 <= int(values["BRAND_AI_TIMEOUT_SECONDS"]) <= 30
    ):
        raise ValueError("BRAND_AI_TIMEOUT_SECONDS must be between 3 and 30")
    if (
        not values["BRAND_AI_RATE_LIMIT_PER_HOUR"].isdigit()
        or not 1 <= int(values["BRAND_AI_RATE_LIMIT_PER_HOUR"]) <= 120
    ):
        raise ValueError("BRAND_AI_RATE_LIMIT_PER_HOUR must be between 1 and 120")
    if values["HOSTINGER_VPS_REGION"] != "Boston_2":
        raise ValueError("HOSTINGER_VPS_REGION must use the selected Boston_2 target")
    public_ipv4 = require_ip_address(
        values["HOSTINGER_VPS_IP"], "HOSTINGER_VPS_IP", version=4
    )
    public_ipv6 = require_ip_address(
        values["HOSTINGER_VPS_IPV6"], "HOSTINGER_VPS_IPV6", version=6
    )
    profile_name = values["HOSTINGER_VPS_PROFILE"]
    if profile_name not in VPS_PROFILES:
        raise ValueError("HOSTINGER_VPS_PROFILE must be compact or full")
    profile = VPS_PROFILES[profile_name]
    try:
        vps_memory = int(values["HOSTINGER_VPS_MEMORY_GB"])
        vps_vcpu = int(values["HOSTINGER_VPS_VCPU"])
    except ValueError as error:
        raise ValueError("Hostinger VPS capacity must use integer values") from error
    reserved_memory = sum(
        memory_gib(values[label]) for label in PERSISTENT_MEMORY_LABELS
    )
    if vps_memory < profile["memory_gb"] or vps_vcpu < profile["vcpu"]:
        raise ValueError(
            f"Hostinger capacity is below the {profile_name} profile floor"
        )
    if reserved_memory > vps_memory * profile["reserved_memory_ratio"]:
        headroom = round((1 - profile["reserved_memory_ratio"]) * 100)
        raise ValueError(
            f"persistent memory ceilings must leave at least {headroom}% host headroom"
        )
    images = [image_reference(values[label], label) for label in IMAGE_LABELS]
    image_digests = [image.rsplit("@sha256:", 1)[1] for image in images]
    if len(set(image_digests)) != len(image_digests):
        raise ValueError(
            "API, media worker, web, backup, Caddy, storage, node exporter, "
            "and Blackbox image digests must be distinct"
        )
    hosts = (
        values["WEB_HOSTNAME"],
        values["ORIGIN_HOSTNAME"],
        values["STORAGE_HOSTNAME"],
        values["CDN_HOSTNAME"],
    )
    if len(set(hosts)) != 4 or any("." not in host for host in hosts):
        raise ValueError("public hostnames must be distinct DNS names")
    for label in ("BACKUP_S3_ENDPOINT", "REPLICA_S3_ENDPOINT"):
        require_https_origin(values[label], label)
    if deploy:
        required_for_deploy = labels - OPTIONAL_LABELS
        required_for_deploy.update(active_conditional_labels(values))
        dummy = sorted(
            key for key in required_for_deploy if "DUMMY" in values[key].upper()
        )
        if dummy:
            raise ValueError("replace dummy labels before deploy: " + ", ".join(dummy))
        if not public_ipv4.is_global:
            raise ValueError("HOSTINGER_VPS_IP must be a public IPv4 address")
        if not public_ipv6.is_global:
            raise ValueError("HOSTINGER_VPS_IPV6 must be a public IPv6 address")
        for key in (
            "POSTGRES_PASSWORD",
            "REDIS_PASSWORD",
            "MINIO_ROOT_PASSWORD",
            "SESSION_SECRET",
            "STUDIO_EDGE_SECRET",
            "METRICS_BEARER_TOKEN",
            "CDN_SIGNING_SECRET",
            "CDN_ORIGIN_SECRET",
            "GEO_ASSERTION_SECRET",
            "BACKUP_S3_SECRET_KEY",
            "REPLICA_S3_SECRET_KEY",
            "ORIGIN_EDGE_SECRET",
            "CUSTOM_DOMAIN_EDGE_SECRET",
        ):
            if len(values[key]) < 32:
                raise ValueError(f"{key} must contain at least 32 characters")
        if values["POLICY_REQUIRE_APPROVED"].lower() != "true":
            raise ValueError("POLICY_REQUIRE_APPROVED must be true for deployment")
        if any(value.endswith("0" * 64) for value in images):
            raise ValueError(
                "production image digests must not use the dummy zero digest"
            )


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), required=True)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument(
        "--require-hostinger-api-token",
        action="store_true",
        help="fail unless a non-placeholder local token is present for a Hostinger API call",
    )
    args = parser.parse_args(argv)
    validate(
        load(args.input),
        deploy=args.mode == "deploy",
        require_hostinger_token=args.require_hostinger_api_token,
    )
    print("Hostinger VPS configuration is structurally valid.")


if __name__ == "__main__":
    main()
