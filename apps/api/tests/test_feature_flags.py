from types import SimpleNamespace

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import app.feature_flags as feature_flags
from app.config import Settings


def test_feature_flag_environment_names_are_typed() -> None:
    settings = Settings(
        _env_file=None,
        feature_scene_lens_enabled="false",
        feature_ask_movie_enabled="0",
        feature_community_enabled="no",
        feature_watch_parties_enabled="off",
        feature_experimental_recommendations_enabled="false",
    )
    assert not settings.feature_scene_lens_enabled
    assert not settings.feature_ask_movie_enabled
    assert not settings.feature_community_enabled
    assert not settings.feature_watch_parties_enabled
    assert not settings.feature_experimental_recommendations_enabled


def test_disabled_feature_fails_closed_without_leaking_capability(
    monkeypatch,
) -> None:
    app = FastAPI()
    dependency = feature_flags.require_feature("feature_test_enabled")

    @app.get("/optional", dependencies=[Depends(dependency)])
    def optional() -> dict[str, bool]:
        return {"enabled": True}

    monkeypatch.setattr(
        feature_flags,
        "get_settings",
        lambda: SimpleNamespace(feature_test_enabled=False),
    )
    response = TestClient(app).get("/optional")
    assert response.status_code == 404
    assert response.json() == {"detail": "Not found"}

    monkeypatch.setattr(
        feature_flags,
        "get_settings",
        lambda: SimpleNamespace(feature_test_enabled=True),
    )
    assert TestClient(app).get("/optional").json() == {"enabled": True}
