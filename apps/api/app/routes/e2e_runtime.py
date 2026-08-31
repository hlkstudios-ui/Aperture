"""Test-only runtime identity handshake for isolated browser acceptance."""

import os
import re
import secrets
from urllib.parse import urlsplit

from fastapi import APIRouter, Header, HTTPException, Response
from sqlalchemy import text

from app.config import get_settings
from app.db import engine
from app.e2e_redis_fence import E2ERedisFenceError, verify_owner

router = APIRouter(prefix="/__test__", tags=["test-runtime"])
RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{6,38}[a-z0-9]$")


def redis_database(redis_url: str) -> int:
    path = urlsplit(redis_url).path.removeprefix("/")
    if not path.isdigit():
        raise HTTPException(status_code=503, detail="Test runtime identity is unavailable")
    return int(path)


@router.get("/runtime-identity", include_in_schema=False)
def runtime_identity(
    response: Response,
    supplied_run_id: str | None = Header(default=None, alias="X-Aperture-E2E-Run"),
    supplied_owner_token: str | None = Header(
        default=None, alias="X-Aperture-E2E-Owner"
    ),
) -> dict[str, str | int]:
    settings = get_settings()
    run_id = os.environ.get("E2E_RUN_ID", "").strip()
    if (
        settings.app_env != "test"
        or not RUN_ID_PATTERN.fullmatch(run_id)
        or supplied_run_id is None
        or not secrets.compare_digest(supplied_run_id, run_id)
        or supplied_owner_token is None
    ):
        raise HTTPException(status_code=404, detail="Not found")

    try:
        redis_owner = verify_owner(settings.redis_url, run_id, supplied_owner_token)
    except E2ERedisFenceError as exc:
        raise HTTPException(status_code=404, detail="Not found") from exc

    with engine.connect() as connection:
        database_name = connection.scalar(text("SELECT current_database()"))
    if not isinstance(database_name, str) or database_name != engine.url.database:
        raise HTTPException(status_code=503, detail="Test runtime identity is unavailable")

    response.headers["Cache-Control"] = "no-store, max-age=0"
    return {
        "environment": settings.app_env,
        "run_id": run_id,
        "database_name": database_name,
        "s3_bucket": settings.s3_bucket,
        "redis_database": redis_database(settings.redis_url),
        "redis_owner_token_sha256": redis_owner.token_sha256,
        "api_origin": str(settings.api_origin).rstrip("/"),
    }
