import importlib.util
import json
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[3]
    / "deploy"
    / "production"
    / "digitalocean"
    / "digitalocean_rollback.py"
)
INPUT_PATH = MODULE_PATH.with_name("rollback.example.env")
SPEC = importlib.util.spec_from_file_location("digitalocean_rollback", MODULE_PATH)
assert SPEC and SPEC.loader
rollback = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(rollback)

APP_ID = "11111111-1111-4111-8111-111111111111"
TARGET_ID = "22222222-2222-4222-8222-222222222222"


def configure(monkeypatch) -> None:
    monkeypatch.setenv("DIGITALOCEAN_APP_ID", APP_ID)
    monkeypatch.setenv("DIGITALOCEAN_ROLLBACK_DEPLOYMENT_ID", TARGET_ID)
    monkeypatch.setenv("DIGITALOCEAN_TOKEN", "private-operator-token")
    monkeypatch.setenv("ROLLBACK_CONFIRMATION", "")


def test_dummy_mode_never_calls_provider(monkeypatch) -> None:
    monkeypatch.setattr(rollback, "api_request", lambda *args, **kwargs: 1 / 0)
    assert rollback.run("dummy") == {
        "event": "rollback.dummy_validated",
        "status": "pass",
    }


def test_inspection_requires_exact_active_target(monkeypatch) -> None:
    configure(monkeypatch)
    monkeypatch.setattr(
        rollback,
        "api_request",
        lambda path, token: {
            "deployment": {
                "id": TARGET_ID,
                "phase": "ACTIVE",
                "created_at": "2026-08-16T12:00:00Z",
            }
        },
    )
    result = rollback.run("inspect", INPUT_PATH)
    assert result["event"] == "rollback.target_inspected"
    assert result["deployment_id"] == TARGET_ID


def test_execute_requires_confirmation_and_posts_exact_target(monkeypatch) -> None:
    configure(monkeypatch)
    try:
        rollback.run("execute", INPUT_PATH)
    except RuntimeError as error:
        assert "confirmation" in str(error).lower()
    else:
        raise AssertionError("rollback executed without confirmation")

    monkeypatch.setenv("ROLLBACK_CONFIRMATION", rollback.CONFIRMATION)
    calls = []

    def fake_request(path, token, payload=None):
        calls.append((path, token, payload))
        if payload is None:
            return {"deployment": {"id": TARGET_ID, "phase": "ACTIVE"}}
        return {"deployment": {"id": "33333333-3333-4333-8333-333333333333"}}

    monkeypatch.setattr(rollback, "api_request", fake_request)
    result = rollback.run("execute", INPUT_PATH)
    assert result["event"] == "rollback.initiated"
    assert calls[-1] == (
        f"{APP_ID}/rollback",
        "private-operator-token",
        {"deployment_id": TARGET_ID},
    )


def test_failure_output_redacts_provider_and_token_details(monkeypatch, capsys) -> None:
    configure(monkeypatch)
    secret = "private-operator-token"
    monkeypatch.setattr(rollback, "run", lambda mode: (_ for _ in ()).throw(RuntimeError(secret)))
    monkeypatch.setattr("sys.argv", ["digitalocean_rollback.py", "--mode", "inspect"])
    assert rollback.main() == 1
    captured = capsys.readouterr()
    assert secret not in captured.err
    assert json.loads(captured.err) == {"event": "rollback.failed", "status": "fail"}
