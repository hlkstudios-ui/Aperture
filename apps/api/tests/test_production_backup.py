import importlib.util
import json
from pathlib import Path

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
