from collections.abc import Callable

from fastapi import HTTPException, status

from app.config import get_settings


def require_feature(setting_name: str) -> Callable[[], None]:
    """Create a request dependency that hides a disabled optional capability."""

    def dependency() -> None:
        if not getattr(get_settings(), setting_name, False):
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Not found")

    return dependency


require_ask_movie = require_feature("feature_ask_movie_enabled")
require_watch_parties = require_feature("feature_watch_parties_enabled")
