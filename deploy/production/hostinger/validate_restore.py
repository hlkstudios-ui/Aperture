"""Fail closed before an isolated Hostinger restore container is started."""

import argparse
from pathlib import Path
from urllib.parse import urlsplit

REQUIRED = {
    "RESTORE_DATABASE_URL",
    "RESTORE_MANIFEST_KEY",
    "RESTORE_CONFIRMATION",
    "BACKUP_S3_ENDPOINT",
    "BACKUP_S3_REGION",
    "BACKUP_S3_BUCKET",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
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
        if key in REQUIRED:
            values[key] = value
    missing = sorted(REQUIRED - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    return values


def validate(values: dict[str, str]) -> None:
    dummy = sorted(key for key, value in values.items() if "DUMMY" in value.upper())
    if dummy:
        raise ValueError("replace dummy labels before restore: " + ", ".join(dummy))
    parsed = urlsplit(values["RESTORE_DATABASE_URL"].replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("RESTORE_DATABASE_URL must be PostgreSQL")
    if not parsed.path.removeprefix("/").startswith("aperture_restore_"):
        raise ValueError("restore database name must start with aperture_restore_")
    if values["RESTORE_CONFIRMATION"] != "RESTORE_TO_ISOLATED_EMPTY_DATABASE":
        raise ValueError("restore confirmation is invalid")
    if not values["RESTORE_MANIFEST_KEY"].endswith(".manifest.json"):
        raise ValueError("restore manifest key is invalid")
    if urlsplit(values["BACKUP_S3_ENDPOINT"]).scheme != "https":
        raise ValueError("backup endpoint must use HTTPS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(load(args.input))
    print("Isolated restore configuration is valid.")


if __name__ == "__main__":
    main()
