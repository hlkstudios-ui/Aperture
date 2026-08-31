import hashlib
from types import SimpleNamespace
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db import engine
from app.e2e_redis_fence import E2ERedisFenceError
from app.main import app
from app.routes import e2e_runtime

RUN_ID = "identity-safety01"
OWNER_TOKEN = "a" * 64
OWNER_TOKEN_HASH = hashlib.sha256(OWNER_TOKEN.encode()).hexdigest()


@pytest.fixture(autouse=True)
def redis_owner(monkeypatch: pytest.MonkeyPatch) -> None:
    def verify(_redis_url: str, _run_id: str, token: str) -> SimpleNamespace:
        if token != OWNER_TOKEN:
            raise E2ERedisFenceError("different owner")
        return SimpleNamespace(token_sha256=OWNER_TOKEN_HASH)

    monkeypatch.setattr(e2e_runtime, "verify_owner", verify)


def test_runtime_identity_has_a_second_non_test_environment_guard(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)
    monkeypatch.setattr(
        e2e_runtime,
        "get_settings",
        lambda: SimpleNamespace(app_env="production"),
    )

    response = TestClient(app).get(
        "/__test__/runtime-identity",
        headers={
            "X-Aperture-E2E-Owner": OWNER_TOKEN,
            "X-Aperture-E2E-Run": RUN_ID,
        },
    )

    assert response.status_code == 404


def test_runtime_identity_requires_the_matching_run_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)
    client = TestClient(app)

    assert client.get("/__test__/runtime-identity").status_code == 404
    assert (
        client.get(
            "/__test__/runtime-identity",
            headers={"X-Aperture-E2E-Run": RUN_ID},
        ).status_code
        == 404
    )
    assert (
        client.get(
            "/__test__/runtime-identity",
            headers={
                "X-Aperture-E2E-Owner": OWNER_TOKEN,
                "X-Aperture-E2E-Run": "different-run01",
            },
        ).status_code
        == 404
    )
    assert "/__test__/runtime-identity" not in client.get("/openapi.json").json()["paths"]


def test_runtime_identity_reports_the_resources_bound_to_the_running_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("E2E_RUN_ID", RUN_ID)
    response = TestClient(app).get(
        "/__test__/runtime-identity",
        headers={
            "X-Aperture-E2E-Owner": OWNER_TOKEN,
            "X-Aperture-E2E-Run": RUN_ID,
        },
    )

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.json() == {
        "environment": "test",
        "run_id": RUN_ID,
        "database_name": engine.url.database,
        "s3_bucket": get_settings().s3_bucket,
        "redis_database": int(urlsplit(get_settings().redis_url).path.removeprefix("/")),
        "redis_owner_token_sha256": OWNER_TOKEN_HASH,
        "api_origin": str(get_settings().api_origin).rstrip("/"),
    }
