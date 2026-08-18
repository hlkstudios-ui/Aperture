import hashlib
import importlib.util
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).parents[3] / "deploy" / "production" / "digitalocean"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPT_DIR / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


load("production_backup", "production_backup.py")
restore = load("production_restore_verify", "production_restore_verify.py")


def manifest(**overrides) -> dict[str, object]:
    value = {
        "format_version": 1,
        "created_at": "2026-08-16T03:17:00+00:00",
        "dump_key": "postgres/2026/08/16/20260816T031700Z.dump",
        "sha256": hashlib.sha256(b"dump").hexdigest(),
        "size_bytes": 4,
        "migration_head": "94f37d54a8bc",
        "public_table_count": 90,
    }
    value.update(overrides)
    return value


def test_manifest_requires_matching_dump_object_and_valid_evidence() -> None:
    key = "postgres/2026/08/16/20260816T031700Z.manifest.json"
    assert restore.validate_manifest(json.dumps(manifest()).encode(), key)["size_bytes"] == 4

    for bad in (
        manifest(dump_key="postgres/unrelated.dump"),
        manifest(sha256="short"),
        manifest(size_bytes=0),
        manifest(public_table_count=0),
    ):
        try:
            restore.validate_manifest(json.dumps(bad).encode(), key)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe manifest was accepted")


def test_restore_requires_explicit_confirmation(monkeypatch) -> None:
    for label in restore.REQUIRED_ENV:
        monkeypatch.setenv(label, "configured")
    monkeypatch.delenv("RESTORE_CONFIRMATION", raising=False)
    try:
        restore.required_environment()
    except RuntimeError as error:
        assert "confirmation" in str(error).lower()
    else:
        raise AssertionError("restore ran without explicit confirmation")


def test_restore_failure_log_redacts_details(monkeypatch, capsys) -> None:
    secret = "never-log-restore-password"

    def fail() -> dict[str, object]:
        raise RuntimeError(secret)

    monkeypatch.setattr(restore, "run_restore", fail)
    assert restore.main() == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert secret not in captured.err
    assert json.loads(captured.err) == {"event": "restore.failed", "status": "fail"}
