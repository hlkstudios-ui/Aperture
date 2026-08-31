"""Fail-closed resource guard shared by local browser-test helpers."""

import ipaddress
import os
import re
import sys
from pathlib import Path
from urllib.parse import urlsplit

from sqlalchemy.engine import make_url

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.config import Settings, get_settings  # noqa: E402
from app.e2e_redis_fence import E2ERedisFenceError, verify_owner  # noqa: E402

E2E_RUN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{6,38}[a-z0-9]$")
E2E_REDIS_DATABASE = 14


def expected_database_name(run_id: str) -> str:
    return f"aperture_e2e_{run_id.replace('-', '_')}"


def expected_bucket_name(run_id: str) -> str:
    return f"aperture-e2e-{run_id}"


def _require_loopback_host(host: str | None, resource: str) -> None:
    if not host:
        raise SystemExit(f"E2E {resource} requires an explicit loopback host")
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        raise SystemExit(f"E2E {resource} must use a loopback host") from None
    if not address.is_loopback:
        raise SystemExit(f"E2E {resource} must use a loopback host")


def require_e2e_test_environment(
    settings: Settings | None = None, *, verify_redis_ownership: bool = True
) -> Settings:
    """Return settings only when every mutable resource is explicitly E2E-isolated."""

    if os.environ.get("APP_ENV") != "test":
        raise SystemExit("E2E helpers require an explicit APP_ENV=test process")

    run_id = os.environ.get("E2E_RUN_ID", "")
    if not E2E_RUN_ID_PATTERN.fullmatch(run_id):
        raise SystemExit(
            "E2E helpers require E2E_RUN_ID with 8-40 lowercase letters, digits, or hyphens"
        )

    resolved = settings or get_settings()
    if resolved.app_env != "test":
        raise SystemExit("E2E helpers require settings resolved with APP_ENV=test")

    database_url = make_url(resolved.database_url)
    if database_url.drivername not in {"postgresql", "postgresql+psycopg"}:
        raise SystemExit("E2E helpers require an isolated PostgreSQL database")
    _require_loopback_host(database_url.host, "PostgreSQL")
    if database_url.database != expected_database_name(run_id):
        raise SystemExit(
            "E2E helper database does not match the isolated E2E_RUN_ID namespace"
        )
    if resolved.s3_bucket != expected_bucket_name(run_id):
        raise SystemExit(
            "E2E helper object-storage bucket does not match the isolated E2E_RUN_ID namespace"
        )

    s3_endpoint = urlsplit(str(resolved.s3_endpoint))
    if s3_endpoint.scheme not in {"http", "https"} or s3_endpoint.path not in {"", "/"}:
        raise SystemExit("E2E object storage requires an HTTP(S) origin without a path")
    _require_loopback_host(s3_endpoint.hostname, "object storage")
    redis_url = urlsplit(resolved.redis_url)
    if redis_url.scheme not in {"redis", "rediss"}:
        raise SystemExit("E2E helpers require a Redis URL")
    if redis_url.query or redis_url.fragment:
        raise SystemExit(
            "E2E Redis URL cannot contain a query or fragment that overrides database 14"
        )
    _require_loopback_host(redis_url.hostname, "Redis")
    if redis_url.path != f"/{E2E_REDIS_DATABASE}":
        raise SystemExit(f"E2E helpers require isolated Redis database {E2E_REDIS_DATABASE}")
    if verify_redis_ownership:
        try:
            verify_owner(
                resolved.redis_url,
                run_id,
                os.environ.get("E2E_OWNER_TOKEN", ""),
            )
        except E2ERedisFenceError as exc:
            raise SystemExit(f"E2E Redis ownership was not verified: {exc}") from exc
    return resolved
