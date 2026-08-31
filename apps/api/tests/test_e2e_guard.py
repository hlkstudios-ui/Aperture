from pathlib import Path
from types import SimpleNamespace

import pytest

from app.e2e_redis_fence import E2ERedisFenceError
from scripts import e2e_guard
from scripts.e2e_guard import (
    expected_bucket_name,
    expected_database_name,
    require_e2e_test_environment,
)

RUN_ID = "local-safety01"
OWNER_TOKEN = "a" * 64
SCRIPTS_DIRECTORY = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture(autouse=True)
def verified_redis_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("E2E_OWNER_TOKEN", OWNER_TOKEN)
    monkeypatch.setattr(e2e_guard, "verify_owner", lambda *_arguments: object())


def settings(
    *,
    app_env: str = "test",
    database_name: str | None = None,
    bucket_name: str | None = None,
    database_host: str = "127.0.0.1",
    redis_url: str = "redis://127.0.0.1:6380/14",
    s3_endpoint: str = "http://127.0.0.1:9100",
) -> SimpleNamespace:
    return SimpleNamespace(
        app_env=app_env,
        database_url=(
            f"postgresql+psycopg://aperture:secret@{database_host}:5433/"
            f"{database_name or expected_database_name(RUN_ID)}"
        ),
        redis_url=redis_url,
        s3_bucket=bucket_name or expected_bucket_name(RUN_ID),
        s3_endpoint=s3_endpoint,
    )


def test_e2e_guard_accepts_matching_test_resources(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    assert require_e2e_test_environment(settings()) == settings()


@pytest.mark.parametrize(
    "explicit_env,settings_env",
    [("development", "development"), ("test", "development")],
)
def test_e2e_guard_rejects_non_test_environment(
    monkeypatch: pytest.MonkeyPatch, explicit_env: str, settings_env: str
) -> None:
    monkeypatch.setenv("APP_ENV", explicit_env)
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="APP_ENV=test"):
        require_e2e_test_environment(settings(app_env=settings_env))


def test_e2e_guard_rejects_development_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="database"):
        require_e2e_test_environment(settings(database_name="anime_streaming_dev"))


def test_e2e_guard_rejects_development_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="bucket"):
        require_e2e_test_environment(settings(bucket_name="anime-streaming-development"))


@pytest.mark.parametrize(
    "overrides",
    [
        {"database_host": "database.example.com"},
        {"redis_url": "redis://cache.example.com:6379/14"},
        {"s3_endpoint": "https://objects.example.com"},
    ],
)
def test_e2e_guard_rejects_remote_mutable_services(
    monkeypatch: pytest.MonkeyPatch, overrides: dict[str, str]
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="loopback"):
        require_e2e_test_environment(settings(**overrides))


def test_e2e_guard_rejects_shared_redis_database(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="Redis database 14"):
        require_e2e_test_environment(settings(redis_url="redis://127.0.0.1:6380/0"))


def test_e2e_guard_rejects_redis_database_query_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    with pytest.raises(SystemExit, match="query or fragment"):
        require_e2e_test_environment(
            settings(redis_url="redis://127.0.0.1:6380/14?db=0")
        )


def test_e2e_guard_rejects_missing_run_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("E2E_RUN_ID", raising=False)

    with pytest.raises(SystemExit, match="E2E_RUN_ID"):
        require_e2e_test_environment(settings())


def test_e2e_guard_requires_the_matching_redis_owner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)

    def refuse_owner(*_arguments: object) -> None:
        raise E2ERedisFenceError("different owner")

    monkeypatch.setattr(e2e_guard, "verify_owner", refuse_owner)

    with pytest.raises(SystemExit, match="ownership was not verified: different owner"):
        require_e2e_test_environment(settings())


def test_every_stateful_e2e_helper_uses_the_shared_fail_closed_guard() -> None:
    unguarded: list[str] = []
    development_allowed: list[str] = []
    for script in SCRIPTS_DIRECTORY.glob("e2e_*.py"):
        source = script.read_text(encoding="utf-8")
        if "SessionLocal" in source and "require_e2e_test_environment()" not in source:
            unguarded.append(script.name)
        if '"development", "test"' in source:
            development_allowed.append(script.name)

    assert unguarded == []
    assert development_allowed == []
