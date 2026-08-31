#!/usr/bin/env python3
"""Snapshot and restore homepage state for isolated browser acceptance."""

import json
import sys
import uuid
from datetime import datetime
from pathlib import Path

from sqlalchemy import delete

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from e2e_guard import require_e2e_test_environment  # noqa: E402

from app.db import SessionLocal  # noqa: E402
from app.homepage_service import get_configuration  # noqa: E402
from app.models import HomepageRail  # noqa: E402


def main() -> None:
    require_e2e_test_environment()
    command = json.load(sys.stdin)
    with SessionLocal() as db:
        config = get_configuration(db)
        if command["action"] == "snapshot":
            print(
                json.dumps(
                    {
                        "hero_movie_id": str(config.draft_hero_movie_id)
                        if config.draft_hero_movie_id
                        else None,
                        "hero_series_id": str(config.draft_hero_series_id)
                        if config.draft_hero_series_id
                        else None,
                        "published_snapshot": config.published_snapshot,
                        "published_at": config.published_at.isoformat()
                        if config.published_at
                        else None,
                        "rail_ids": [str(rail.id) for rail in config.rails],
                    }
                )
            )
            return
        if command["action"] == "restore":
            keep = [uuid.UUID(value) for value in command["snapshot"]["rail_ids"]]
            statement = delete(HomepageRail)
            if keep:
                statement = statement.where(HomepageRail.id.not_in(keep))
            db.execute(statement)
            snapshot = command["snapshot"]
            config.draft_hero_movie_id = (
                uuid.UUID(snapshot["hero_movie_id"]) if snapshot["hero_movie_id"] else None
            )
            config.draft_hero_series_id = (
                uuid.UUID(snapshot["hero_series_id"]) if snapshot["hero_series_id"] else None
            )
            config.published_snapshot = snapshot["published_snapshot"]
            config.published_at = (
                datetime.fromisoformat(snapshot["published_at"])
                if snapshot["published_at"]
                else None
            )
            db.commit()
            print(json.dumps({"restored": True}))
            return
        raise ValueError("Unknown action")


if __name__ == "__main__":
    main()
