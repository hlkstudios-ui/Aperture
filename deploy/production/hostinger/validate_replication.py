"""Validate independent media-replica inputs before copying any object."""

import argparse
from pathlib import Path
from urllib.parse import urlsplit


def load(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def validate(values: dict[str, str]) -> None:
    required = {
        "S3_BUCKET", "REPLICA_S3_ENDPOINT", "REPLICA_S3_BUCKET",
        "REPLICA_S3_ACCESS_KEY", "REPLICA_S3_SECRET_KEY",
    }
    missing = sorted(key for key in required if not values.get(key))
    if missing:
        raise ValueError("missing replication labels: " + ", ".join(missing))
    dummy = sorted(key for key in required if "DUMMY" in values[key].upper())
    if dummy:
        raise ValueError("replace dummy labels before replication: " + ", ".join(dummy))
    endpoint = urlsplit(values["REPLICA_S3_ENDPOINT"])
    if endpoint.scheme != "https" or not endpoint.hostname or endpoint.path not in {"", "/"}:
        raise ValueError("REPLICA_S3_ENDPOINT must be an HTTPS origin")
    if endpoint.hostname in {"localhost", "127.0.0.1", "minio"}:
        raise ValueError("media replica must be outside the Hostinger VPS")
    if values["REPLICA_S3_BUCKET"] == values["S3_BUCKET"]:
        raise ValueError("replica bucket must differ from the production media bucket")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    validate(load(args.input))
    print("Independent media replication configuration is valid.")


if __name__ == "__main__":
    main()
