"""Create a private PostgreSQL custom dump and checksum manifest in backup Spaces."""

import hashlib
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import boto3
from botocore.config import Config

REQUIRED_ENV = (
    "BACKUP_DATABASE_URL",
    "BACKUP_S3_ENDPOINT",
    "BACKUP_S3_REGION",
    "BACKUP_S3_BUCKET",
    "BACKUP_S3_ACCESS_KEY",
    "BACKUP_S3_SECRET_KEY",
)


def required_environment() -> dict[str, str]:
    missing = [key for key in REQUIRED_ENV if not os.environ.get(key)]
    if missing:
        raise RuntimeError("missing backup configuration labels: " + ", ".join(missing))
    return {key: os.environ[key] for key in REQUIRED_ENV}


def postgres_connection(url: str) -> tuple[list[str], dict[str, str]]:
    normalized = url.replace("postgresql+psycopg://", "postgresql://", 1)
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise ValueError("BACKUP_DATABASE_URL must be PostgreSQL")
    if not all((parsed.hostname, parsed.username, parsed.path.removeprefix("/"))):
        raise ValueError("BACKUP_DATABASE_URL is incomplete")
    query = parse_qs(parsed.query)
    args = [
        "--host",
        parsed.hostname,
        "--port",
        str(parsed.port or 5432),
        "--username",
        unquote(parsed.username),
        "--dbname",
        unquote(parsed.path.removeprefix("/")),
    ]
    process_env = os.environ.copy()
    process_env["PGPASSWORD"] = unquote(parsed.password or "")
    process_env["PGSSLMODE"] = query.get("sslmode", ["require"])[0]
    return args, process_env


def command_output(command: list[str], process_env: dict[str, str]) -> str:
    result = subprocess.run(
        command,
        check=True,
        capture_output=True,
        text=True,
        env=process_env,
        timeout=120,
    )
    return result.stdout.strip()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_backup() -> dict[str, object]:
    config = required_environment()
    connection_args, process_env = postgres_connection(config["BACKUP_DATABASE_URL"])
    instant = datetime.now(UTC)
    prefix = instant.strftime("postgres/%Y/%m/%d/%Y%m%dT%H%M%SZ")
    with tempfile.TemporaryDirectory(prefix="aperture-backup-") as temporary:
        dump_path = Path(temporary) / "database.dump"
        subprocess.run(
            [
                "pg_dump",
                *connection_args,
                "--format=custom",
                "--no-owner",
                "--no-acl",
                "--file",
                str(dump_path),
            ],
            check=True,
            env=process_env,
            timeout=3600,
        )
        migration_head = command_output(
            [
                "psql",
                *connection_args,
                "--tuples-only",
                "--no-align",
                "--command",
                "SELECT version_num FROM alembic_version",
            ],
            process_env,
        )
        table_count = int(
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
        checksum = sha256_file(dump_path)
        manifest = {
            "format_version": 1,
            "created_at": instant.isoformat(),
            "dump_key": f"{prefix}.dump",
            "sha256": checksum,
            "size_bytes": dump_path.stat().st_size,
            "migration_head": migration_head,
            "public_table_count": table_count,
        }
        client = boto3.client(
            "s3",
            endpoint_url=config["BACKUP_S3_ENDPOINT"],
            region_name=config["BACKUP_S3_REGION"],
            aws_access_key_id=config["BACKUP_S3_ACCESS_KEY"],
            aws_secret_access_key=config["BACKUP_S3_SECRET_KEY"],
            config=Config(s3={"addressing_style": "path"}, signature_version="s3v4"),
        )
        client.upload_file(
            str(dump_path),
            config["BACKUP_S3_BUCKET"],
            manifest["dump_key"],
            ExtraArgs={"ContentType": "application/octet-stream"},
        )
        client.put_object(
            Bucket=config["BACKUP_S3_BUCKET"],
            Key=f"{prefix}.manifest.json",
            Body=json.dumps(manifest, sort_keys=True).encode(),
            ContentType="application/json",
        )
    return {"status": "pass", "manifest_key": f"{prefix}.manifest.json"}


def main() -> int:
    try:
        result = run_backup()
    except Exception:
        # Keep provider URLs, database identifiers, and subprocess details out of job logs.
        print(json.dumps({"event": "backup.failed", "status": "fail"}), file=sys.stderr)
        return 1
    print(json.dumps({"event": "backup.completed", **result}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
