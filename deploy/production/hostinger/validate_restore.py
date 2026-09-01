"""Fail closed before an isolated Hostinger restore container is started."""

import argparse
import stat
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
        if key in values:
            raise ValueError(f"duplicate label: {key}")
        values[key] = value
    missing = sorted(REQUIRED - values.keys())
    if missing:
        raise ValueError("missing labels: " + ", ".join(missing))
    unexpected = sorted(values.keys() - REQUIRED)
    if unexpected:
        raise ValueError("unexpected labels: " + ", ".join(unexpected))
    return values


def validate_input_file(path: Path, *, expected_owner_uid: int) -> None:
    """Require a protected, non-symlink one-shot input in a protected directory."""
    try:
        metadata = path.lstat()
        parent = path.parent.lstat()
    except OSError as error:
        raise ValueError("restore input is unavailable") from error

    if not stat.S_ISREG(metadata.st_mode) or path.is_symlink():
        raise ValueError("restore input must be a regular non-symlink file")
    if stat.S_IMODE(metadata.st_mode) != 0o600:
        raise ValueError("restore input mode must be 0600")
    if metadata.st_uid != expected_owner_uid:
        raise ValueError("restore input owner is invalid")

    if not stat.S_ISDIR(parent.st_mode) or path.parent.is_symlink():
        raise ValueError("restore input parent must be a non-symlink directory")
    if parent.st_uid != expected_owner_uid or stat.S_IMODE(parent.st_mode) & 0o022:
        raise ValueError("restore input parent is not owner-protected")


def validate(values: dict[str, str]) -> None:
    empty = sorted(key for key in REQUIRED if not values.get(key))
    if empty:
        raise ValueError("empty labels: " + ", ".join(empty))
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
    parser.add_argument("--expected-owner-uid", type=int, default=0)
    args = parser.parse_args()
    validate_input_file(args.input, expected_owner_uid=args.expected_owner_uid)
    validate(load(args.input))
    print("Isolated restore configuration is valid.")


if __name__ == "__main__":
    main()
