"""Render local DigitalOcean files without printing credential values."""

import argparse
import copy
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
DEFAULT_INPUT = PROJECT_ROOT / ".env"
EXAMPLE_INPUT = ROOT / "credentials.example.env"
APP_TEMPLATE = ROOT / "app.template.yaml"
APP_OUTPUT = ROOT / "app.local.yaml"
OWNER_KEYS = {
    "DNS_ZONE",
    "WEB_HOSTNAME",
    "ADMIN_WEB_ORIGIN",
    "CDN_HOSTNAME",
    "GITHUB_REPOSITORY",
    "DEPLOY_BRANCH",
    "POSTGRES_CLUSTER_NAME",
    "VALKEY_CLUSTER_NAME",
    "SPACES_BUCKET",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "SESSION_SECRET",
    "STUDIO_EDGE_SECRET",
    "METRICS_BEARER_TOKEN",
    "CDN_SIGNING_SECRET",
    "CDN_ORIGIN_SECRET",
    "GEO_ASSERTION_SECRET",
    "GEO_EDGE_ORIGIN_WEB",
    "OAUTH_GOOGLE_CLIENT_ID",
    "OAUTH_GOOGLE_CLIENT_SECRET",
    "OAUTH_MICROSOFT_CLIENT_ID",
    "OAUTH_MICROSOFT_CLIENT_SECRET",
    "OAUTH_GITHUB_CLIENT_ID",
    "OAUTH_GITHUB_CLIENT_SECRET",
    "OAUTH_APPLE_CLIENT_ID",
    "OAUTH_APPLE_CLIENT_SECRET",
    "CAPTCHA_REQUIRED",
    "NEXT_PUBLIC_TURNSTILE_SITE_KEY",
    "TURNSTILE_SECRET_KEY",
    "BRAND_AI_PROVIDER",
    "BRAND_AI_MODEL",
    "BRAND_AI_TIMEOUT_SECONDS",
    "BRAND_AI_RATE_LIMIT_PER_HOUR",
    "OPENAI_API_KEY",
    "FEATURE_SCENE_LENS_ENABLED",
    "FEATURE_ASK_MOVIE_ENABLED",
    "FEATURE_COMMUNITY_ENABLED",
    "FEATURE_WATCH_PARTIES_ENABLED",
    "FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED",
    "POLICY_REQUIRE_APPROVED",
    "MALWARE_SCANNER_HOST",
    "MALWARE_SCANNER_PORT",
    "STRIPE_SECRET_KEY",
    "STRIPE_WEBHOOK_SECRET",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
    "ERROR_TRACKING_DSN",
    "BACKUP_S3_BUCKET",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
    "BACKUP_RETENTION_DAYS",
    "RECOVERY_POINT_OBJECTIVE_HOURS",
    "RECOVERY_TIME_OBJECTIVE_HOURS",
}
OAUTH_PAIRS = (
    ("OAUTH_GOOGLE_CLIENT_ID", "OAUTH_GOOGLE_CLIENT_SECRET"),
    ("OAUTH_MICROSOFT_CLIENT_ID", "OAUTH_MICROSOFT_CLIENT_SECRET"),
    ("OAUTH_GITHUB_CLIENT_ID", "OAUTH_GITHUB_CLIENT_SECRET"),
    ("OAUTH_APPLE_CLIENT_ID", "OAUTH_APPLE_CLIENT_SECRET"),
)
DO_BINDABLES = {
    "aperture-postgres.DATABASE_PRIVATE_URL",
    "aperture-valkey.REDIS_URL",
}


