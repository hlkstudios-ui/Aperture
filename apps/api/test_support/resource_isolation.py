from __future__ import annotations

import ipaddress
import json
import os
import re
import secrets
import socket
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import SplitResult, urlsplit, urlunsplit

from sqlalchemy.engine import URL, make_url

TEST_DATABASE_PREFIX = "aperture_pytest_"
TEST_BUCKET_PREFIX = "aperture-pytest-"
TEST_REDIS_DATABASE = 15
RESOURCE_OWNER_SCHEMA = "aperture.pytest.resource-owner.v1"

_DATABASE_NAME_PATTERN = re.compile(r"^aperture_pytest_[a-z0-9_]{8,45}$")
_BUCKET_NAME_PATTERN = re.compile(r"^aperture-pytest-[a-z0-9-]{8,44}$")
_ALLOWED_POSTGRES_DRIVERS = frozenset({"postgresql", "postgresql+psycopg"})
_ALLOWED_SOURCE_ENVIRONMENTS = frozenset({"development", "test"})


class UnsafeTestResourceError(RuntimeError):
    """Raised before a test can point at a persistent or remote resource."""


@dataclass(frozen=True, slots=True)
class TestResourcePlan:
    database_name: str
    database_url: str
    admin_database_url: str
    redis_url: str
    s3_bucket: str
    run_token: str


@dataclass(frozen=True, slots=True)
class ResourceOwner:
    """Durable provenance used before reclaiming an abandoned test resource."""

    resource_kind: str
    resource_name: str
    run_token: str
    hostname: str
    pid: int
    created_at: datetime

    def to_json(self) -> str:
        return json.dumps(
            {
                "schema": RESOURCE_OWNER_SCHEMA,
                "resource_kind": self.resource_kind,
                "resource_name": self.resource_name,
                "run_token": self.run_token,
                "hostname": self.hostname,
                "pid": self.pid,
                "created_at": self.created_at.astimezone(UTC).isoformat(),
            },
            separators=(",", ":"),
            sort_keys=True,
        )


def new_resource_owner(
    *,
    resource_kind: str,
    resource_name: str,
    run_token: str,
    now: datetime | None = None,
) -> ResourceOwner:
    return ResourceOwner(
        resource_kind=resource_kind,
        resource_name=resource_name,
        run_token=run_token,
        hostname=socket.gethostname().casefold(),
        pid=os.getpid(),
        created_at=(now or datetime.now(UTC)).astimezone(UTC),
    )


def parse_resource_owner(
    payload: bytes | str,
    *,
    resource_kind: str,
    resource_name: str,
) -> ResourceOwner:
    """Parse only the exact owner schema expected for a specific resource."""

    try:
        raw = payload.decode("utf-8") if isinstance(payload, bytes) else payload
        value = json.loads(raw)
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "resource_kind",
            "resource_name",
            "run_token",
            "hostname",
            "pid",
            "created_at",
        }:
            raise ValueError
        if value["schema"] != RESOURCE_OWNER_SCHEMA:
            raise ValueError
        if value["resource_kind"] != resource_kind or value["resource_name"] != resource_name:
            raise ValueError
        run_token = value["run_token"]
        hostname = value["hostname"]
        pid = value["pid"]
        if not isinstance(run_token, str) or not re.fullmatch(r"[a-z0-9]{8,32}", run_token):
            raise ValueError
        if not isinstance(hostname, str) or not hostname or hostname != hostname.casefold():
            raise ValueError
        if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
            raise ValueError
        created_at = datetime.fromisoformat(value["created_at"])
        if created_at.tzinfo is None:
            raise ValueError
    except (AttributeError, TypeError, UnicodeDecodeError, ValueError) as exc:
        raise UnsafeTestResourceError(
            f"Resource {resource_kind}/{resource_name} has invalid ownership metadata"
        ) from exc
    return ResourceOwner(
        resource_kind=resource_kind,
        resource_name=resource_name,
        run_token=run_token,
        hostname=hostname,
        pid=pid,
        created_at=created_at.astimezone(UTC),
    )


