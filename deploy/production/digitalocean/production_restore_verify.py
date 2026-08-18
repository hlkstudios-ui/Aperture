"""Download and verify one production backup into a pre-created isolated database."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import boto3
from botocore.config import Config

from production_backup import command_output, postgres_connection

REQUIRED_ENV = (
    "RESTORE_DATABASE_URL",
    "RESTORE_MANIFEST_KEY",
    "BACKUP_S3_ENDPOINT",
    "BACKUP_S3_REGION",
    "BACKUP_S3_BUCKET",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
)
CONFIRMATION = "RESTORE_TO_ISOLATED_EMPTY_DATABASE"


def required_environment() -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        raise RuntimeError("missing restore configuration labels: " + ", ".join(missing))
    if os.environ.get("RESTORE_CONFIRMATION") != CONFIRMATION:
        raise RuntimeError("RESTORE_CONFIRMATION does not authorize an isolated restore")
    return {key: os.environ[key] for key in REQUIRED_ENV}


def validate_manifest(raw: bytes, manifest_key: str) -> dict[str, object]:
    value = json.loads(raw)
    required = {
        "format_version",
        "created_at",
        "dump_key",
        "sha256",
        "size_bytes",
        "migration_head",
        "public_table_count",
    }
    if not isinstance(value, dict) or not required.issubset(value):
        raise ValueError("backup manifest is incomplete")
    if value["format_version"] != 1:
        raise ValueError("backup manifest version is unsupported")
    expected_dump_key = manifest_key.removesuffix(".manifest.json") + ".dump"
    if value["dump_key"] != expected_dump_key:
        raise ValueError("backup manifest dump key does not match its object key")
    checksum = value["sha256"]
    if not isinstance(checksum, str) or len(checksum) != 64:
        raise ValueError("backup manifest checksum is invalid")
    if not isinstance(value["size_bytes"], int) or value["size_bytes"] <= 0:
        raise ValueError("backup manifest size is invalid")
    if not isinstance(value["public_table_count"], int) or value["public_table_count"] <= 0:
        raise ValueError("backup manifest table count is invalid")
    return value


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_restore() -> dict[str, object]:
    config = required_environment()
    connection_args, process_env = postgres_connection(config["RESTORE_DATABASE_URL"])
    database_name = connection_args[connection_args.index("--dbname") + 1]
    if not database_name.startswith("aperture_restore_"):
        raise ValueError("restore target database name must start with aperture_restore_")

    client = boto3.client(
        "s3",
        endpoint_url=config["BACKUP_S3_ENDPOINT"],
        region_name=config["BACKUP_S3_REGION"],
        aws_access_key_id=config["BACKUP_S3_ACCESS_KEY"],
        aws_secret_access_key=config["BACKUP_S3_SECRET_KEY"],
        config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
    )
    started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="aperture-restore-") as temporary:
        manifest_response = client.get_object(
            Bucket=config["BACKUP_S3_BUCKET"], Key=config["RESTORE_MANIFEST_KEY"]
        )
        manifest = validate_manifest(
            manifest_response["Body"].read(), config["RESTORE_MANIFEST_KEY"]
        )
        existing_tables = int(
            command_output(
                [
                    "psql",
                    *connection_args,
                    "--tuples-only",
                    "--no-align",
                    "--command",
                    "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'",
                ],
                process_env,
            )
        )
        if existing_tables != 0:
            raise RuntimeError("restore target database is not empty")
        dump_path = Path(temporary) / "database.dump"
        client.download_file(
            config["BACKUP_S3_BUCKET"], str(manifest["dump_key"]), str(dump_path)
        )
        if dump_path.stat().st_size != manifest["size_bytes"]:
            raise ValueError("downloaded backup size does not match manifest")
        if sha256_file(dump_path) != manifest["sha256"]:
            raise ValueError("downloaded backup checksum does not match manifest")
        subprocess.run(
            [
                "pg_restore",
                *connection_args,
                "--no-owner",
                "--no-privileges",
                "--exit-on-error",
                str(dump_path),
            ],
            check=True,
            env=process_env,
            timeout=3600,
        )
        restored_head = command_output(
            ["psql", *connection_args, "--tuples-only", "--no-align", "--command", "SELECT version_num FROM alembic_version"],
            process_env,
        )
        restored_tables = int(
            command_output(
                ["psql", *connection_args, "--tuples-only", "--no-align", "--command", "SELECT count(*) FROM pg_tables WHERE schemaname = 'public'"],
                process_env,
            )
        )
        if restored_head != manifest["migration_head"] or restored_tables != manifest["public_table_count"]:
            raise RuntimeError("restored database does not match backup manifest")
    return {
        "status": "pass",
        "migration_head": restored_head,
        "public_table_count": restored_tables,
        "elapsed_seconds": round(time.monotonic() - started, 3),
    }


def main() -> int:
    try:
        result = run_restore()
    except Exception:
        print(json.dumps({"event": "restore.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps({"event": "restore.verified", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