def load_values(path: Path = DEFAULT_INPUT) -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(path.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid dotenv line {line_number}")
        key, value = line.split("=", 1)
        if key not in OWNER_KEYS:
            continue
        if key in values:
            raise ValueError(f"duplicate credential label: {key}")
        values[key] = value
    missing = sorted(OWNER_KEYS - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    return values


def validate_deploy_values(values: dict[str, str]) -> None:
    validate_auth_values(values)
    dummy = sorted(key for key, value in values.items() if "DUMMY" in value)
    if dummy:
        raise ValueError("replace dummy labels before deploy: " + ", ".join(dummy))
    if not values["STRIPE_SECRET_KEY"].startswith("sk_live_"):
        raise ValueError("STRIPE_SECRET_KEY must be a live key in deploy mode")
    if not values["STRIPE_WEBHOOK_SECRET"].startswith("whsec_"):
        raise ValueError("STRIPE_WEBHOOK_SECRET must be a webhook signing secret")
    if any(
        len(values[key]) < 32
        for key in (
            "SESSION_SECRET",
            "STUDIO_EDGE_SECRET",
            "METRICS_BEARER_TOKEN",
            "CDN_SIGNING_SECRET",
            "CDN_ORIGIN_SECRET",
            "GEO_ASSERTION_SECRET",
        )
    ):
        raise ValueError("application security secrets must be at least 32 characters")
    feature_keys = tuple(key for key in OWNER_KEYS if key.startswith("FEATURE_"))
    invalid_features = sorted(key for key in feature_keys if values[key] not in {"true", "false"})
    if invalid_features:
        raise ValueError("feature labels must be true or false: " + ", ".join(invalid_features))
    if values["FEATURE_ASK_MOVIE_ENABLED"] == "true" and values["FEATURE_SCENE_LENS_ENABLED"] != "true":
        raise ValueError("FEATURE_ASK_MOVIE_ENABLED requires FEATURE_SCENE_LENS_ENABLED")
    if values["FEATURE_WATCH_PARTIES_ENABLED"] == "true" and values["FEATURE_COMMUNITY_ENABLED"] != "true":
        raise ValueError("FEATURE_WATCH_PARTIES_ENABLED requires FEATURE_COMMUNITY_ENABLED")
    if values["POLICY_REQUIRE_APPROVED"] != "true":
        raise ValueError("POLICY_REQUIRE_APPROVED must be true in deploy mode")
    if not values["MALWARE_SCANNER_PORT"].isdigit() or not 1 <= int(values["MALWARE_SCANNER_PORT"]) <= 65535:
        raise ValueError("MALWARE_SCANNER_PORT must be between 1 and 65535")


def validate_auth_values(values: dict[str, str]) -> None:
    if values["CAPTCHA_REQUIRED"] not in {"true", "false"}:
        raise ValueError("CAPTCHA_REQUIRED must be true or false")
    if values["CAPTCHA_REQUIRED"] == "true" and not all(
        values[key] for key in ("NEXT_PUBLIC_TURNSTILE_SITE_KEY", "TURNSTILE_SECRET_KEY")
    ):
        raise ValueError(
            "CAPTCHA_REQUIRED requires both NEXT_PUBLIC_TURNSTILE_SITE_KEY "
            "and TURNSTILE_SECRET_KEY"
        )
    for client_id, client_secret in OAUTH_PAIRS:
        if bool(values[client_id]) != bool(values[client_secret]):
            raise ValueError(f"{client_id} and {client_secret} must be configured together")
    if values["BRAND_AI_PROVIDER"] not in {"disabled", "openai"}:
        raise ValueError("BRAND_AI_PROVIDER must be disabled or openai")
    if values["BRAND_AI_PROVIDER"] == "openai" and not values["OPENAI_API_KEY"]:
        raise ValueError("BRAND_AI_PROVIDER=openai requires OPENAI_API_KEY")
    if values["BRAND_AI_MODEL"].startswith("ft:"):
        raise ValueError("BRAND_AI_MODEL must not use a fine-tuned model")
    if not values["BRAND_AI_TIMEOUT_SECONDS"].isdigit() or not 3 <= int(
        values["BRAND_AI_TIMEOUT_SECONDS"]
    ) <= 30:
        raise ValueError("BRAND_AI_TIMEOUT_SECONDS must be between 3 and 30")
    if not values["BRAND_AI_RATE_LIMIT_PER_HOUR"].isdigit() or not 1 <= int(
        values["BRAND_AI_RATE_LIMIT_PER_HOUR"]
    ) <= 120:
        raise ValueError("BRAND_AI_RATE_LIMIT_PER_HOUR must be between 1 and 120")


def render(template: str, values: dict[str, str]) -> str:
    def replacement(match: re.Match[str]) -> str:
        key = match.group(1)
        if key in DO_BINDABLES:
            return match.group(0)
        if key not in values:
            raise ValueError(f"template references unknown label: {key}")
        return values[key]

    return re.sub(r"\$\{([^}]+)\}", replacement, template)


def write_private(path: Path, content: str) -> None:
    path.write_text(content)
    os.chmod(path, 0o600)


def render_app(values: dict[str, str]) -> str:
    validate_auth_values(values)
    document = yaml.safe_load(render(APP_TEMPLATE.read_text(), values))
    api_envs = document.pop("x-api-envs")
    api_auth_envs = document.pop("x-api-auth-envs")
    optional_api_keys = {
        "TURNSTILE_SECRET_KEY",
        "OPENAI_API_KEY",
        *(label for pair in OAUTH_PAIRS for label in pair),
    }
    api_auth_envs = [
        item
        for item in api_auth_envs
        if item["key"] not in optional_api_keys or values[item["key"]]
    ]
    backup_envs = document.pop("x-backup-envs")
    api_jobs = [item for item in document["jobs"] if item["name"] != "postgres-backup"]
    for component in [*api_jobs, *document["workers"]]:
        component["envs"] = copy.deepcopy(api_envs)
    api = next(item for item in document["services"] if item["name"] == "api")
    api["envs"] = copy.deepcopy([*api_envs, *api_auth_envs])
    next(item for item in document["jobs"] if item["name"] == "postgres-backup")[
        "envs"
    ] = copy.deepcopy(backup_envs)
    web = next(item for item in document["services"] if item["name"] == "web")
    if not values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"]:
        web["envs"] = [
            item for item in web["envs"] if item["key"] != "NEXT_PUBLIC_TURNSTILE_SITE_KEY"
        ]
    return yaml.safe_dump(document, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), default="dummy")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    values = load_values(args.input)
    if args.mode == "deploy":
        validate_deploy_values(values)
    write_private(APP_OUTPUT, render_app(values))
    print(
        f"Rendered 1 local file in {args.mode} mode; credential values were not printed."
    )


if __name__ == "__main__":
    main()
