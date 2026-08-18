"""Render local DigitalOcean files without printing credential values."""

import argparse
import copy
import os
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent
CREDENTIALS = ROOT / "credentials.local.env"
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
DO_BINDABLES = {
    "aperture-postgres.DATABASE_PRIVATE_URL",
    "aperture-valkey.REDIS_URL",
}


def load_values() -> dict[str, str]:
    values: dict[str, str] = {}
    for line_number, raw in enumerate(CREDENTIALS.read_text().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"invalid credentials.local.env line {line_number}")
        key, value = line.split("=", 1)
        if key not in OWNER_KEYS:
            raise ValueError(f"unknown credential label: {key}")
        values[key] = value
    missing = sorted(OWNER_KEYS - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    return values


def validate_deploy_values(values: dict[str, str]) -> None:
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
    document = yaml.safe_load(render(APP_TEMPLATE.read_text(), values))
    api_envs = document.pop("x-api-envs")
    backup_envs = document.pop("x-backup-envs")
    api_jobs = [item for item in document["jobs"] if item["name"] != "postgres-backup"]
    for component in [*api_jobs, document["services"][0], *document["workers"]]:
        component["envs"] = copy.deepcopy(api_envs)
    next(item for item in document["jobs"] if item["name"] == "postgres-backup")[
        "envs"
    ] = copy.deepcopy(backup_envs)
    return yaml.safe_dump(document, sort_keys=False)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), default="dummy")
    args = parser.parse_args()
    values = load_values()
    if args.mode == "deploy":
        validate_deploy_values(values)
    write_private(APP_OUTPUT, render_app(values))
    print(
        f"Rendered 1 local file in {args.mode} mode; credential values were not printed."
    )


if __name__ == "__main__":
    main()