def is_proven_dead_local_owner(
    owner: ResourceOwner,
    *,
    hostname: str | None = None,
    process_is_alive: Callable[[int], bool] | None = None,
) -> bool:
    """Return true only when the owner host is this host and its PID is absent."""

    local_host = (hostname or socket.gethostname()).casefold()
    checker = process_is_alive or _process_is_alive
    return owner.hostname == local_host and not checker(owner.pid)


def is_reapable_owner(
    owner: ResourceOwner,
    *,
    minimum_age_seconds: int,
    now: datetime | None = None,
    hostname: str | None = None,
    process_is_alive: Callable[[int], bool] | None = None,
) -> bool:
    if minimum_age_seconds < 0:
        raise ValueError("minimum_age_seconds must not be negative")
    current_time = (now or datetime.now(UTC)).astimezone(UTC)
    age_seconds = (current_time - owner.created_at).total_seconds()
    return age_seconds >= minimum_age_seconds and is_proven_dead_local_owner(
        owner,
        hostname=hostname,
        process_is_alive=process_is_alive,
    )


def new_run_token() -> str:
    """Return a short process-specific token valid in database and bucket names."""

    return f"{os.getpid():x}{secrets.token_hex(6)}"


def build_test_resource_plan(
    *,
    app_env: str,
    database_url: str,
    redis_url: str,
    s3_endpoint: str,
    run_token: str | None = None,
) -> TestResourcePlan:
    """Validate source services and derive resources that are safe to destroy.

    The configured resources are used only as local service endpoints. Tests always
    receive a newly created database, Redis database 15, and a uniquely named bucket.
    """

    normalized_env = app_env.strip().lower()
    if normalized_env not in _ALLOWED_SOURCE_ENVIRONMENTS:
        raise UnsafeTestResourceError(
            "API tests may use resources only from APP_ENV=development or APP_ENV=test"
        )

    source_database = _validated_postgres_url(database_url)
    isolated_redis_url = _isolated_redis_url(redis_url)
    _validate_loopback_endpoint(s3_endpoint, resource="S3")

    token = (run_token or new_run_token()).strip().lower()
    if not re.fullmatch(r"[a-z0-9]{8,32}", token):
        raise UnsafeTestResourceError(
            "The pytest run token must contain 8-32 lowercase letters or digits"
        )

    database_name = f"{TEST_DATABASE_PREFIX}{token}"
    bucket_name = f"{TEST_BUCKET_PREFIX}{token}"
    assert_disposable_database_name(database_name)
    assert_disposable_bucket_name(bucket_name)

    database = source_database.set(database=database_name)
    admin_database = source_database.set(database="postgres")
    return TestResourcePlan(
        database_name=database_name,
        database_url=_render_url(database),
        admin_database_url=_render_url(admin_database),
        redis_url=isolated_redis_url,
        s3_bucket=bucket_name,
        run_token=token,
    )


def assert_disposable_database_name(database_name: str) -> None:
    if not _DATABASE_NAME_PATTERN.fullmatch(database_name):
        raise UnsafeTestResourceError(
            f"Refusing destructive database operation for {database_name!r}; "
            f"expected a generated {TEST_DATABASE_PREFIX!r} name"
        )


def assert_disposable_bucket_name(bucket_name: str) -> None:
    if not _BUCKET_NAME_PATTERN.fullmatch(bucket_name):
        raise UnsafeTestResourceError(
            f"Refusing destructive bucket operation for {bucket_name!r}; "
            f"expected a generated {TEST_BUCKET_PREFIX!r} name"
        )


def assert_isolated_redis_url(redis_url: str) -> None:
    parsed = _validated_redis_url(redis_url)
    if parsed.path != f"/{TEST_REDIS_DATABASE}":
        raise UnsafeTestResourceError(
            f"Refusing destructive Redis operation outside database {TEST_REDIS_DATABASE}"
        )


def safe_url(url: str) -> str:
    """Render a SQLAlchemy URL without revealing a password in diagnostics."""

    try:
        return make_url(url).render_as_string(hide_password=True)
    except Exception:
        return "<invalid URL>"


