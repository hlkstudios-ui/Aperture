"""Validate labeled free-tier staging inputs without contacting providers."""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
DEFAULT_INPUT = PROJECT_ROOT / ".env"
EXAMPLE_INPUT = ROOT / "credentials.example.env"
REQUIRED = {
    "STAGING_WEB_ORIGIN", "STAGING_API_ORIGIN", "STAGING_COOKIE_DOMAIN",
    "DATABASE_URL", "REDIS_URL", "S3_ENDPOINT", "S3_PUBLIC_ENDPOINT",
    "S3_REGION", "S3_BUCKET", "S3_ACCESS_KEY", "S3_SECRET_KEY",
    "SESSION_SECRET", "METRICS_BEARER_TOKEN", "GEO_ASSERTION_SECRET",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USERNAME", "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL", "ERROR_TRACKING_DSN", "FEATURE_SCENE_LENS_ENABLED",
    "BRAND_AI_PROVIDER", "BRAND_AI_MODEL", "BRAND_AI_TIMEOUT_SECONDS",
    "BRAND_AI_RATE_LIMIT_PER_HOUR", "OPENAI_API_KEY",
    "FEATURE_ASK_MOVIE_ENABLED", "FEATURE_COMMUNITY_ENABLED",
    "FEATURE_WATCH_PARTIES_ENABLED", "FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED",
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
        if key not in REQUIRED:
            continue
        if key in values:
            raise ValueError(f"duplicate label: {key}")
        values[key] = value
    missing = sorted(REQUIRED - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    return values


def validate(values: dict[str, str], deploy: bool) -> None:
    for key in ("STAGING_WEB_ORIGIN", "STAGING_API_ORIGIN", "S3_ENDPOINT", "S3_PUBLIC_ENDPOINT"):
        parsed = urlparse(values[key])
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"{key} must be an HTTPS origin")
    if not values["DATABASE_URL"].startswith("postgresql+psycopg://"):
        raise ValueError("DATABASE_URL must use postgresql+psycopg")
    if "sslmode=require" not in values["DATABASE_URL"]:
        raise ValueError("DATABASE_URL must require TLS")
    if not values["REDIS_URL"].startswith("rediss://"):
        raise ValueError("REDIS_URL must use TLS (rediss://)")
    if values["S3_REGION"] != "auto":
        raise ValueError("Cloudflare R2 staging uses S3_REGION=auto")
    for key in ("SESSION_SECRET", "METRICS_BEARER_TOKEN", "GEO_ASSERTION_SECRET"):
        if len(values[key]) < 32:
            raise ValueError(f"{key} must contain at least 32 characters")
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
    features = sorted(key for key in REQUIRED if key.startswith("FEATURE_"))
    invalid = [key for key in features if values[key] not in {"true", "false"}]
    if invalid:
        raise ValueError("feature labels must be true or false: " + ", ".join(invalid))
    if values["FEATURE_ASK_MOVIE_ENABLED"] == "true" and values["FEATURE_SCENE_LENS_ENABLED"] != "true":
        raise ValueError("Ask This Movie requires SceneLens")
    if values["FEATURE_WATCH_PARTIES_ENABLED"] == "true" and values["FEATURE_COMMUNITY_ENABLED"] != "true":
        raise ValueError("watch parties require Community")
    if deploy:
        dummy = sorted(key for key, value in values.items() if "DUMMY" in value.upper())
        if dummy:
            raise ValueError("replace dummy labels before staging deploy: " + ", ".join(dummy))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("dummy", "deploy"), default="dummy")
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    validate(load(args.input), deploy=args.mode == "deploy")
    print(f"Free-tier staging inputs passed {args.mode} validation; no network calls were made.")


if __name__ == "__main__":
    main()
