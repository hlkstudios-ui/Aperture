import importlib.util
import json
from pathlib import Path
from unittest.mock import Mock

MODULE_PATH = (
    Path(__file__).parents[3] / "deploy" / "production" / "digitalocean" / "production_backup.py"
)
SPEC = importlib.util.spec_from_file_location("production_backup", MODULE_PATH)
assert SPEC and SPEC.loader
production_backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(production_backup)


def test_postgres_connection_keeps_password_out_of_arguments(monkeypatch) -> None:
    monkeypatch.setenv("UNRELATED", "preserved")
    args, process_env = production_backup.postgres_connection(
        "postgresql+psycopg://backup-user:p%40ssword@private-db:25060/aperture?sslmode=require"
    )
    assert args == [
        "--host",
        "private-db",
        "--port",
        "25060",
        "--username",
        "backup-user",
        "--dbname",
        "aperture",
    ]
    assert "p@ssword" not in " ".join(args)
    assert process_env["PGPASSWORD"] == "p@ssword"
    assert process_env["PGSSLMODE"] == "require"
    assert process_env["UNRELATED"] == "preserved"


def test_backup_uploads_without_object_acls(monkeypatch) -> None:
    for key, value in {
        "BACKUP_DATABASE_URL": "postgresql://backup:secret@database/aperture",
        "BACKUP_S3_ENDPOINT": "https://s3.example.com",
        "BACKUP_S3_REGION": "region-1",
        "BACKUP_S3_BUCKET": "aperture-backups",
        "BACKUP_S3_ACCESS_KEY": "access-key",
        "BACKUP_S3_SECRET_KEY": "secret-key",
    }.items():
        monkeypatch.setenv(key, value)

    def create_dump(command, **_kwargs) -> None:
        dump_path = Path(command[command.index("--file") + 1])
        dump_path.write_bytes(b"database dump")

    outputs = iter(("migration-head", "3"))
    client = Mock()
    monkeypatch.setattr(production_backup.subprocess, "run", create_dump)
    monkeypatch.setattr(
        production_backup, "command_output", lambda *_args: next(outputs)
    )
    monkeypatch.setattr(production_backup.boto3, "client", Mock(return_value=client))

    assert production_backup.run_backup()["status"] == "pass"

    upload_args = client.upload_file.call_args.kwargs["ExtraArgs"]
    assert upload_args == {"ContentType": "application/octet-stream"}
    put_args = client.put_object.call_args.kwargs
    assert put_args["ContentType"] == "application/json"
    assert "ACL" not in upload_args
    assert "ACL" not in put_args


def test_main_redacts_failure_details(monkeypatch, capsys) -> None:
    secret = "do-not-print-this-database-password"

    def fail() -> dict[str, object]:
        raise RuntimeError(secret)

    monkeypatch.setattr(production_backup, "run_backup", fail)
    assert production_backup.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert secret not in captured.err
    assert json.loads(captured.err) == {"event": "backup.failed", "status": "fail"}