def _validated_postgres_url(database_url: str) -> URL:
    try:
        parsed = make_url(database_url)
    except Exception as exc:
        raise UnsafeTestResourceError("DATABASE_URL is not a valid database URL") from exc
    if parsed.drivername not in _ALLOWED_POSTGRES_DRIVERS:
        raise UnsafeTestResourceError("API tests require PostgreSQL with the psycopg driver")
    _validate_loopback_host(parsed.host, resource="PostgreSQL")
    if not parsed.database:
        raise UnsafeTestResourceError("DATABASE_URL must name a source database")
    return parsed


def _isolated_redis_url(redis_url: str) -> str:
    parsed = _validated_redis_url(redis_url)
    isolated = SplitResult(
        scheme=parsed.scheme,
        netloc=parsed.netloc,
        path=f"/{TEST_REDIS_DATABASE}",
        query=parsed.query,
        fragment="",
    )
    result = urlunsplit(isolated)
    assert_isolated_redis_url(result)
    return result


def _validated_redis_url(redis_url: str) -> SplitResult:
    try:
        parsed = urlsplit(redis_url)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeTestResourceError("REDIS_URL is not a valid Redis URL") from exc
    if parsed.scheme not in {"redis", "rediss"}:
        raise UnsafeTestResourceError("REDIS_URL must use the redis or rediss scheme")
    _validate_loopback_host(parsed.hostname, resource="Redis")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeTestResourceError("REDIS_URL has an invalid port")
    if parsed.fragment:
        raise UnsafeTestResourceError("REDIS_URL must not contain a fragment")
    if parsed.path not in {"", "/"}:
        try:
            database = int(parsed.path.removeprefix("/"))
        except ValueError as exc:
            raise UnsafeTestResourceError("REDIS_URL must contain a numeric database") from exc
        if not 0 <= database <= 15:
            raise UnsafeTestResourceError("REDIS_URL database must be between 0 and 15")
    return parsed


def _validate_loopback_endpoint(endpoint: str, *, resource: str) -> None:
    try:
        parsed = urlsplit(endpoint)
        port = parsed.port
    except ValueError as exc:
        raise UnsafeTestResourceError(f"{resource} endpoint is not a valid URL") from exc
    if parsed.scheme not in {"http", "https"}:
        raise UnsafeTestResourceError(f"{resource} endpoint must use HTTP or HTTPS")
    _validate_loopback_host(parsed.hostname, resource=resource)
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise UnsafeTestResourceError(f"{resource} endpoint contains unsupported URL components")
    if parsed.path not in {"", "/"}:
        raise UnsafeTestResourceError(f"{resource} endpoint must not contain a path")
    if port is not None and not 1 <= port <= 65535:
        raise UnsafeTestResourceError(f"{resource} endpoint has an invalid port")


def _validate_loopback_host(host: str | None, *, resource: str) -> None:
    if not host:
        raise UnsafeTestResourceError(f"{resource} must have an explicit loopback host")
    normalized = host.rstrip(".").lower()
    if normalized == "localhost":
        return
    try:
        address = ipaddress.ip_address(normalized)
    except ValueError as exc:
        raise UnsafeTestResourceError(
            f"{resource} host must be localhost or a loopback IP address"
        ) from exc
    if not address.is_loopback:
        raise UnsafeTestResourceError(
            f"{resource} host must be localhost or a loopback IP address"
        )


def _process_is_alive(pid: int) -> bool:
    """Check a PID without signaling it; uncertainty is treated as alive."""

    if pid <= 0:
        return True
    if os.name == "nt":
        return _windows_process_is_alive(pid)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except (OSError, PermissionError):
        return True
    return True


def _windows_process_is_alive(pid: int) -> bool:
    # os.kill(pid, 0) is not a portable no-op on Windows, so query the handle.
    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    still_active = 259
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
    kernel32.CloseHandle.restype = wintypes.BOOL
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # ERROR_INVALID_PARAMETER proves that no such PID exists. Access denied and
        # every other result are deliberately treated as potentially live.
        return ctypes.get_last_error() != 87
    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return True
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _render_url(url: URL) -> str:
    return url.render_as_string(hide_password=False)
