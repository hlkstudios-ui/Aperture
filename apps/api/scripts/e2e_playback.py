"""Restricted profile-progress inspection for local playback acceptance tests."""

import json
import sys

from sqlalchemy import func, select

from app.catalog_models import Movie
from app.config import get_settings
from app.db import SessionLocal
from app.models import AnalyticsEvent, PlaybackSource, Profile, User, WatchProgress


def main() -> None:
    payload = json.load(sys.stdin)
    slug = payload["slug"]
    if get_settings().app_env not in {"development", "test"} or not slug.startswith(
        "e2e-studio-draft-playback-"
    ):
        raise SystemExit("E2E playback helper is restricted to development fixtures")
    with SessionLocal() as db:
        progress = db.execute(
            select(WatchProgress, Profile, PlaybackSource)
            .join(Profile, WatchProgress.profile_id == Profile.id)
            .join(User, Profile.user_id == User.id)
            .join(PlaybackSource, WatchProgress.playback_source_id == PlaybackSource.id)
            .join(Movie, PlaybackSource.movie_id == Movie.id)
            .where(User.email == payload["email"].lower(), Movie.slug == slug)
        ).first()
        analytics = db.execute(
            select(AnalyticsEvent.event_type, func.count(AnalyticsEvent.id))
            .join(Profile, AnalyticsEvent.profile_id == Profile.id)
            .join(User, Profile.user_id == User.id)
            .where(
                User.email == payload["email"].lower(),
                AnalyticsEvent.movie_id == db.scalar(select(Movie.id).where(Movie.slug == slug)),
            )
            .group_by(AnalyticsEvent.event_type)
        ).all()
        print(
            json.dumps(
                None
                if progress is None
                else {
                    "position_seconds": progress.WatchProgress.position_seconds,
                    "duration_seconds": progress.WatchProgress.duration_seconds,
                    "percentage": progress.WatchProgress.percentage,
                    "completed": progress.WatchProgress.completed,
                    "profile_name": progress.Profile.name,
                    "analytics": {event_type.value: count for event_type, count in analytics},
                }
            )
        )


if __name__ == "__main__":
    main()
