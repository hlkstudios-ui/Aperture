#!/usr/bin/python3
"""Fail-closed, unattended forward deployment for the Hostinger production VPS.

This controller is deliberately narrower than the manual launch and rollback
procedures.  It accepts an immutable application release only after a production
baseline already exists.  Stateful or platform changes remain manual operations.

The command never prints command output, dotenv content, or image references.
"""

from __future__ import annotations

import argparse
from contextlib import AbstractContextManager, nullcontext
from dataclasses import dataclass
from datetime import datetime, timezone
import errno
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from typing import Callable
import zlib

try:  # The deploy command is Linux-only; the fallback keeps unit tests importable.
    import fcntl
except ImportError:  # pragma: no cover - exercised only outside Linux
    fcntl = None


ARTIFACTS = (
    "api",
    "media_worker",
    "web",
    "backup",
    "caddy",
    "storage",
    "node_exporter",
    "blackbox",
)
TAG_NAMES = {
    "api": "api",
    "media_worker": "media-worker",
    "web": "web",
    "backup": "backup",
    "caddy": "caddy",
    "storage": "storage",
    "node_exporter": "node-exporter",
    "blackbox": "blackbox",
}
IMAGE_LABELS = {
    "api": "API_IMAGE",
    "media_worker": "MEDIA_WORKER_IMAGE",
    "web": "WEB_IMAGE",
    "backup": "BACKUP_IMAGE",
    "caddy": "CADDY_IMAGE",
    "storage": "STORAGE_IMAGE",
    "node_exporter": "NODE_EXPORTER_IMAGE",
    "blackbox": "BLACKBOX_IMAGE",
}
RUNTIME_BINDINGS = {
    "api": "api",
    "media_worker": "media_worker",
    "scene_worker": "api",
    "web": "web",
    "backup": "backup",
    "caddy": "caddy",
    "storage": "storage",
    "node_exporter": "node_exporter",
    "blackbox": "blackbox",
}
UNATTENDED_INFRA = ("caddy", "storage", "node_exporter", "blackbox")
APPLICATION_ARTIFACTS = ("api", "media_worker", "web", "backup")
EXPECTED_REPOSITORY = "ghcr.io/hlkstudios-ui/aperture"

SOURCE_MARKER = ".aperture-source-sha"
HOSTINGER = "deploy/production/hostinger"
PRIVATE_STUDIO = "deploy/production/private-studio"
PUBLIC_EDGE_SMOKE = "deploy/production/public_edge_smoke.py"

# The bundle is a deployment package, not an arbitrary repository archive.  An
# explicit list prevents a privileged extractor from acquiring new behavior just
# because a future commit adds a file under deploy/production.
SUPPORT_FILES = frozenset(
    {
        f"{HOSTINGER}/prepare_vps_env.py",
        f"{HOSTINGER}/read_env.py",
        f"{HOSTINGER}/record_operation.py",
        f"{HOSTINGER}/render_monitoring.py",
        f"{HOSTINGER}/operations.sh",
        f"{HOSTINGER}/validate_caddy_coupling.py",
        f"{HOSTINGER}/validate_config.py",
        f"{HOSTINGER}/validate_host_hardening.py",
        f"{HOSTINGER}/validate_replication.py",
        f"{HOSTINGER}/validate_restore.py",
        f"{HOSTINGER}/validate_topology.py",
        PUBLIC_EDGE_SMOKE,
    }
)
PLATFORM_FILES = frozenset(
    {
        f"{HOSTINGER}/backup.Dockerfile",
        f"{HOSTINGER}/blackbox-exporter.Dockerfile",
        f"{HOSTINGER}/blackbox.yml",
        f"{HOSTINGER}/caddy.Dockerfile",
        f"{HOSTINGER}/Caddyfile",
        f"{HOSTINGER}/compose.yml",
        f"{HOSTINGER}/node-exporter.Dockerfile",
        f"{HOSTINGER}/prometheus.template.yml",
        f"{HOSTINGER}/storage.Dockerfile",
        f"{HOSTINGER}/storage_healthcheck.go",
        f"{PRIVATE_STUDIO}/Caddyfile",
        f"{PRIVATE_STUDIO}/compose.yml",
        "ops/prometheus-alerts.yml",
    }
)
BASELINE_LOCKED_FILES = SUPPORT_FILES | PLATFORM_FILES
REQUIRED_BUNDLE_FILES = SUPPORT_FILES | PLATFORM_FILES | {SOURCE_MARKER}
EXECUTABLE_BUNDLE_FILES = frozenset({f"{HOSTINGER}/operations.sh"})

# Forward-only database migrations make the predecessor's `migrate` image
# unsafe to execute after a later rollout check fails. Recovery therefore
# restores the predecessor runtime in explicit no-dependency phases and leaves
# `migrate` out of every command. Keep this exact contract synchronized with
# the baseline-locked production Compose file.
RECOVERY_STATEFUL_SERVICES = (
    "postgres",
    "redis",
    "minio",
    "clamav",
    "node-exporter",
    "blackbox",
)
RECOVERY_INITIALIZER_SERVICES = ("minio-init",)
RECOVERY_APPLICATION_SERVICES = (
    "api",
    "media-worker",
    "scene-worker",
    "web",
)
RECOVERY_EDGE_SERVICES = ("caddy", "prometheus")
RECOVERY_FORBIDDEN_SERVICES = frozenset({"migrate"})
EXPECTED_DEFAULT_SERVICES = frozenset(
    {
        *RECOVERY_STATEFUL_SERVICES,
        *RECOVERY_INITIALIZER_SERVICES,
        *RECOVERY_APPLICATION_SERVICES,
        *RECOVERY_EDGE_SERVICES,
        *RECOVERY_FORBIDDEN_SERVICES,
    }
)
EXPECTED_OPERATION_SERVICES = frozenset(
    {"maintenance", "preflight", "backup", "restore", "replicate-media"}
)
EXPECTED_PUBLIC_SERVICE_DEPENDENCIES = {
    "postgres": frozenset(),
    "redis": frozenset(),
    "minio": frozenset(),
    "minio-init": frozenset({"minio"}),
    "clamav": frozenset(),
    "migrate": frozenset({"postgres"}),
    "api": frozenset({"migrate", "minio-init", "redis", "clamav"}),
    "media-worker": frozenset({"migrate", "minio-init", "redis", "clamav"}),
    "scene-worker": frozenset({"migrate", "minio-init", "redis", "clamav"}),
    "web": frozenset({"api"}),
    "caddy": frozenset({"web", "minio-init"}),
    "maintenance": frozenset({"postgres", "redis"}),
    "preflight": frozenset({"postgres", "redis", "minio-init", "clamav"}),
    "backup": frozenset({"postgres"}),
    "restore": frozenset(),
    "replicate-media": frozenset({"minio"}),
    "node-exporter": frozenset(),
    "prometheus": frozenset({"api", "node-exporter", "blackbox"}),
    "blackbox": frozenset(),
}
EXPECTED_PUBLIC_SERVICE_IMAGES = {
    "api": "api",
    "media-worker": "media_worker",
    "scene-worker": "api",
    "migrate": "api",
    "maintenance": "api",
    "preflight": "api",
    "web": "web",
    "caddy": "caddy",
    "minio": "storage",
    "backup": "backup",
    "restore": "backup",
    "node-exporter": "node_exporter",
    "blackbox": "blackbox",
}
GENERATED_RUNTIME_FILES = (
    f"{HOSTINGER}/prometheus.local.yml",
    f"{HOSTINGER}/blackbox-targets.local.yml",
)

MANIFEST_KEYS = frozenset(
    {
        "schema_version",
        "release_id",
        "repository",
        "platform",
        "source_commit",
        "artifacts",
        "runtime_bindings",
        "registry_attestations",
    }
)
ARTIFACT_KEYS = frozenset({"tag", "digest", "reference"})
ATTESTATIONS = {
    "provenance": "buildx-mode-max",
    "sbom": "buildx-registry-referrer",
}
RELEASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REPOSITORY_PATTERN = re.compile(r"^[a-z0-9][a-z0-9./_-]*$")
SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
DIGEST_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
IMAGE_PATTERN = re.compile(
    r"^[a-z0-9.-]+(?::[0-9]+)?/[a-z0-9._/-]+"
    r"(?::[a-z0-9][a-z0-9._-]*)?@sha256:[0-9a-f]{64}$"
)
HOSTNAME_PATTERN = re.compile(
    r"^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z]{2,63}$"
)
CHECKSUM_LINE_PATTERN = re.compile(r"^([0-9a-f]{64})  ([A-Za-z0-9._-]+)$")
LAUNCH_MARKER_CONTENT = "APERTURE_PRODUCTION_LAUNCH_ENABLED\n"
MAX_ARCHIVE_FILES = 64
MAX_ARCHIVE_BYTES = 8 * 1024 * 1024
MAX_DECOMPRESSED_ARCHIVE_BYTES = MAX_ARCHIVE_BYTES + 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
MAX_RECORD_BYTES = 1024 * 1024
GC_AUDIT_RECORDS = 50
GC_STATUS_MIN_AGE_SECONDS = 7 * 24 * 60 * 60
GC_ABANDONED_MIN_AGE_SECONDS = 48 * 60 * 60
GC_MIN_FREE_BYTES = 2 * 1024 * 1024 * 1024
GC_MAX_INVENTORY_BYTES = 4 * 1024 * 1024
GC_MAX_INVENTORY_LINES = 10000
GC_IMAGE_REMOVE_BATCH = 100
MAX_ATTEMPT_RECORDS = 1000
CONTROLLER_PATH = Path("/usr/local/sbin/aperture-deploy-release")
SYSTEMD_RUN_PATH = Path("/usr/bin/systemd-run")
SYSTEMCTL_PATH = Path("/usr/bin/systemctl")
SYSTEMD_UNIT = "aperture-production-deploy"
JOB_BUNDLE_SUFFIX = ".source.tar.gz"
JOB_MANIFEST_SUFFIX = ".release.json"
JOB_CHECKSUM_SUFFIX = ".release.sha256"
TEMPORARY_JOB_PATTERN = re.compile(
    r"^\.job-(?P<release_id>[a-z0-9][a-z0-9._-]*)-(?P<pid>[0-9]+)$"
)
TEMPORARY_RELEASE_PATTERN = re.compile(
    r"^\.incoming-(?P<release_id>[a-z0-9][a-z0-9._-]*)-"
    r"(?P<suffix>[a-z0-9_]{8})$"
)
RELEASE_TOMBSTONE_PATTERN = re.compile(r"^\.gc-removed-(?P<original>.+)$")
ATTEMPT_PENDING_PATTERN = re.compile(
    r"^\.pending-(?P<release_id>[a-z0-9][a-z0-9._-]*)\.json$"
)
ACCEPTED_PENDING_PATTERN = re.compile(
    r"^\.pending-accepted-(?P<release_id>[a-z0-9][a-z0-9._-]*)\.json$"
)
ATOMIC_TEMP_SUFFIX_PATTERN = re.compile(r"^[a-z0-9_]{8}$")
TRANSACTION_METADATA = "transaction.json"
TRANSACTION_PUBLIC = "previous-production.env"
TRANSACTION_PRIVATE = "previous-private-studio.env"
TRANSACTION_METADATA_PENDING = ".deploy-transaction-metadata.pending"
LEGACY_TRANSACTION_PENDING_PATTERN = re.compile(r"^\.transaction\.json-[a-z0-9_]{8}$")
ACCEPTED_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "status",
        "release_id",
        "source_commit",
        "platform",
        "accepted_at",
        "previous_release",
        "digests",
        "effective_runtime_references",
        "database_schema_rollback",
    }
)
ATTEMPT_RECORD_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "release_id",
        "source_commit",
        "recorded_at",
        "application_references",
    }
)
STATUS_KEYS = frozenset(
    {
        "schema_version",
        "event",
        "release_id",
        "source_commit",
        "state",
        "stage",
        "recovery_status",
        "updated_at",
    }
)
TRANSACTION_KEYS = frozenset(
    {
        "schema_version",
        "state",
        "release_id",
        "source_commit",
        "previous_release",
        "previous_current_target",
    }
)


class DeployError(RuntimeError):
    """A safe, non-secret deployment failure."""

    def __init__(self, stage: str) -> None:
        super().__init__("production deployment failed")
        self.stage = stage


class LockUnavailable(DeployError):
    """Another deployment owns the production lock."""

    def __init__(self) -> None:
        super().__init__("lock")


class CommandFailure(DeployError):
    """An external command failed without retaining its output."""


class DeploymentExecutionError(DeployError):
    """A live mutation failed and compensation was attempted."""

    def __init__(
        self,
        stage: str,
        recovery_status: str,
        recovery_failure_stage: str | None = None,
    ) -> None:
        super().__init__(stage)
        self.recovery_status = recovery_status
        self.recovery_failure_stage = recovery_failure_stage


@dataclass(frozen=True)
class DeployPaths:
    launch_marker: Path
    public_runtime: Path
    private_runtime: Path
    incoming_root: Path
    releases_dir: Path
    current_link: Path
    history_dir: Path
    attempts_dir: Path
    lock_file: Path
    jobs_dir: Path
    status_dir: Path
    transaction_dir: Path

    @classmethod
    def production(cls) -> "DeployPaths":
        base = Path("/opt/aperture")
        return cls(
            launch_marker=Path("/etc/aperture/production-launch-enabled"),
            public_runtime=base / "shared/production.env",
            private_runtime=base / "shared/private-studio.env",
            incoming_root=Path("/var/lib/aperture-deploy/incoming"),
            releases_dir=base / "releases",
            current_link=base / "current",
            history_dir=base / "release-history",
            attempts_dir=base / "deploy-attempts",
            lock_file=base / "shared/production-deploy.lock",
            jobs_dir=base / "deploy-jobs",
            status_dir=base / "deploy-status",
            transaction_dir=base / "deploy-transaction",
        )


@dataclass(frozen=True)
class Release:
    release_id: str
    repository: str
    source_commit: str
    references: dict[str, str]
    digests: dict[str, str]


class CommandRunner:
    """Run a bounded command while suppressing all potentially sensitive output."""

    def run(
        self,
        stage: str,
        command: list[str],
        *,
        capture: bool = False,
        timeout: int = 900,
        environment: dict[str, str] | None = None,
    ) -> str:
        process_environment = os.environ.copy()
        if environment is not None:
            process_environment.update(environment)
        try:
            completed = subprocess.run(
                command,
                check=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                text=True,
                encoding="utf-8",
                timeout=timeout,
                env=process_environment,
            )
        except (OSError, subprocess.TimeoutExpired) as error:
            raise CommandFailure(stage) from error
        if completed.returncode != 0:
            raise CommandFailure(stage)
        return completed.stdout if capture else ""


class ProductionLock(AbstractContextManager["ProductionLock"]):
    """A nonblocking root-owned flock held for the controller's full lifetime."""

    def __init__(self, path: Path, expected_uid: int) -> None:
        self.path = path
        self.expected_uid = expected_uid
        self.descriptor = -1

    def __enter__(self) -> "ProductionLock":
        if fcntl is None:
            raise LockUnavailable()
        try:
            _secure_directory(
                self.path.parent,
                stage="lock",
                expected_uid=self.expected_uid,
            )
        except DeployError as error:
            raise LockUnavailable() from error
        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            self.descriptor = os.open(self.path, flags, 0o600)
            info = os.fstat(self.descriptor)
            if not stat.S_ISREG(info.st_mode) or info.st_uid != self.expected_uid:
                raise LockUnavailable()
            os.fchmod(self.descriptor, 0o600)
            if stat.S_IMODE(os.fstat(self.descriptor).st_mode) != 0o600:
                raise LockUnavailable()
            fcntl.flock(self.descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except LockUnavailable:
            self.__exit__(None, None, None)
            raise
        except (OSError, BlockingIOError) as error:
            self.__exit__(None, None, None)
            raise LockUnavailable() from error
        return self

    def __exit__(self, *_args: object) -> None:
        if self.descriptor >= 0:
            try:
                if fcntl is not None:
                    fcntl.flock(self.descriptor, fcntl.LOCK_UN)
            finally:
                os.close(self.descriptor)
                self.descriptor = -1


class RetryingProductionLock(AbstractContextManager["RetryingProductionLock"]):
    """Bounded wait for short-lived backup/maintenance lock contention."""

    def __init__(
        self,
        path: Path,
        expected_uid: int,
        *,
        timeout: float = 1800,
        interval: float = 5,
        clock: Callable[[], float] = time.monotonic,
        sleeper: Callable[[float], None] = time.sleep,
        attempt_factory: Callable[[], AbstractContextManager[object]] | None = None,
    ) -> None:
        self.path = path
        self.expected_uid = expected_uid
        self.timeout = timeout
        self.interval = interval
        self.clock = clock
        self.sleeper = sleeper
        self.attempt_factory = attempt_factory or (
            lambda: ProductionLock(path, expected_uid)
        )
        self.acquired: AbstractContextManager[object] | None = None

    def __enter__(self) -> "RetryingProductionLock":
        deadline = self.clock() + self.timeout
        while True:
            attempt = self.attempt_factory()
            try:
                attempt.__enter__()
                self.acquired = attempt
                return self
            except LockUnavailable:
                if self.clock() >= deadline:
                    raise
                self.sleeper(min(self.interval, max(0, deadline - self.clock())))

    def __exit__(self, *args: object) -> None:
        if self.acquired is not None:
            try:
                self.acquired.__exit__(*args)
            finally:
                self.acquired = None


def _effective_uid() -> int:
    getuid = getattr(os, "geteuid", None)
    return int(getuid()) if getuid is not None else -1


def _lstat(path: Path, *, stage: str) -> os.stat_result:
    try:
        return path.lstat()
    except OSError as error:
        raise DeployError(stage) from error


def _secure_directory(
    path: Path,
    *,
    stage: str,
    expected_uid: int | None,
) -> None:
    info = _lstat(path, stage=stage)
    if (
        path.is_symlink()
        or not stat.S_ISDIR(info.st_mode)
        or (expected_uid is not None and info.st_uid != expected_uid)
        or (os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o022)
    ):
        raise DeployError(stage)


def _secure_regular_file(
    path: Path,
    *,
    stage: str,
    expected_uid: int | None,
    sensitive: bool,
    maximum_bytes: int | None = None,
) -> None:
    info = _lstat(path, stage=stage)
    mode = stat.S_IMODE(info.st_mode)
    if (
        path.is_symlink()
        or not stat.S_ISREG(info.st_mode)
        or (expected_uid is not None and info.st_uid != expected_uid)
        or (os.name != "nt" and (mode != 0o600 if sensitive else bool(mode & 0o022)))
        or (maximum_bytes is not None and info.st_size > maximum_bytes)
    ):
        raise DeployError(stage)


def _fsync_directory(path: Path) -> None:
    if os.name == "nt":  # pragma: no cover - deployment is Linux-only
        return
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    descriptor = os.open(path, flags)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_write(path: Path, content: bytes, mode: int) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}-", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temporary, mode)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _cleanup_atomic_write_temps(
    directory: Path,
    *,
    target_names: set[str],
    expected_uid: int,
    stage: str,
) -> int:
    _secure_directory(directory, stage=stage, expected_uid=expected_uid)
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise DeployError(stage) from error
    if len(entries) > 10000:
        raise DeployError(stage)
    pending: list[Path] = []
    for entry in entries:
        for target_name in target_names:
            prefix = f".{target_name}-"
            if entry.name.startswith(prefix) and ATOMIC_TEMP_SUFFIX_PATTERN.fullmatch(
                entry.name[len(prefix) :]
            ):
                _secure_regular_file(
                    entry,
                    stage=stage,
                    expected_uid=expected_uid,
                    sensitive=True,
                    maximum_bytes=MAX_RECORD_BYTES,
                )
                if _lstat(entry, stage=stage).st_nlink != 1:
                    raise DeployError(stage)
                pending.append(entry)
                break
    try:
        for entry in pending:
            entry.unlink()
        if pending:
            _fsync_directory(directory)
    except OSError as error:
        raise DeployError(stage) from error
    return len(pending)


def _exclusive_write(path: Path, content: bytes, mode: int) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, mode)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
            os.fchmod(handle.fileno(), mode)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    _fsync_directory(path.parent)


def _secure_read_bytes(
    path: Path,
    *,
    stage: str,
    expected_uid: int,
    sensitive: bool,
    maximum_bytes: int,
) -> bytes:
    """Read one already-authorized file without a path-swap window."""

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as error:
        raise DeployError(stage) from error
    try:
        info = os.fstat(descriptor)
        mode = stat.S_IMODE(info.st_mode)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != expected_uid
            or (
                os.name != "nt" and (mode != 0o600 if sensitive else bool(mode & 0o022))
            )
            or info.st_size > maximum_bytes
        ):
            raise DeployError(stage)
        with os.fdopen(descriptor, "rb") as handle:
            descriptor = -1
            content = handle.read(maximum_bytes + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if len(content) > maximum_bytes:
        raise DeployError(stage)
    return content


def _json_record(content: bytes, *, stage: str) -> object:
    def pairs(values: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in values:
            if key in result:
                raise DeployError(stage)
            result[key] = value
        return result

    try:
        return json.loads(content.decode("utf-8"), object_pairs_hook=pairs)
    except (UnicodeError, json.JSONDecodeError) as error:
        raise DeployError(stage) from error


def _json_without_duplicates(content: bytes) -> object:
    return _json_record(content, stage="manifest")


def validate_manifest(
    content: bytes,
    *,
    expected_source_sha: str,
    expected_release_id: str,
) -> Release:
    if not SOURCE_COMMIT_PATTERN.fullmatch(expected_source_sha):
        raise DeployError("expected_source")
    if (
        not RELEASE_ID_PATTERN.fullmatch(expected_release_id)
        or "latest" in expected_release_id
        or "dummy" in expected_release_id
    ):
        raise DeployError("expected_release")

    value = _json_without_duplicates(content)
    if not isinstance(value, dict) or set(value) != MANIFEST_KEYS:
        raise DeployError("manifest")
    if value.get("schema_version") != 1 or isinstance(
        value.get("schema_version"), bool
    ):
        raise DeployError("manifest")
    if value.get("release_id") != expected_release_id:
        raise DeployError("manifest")
    if value.get("source_commit") != expected_source_sha:
        raise DeployError("manifest")
    if value.get("platform") != "linux/amd64":
        raise DeployError("manifest")
    repository = value.get("repository")
    if repository != EXPECTED_REPOSITORY or not REPOSITORY_PATTERN.fullmatch(
        repository
    ):
        raise DeployError("manifest")
    if value.get("registry_attestations") != ATTESTATIONS:
        raise DeployError("manifest")

    artifacts = value.get("artifacts")
    if not isinstance(artifacts, dict) or set(artifacts) != set(ARTIFACTS):
        raise DeployError("manifest")
    references: dict[str, str] = {}
    digests: dict[str, str] = {}
    for component in ARTIFACTS:
        record = artifacts.get(component)
        if not isinstance(record, dict) or set(record) != ARTIFACT_KEYS:
            raise DeployError("manifest")
        tag = f"{repository}/{TAG_NAMES[component]}:{expected_release_id}"
        digest = record.get("digest")
        reference = record.get("reference")
        if (
            record.get("tag") != tag
            or not isinstance(digest, str)
            or not DIGEST_PATTERN.fullmatch(digest)
            or reference != f"{tag}@{digest}"
            or not IMAGE_PATTERN.fullmatch(reference)
            or reference.lower().find("dummy") >= 0
            or digest == "sha256:" + "0" * 64
        ):
            raise DeployError("manifest")
        references[component] = reference
        digests[component] = digest
    if len(set(digests.values())) != len(ARTIFACTS):
        raise DeployError("manifest")

    bindings = value.get("runtime_bindings")
    expected_bindings = {
        binding: references[component]
        for binding, component in RUNTIME_BINDINGS.items()
    }
    if bindings != expected_bindings:
        raise DeployError("manifest")
    return Release(
        release_id=expected_release_id,
        repository=repository,
        source_commit=expected_source_sha,
        references=references,
        digests=digests,
    )


def validate_checksum(
    manifest_path: Path,
    bundle_path: Path,
    checksum_path: Path,
    manifest_content: bytes,
    bundle_content: bytes,
) -> None:
    try:
        checksum_content = checksum_path.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise DeployError("checksum") from error
    if not checksum_content.endswith("\n"):
        raise DeployError("checksum")
    records: dict[str, str] = {}
    for line in checksum_content.splitlines():
        match = CHECKSUM_LINE_PATTERN.fullmatch(line)
        if match is None or match.group(2) in records:
            raise DeployError("checksum")
        records[match.group(2)] = match.group(1)
    expected = {
        manifest_path.name: hashlib.sha256(manifest_content).hexdigest(),
        bundle_path.name: hashlib.sha256(bundle_content).hexdigest(),
    }
    if len(expected) != 2 or records != expected:
        raise DeployError("checksum")


def _allowed_directories() -> frozenset[str]:
    values: set[str] = set()
    for filename in REQUIRED_BUNDLE_FILES:
        parent = PurePosixPath(filename).parent
        while parent != PurePosixPath("."):
            values.add(parent.as_posix())
            parent = parent.parent
    return frozenset(values)


ALLOWED_BUNDLE_DIRECTORIES = _allowed_directories()
MAX_ARCHIVE_HEADERS = len(REQUIRED_BUNDLE_FILES) + len(ALLOWED_BUNDLE_DIRECTORIES)


def _validated_archive_members(archive: tarfile.TarFile) -> list[tarfile.TarInfo]:
    files: list[tarfile.TarInfo] = []
    names: set[str] = set()
    folded: set[str] = set()
    total = 0
    header_count = 0
    while True:
        member = archive.next()
        if member is None:
            break
        header_count += 1
        if header_count > MAX_ARCHIVE_HEADERS:
            raise DeployError("bundle")
        name = member.name
        path = PurePosixPath(name)
        if (
            not name
            or "\\" in name
            or name.startswith("/")
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in path.parts)
            or name in names
            or name.casefold() in folded
        ):
            raise DeployError("bundle")
        names.add(name)
        folded.add(name.casefold())
        if member.isdir():
            if name.rstrip("/") not in ALLOWED_BUNDLE_DIRECTORIES:
                raise DeployError("bundle")
            continue
        if not member.isreg() or name not in REQUIRED_BUNDLE_FILES:
            raise DeployError("bundle")
        if member.size < 0:
            raise DeployError("bundle")
        total += member.size
        files.append(member)
    if (
        len(files) > MAX_ARCHIVE_FILES
        or total > MAX_ARCHIVE_BYTES
        or {member.name for member in files} != set(REQUIRED_BUNDLE_FILES)
    ):
        raise DeployError("bundle")
    return files


def _bounded_gzip_decompress(content: bytes) -> bytes:
    """Decode one exact gzip stream without allowing metadata expansion bombs."""

    decompressor = zlib.decompressobj(16 + zlib.MAX_WBITS)
    output = bytearray()
    try:
        for offset in range(0, len(content), 64 * 1024):
            chunk = content[offset : offset + 64 * 1024]
            remaining = MAX_DECOMPRESSED_ARCHIVE_BYTES + 1 - len(output)
            output.extend(decompressor.decompress(chunk, remaining))
            if (
                len(output) > MAX_DECOMPRESSED_ARCHIVE_BYTES
                or decompressor.unconsumed_tail
            ):
                raise DeployError("bundle")
        remaining = MAX_DECOMPRESSED_ARCHIVE_BYTES + 1 - len(output)
        output.extend(decompressor.flush(remaining))
    except zlib.error as error:
        raise DeployError("bundle") from error
    if (
        len(output) > MAX_DECOMPRESSED_ARCHIVE_BYTES
        or not decompressor.eof
        or decompressor.unused_data
        or decompressor.unconsumed_tail
    ):
        raise DeployError("bundle")
    return bytes(output)


def extract_bundle(
    bundle_content: bytes, destination: Path, expected_source_sha: str
) -> None:
    try:
        tar_content = _bounded_gzip_decompress(bundle_content)
        with tarfile.open(fileobj=io.BytesIO(tar_content), mode="r:") as archive:
            members = _validated_archive_members(archive)
            for member in members:
                target = destination.joinpath(*PurePosixPath(member.name).parts)
                final_mode = 0o755 if member.name in EXECUTABLE_BUNDLE_FILES else 0o644
                target.parent.mkdir(parents=True, exist_ok=True, mode=0o755)
                source = archive.extractfile(member)
                if source is None:
                    raise DeployError("bundle")
                flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
                flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
                descriptor = os.open(target, flags, 0o644)
                copied = 0
                try:
                    with os.fdopen(descriptor, "wb") as output:
                        descriptor = -1
                        while True:
                            chunk = source.read(1024 * 1024)
                            if not chunk:
                                break
                            copied += len(chunk)
                            if copied > member.size:
                                raise DeployError("bundle")
                            output.write(chunk)
                        output.flush()
                        os.fchmod(output.fileno(), final_mode)
                        os.fsync(output.fileno())
                finally:
                    if descriptor >= 0:
                        os.close(descriptor)
                if copied != member.size:
                    raise DeployError("bundle")
                if (
                    os.name != "nt"
                    and stat.S_IMODE(_lstat(target, stage="bundle").st_mode)
                    != final_mode
                ):
                    raise DeployError("bundle")
    except (OSError, tarfile.TarError) as error:
        raise DeployError("bundle") from error

    try:
        marker = (destination / SOURCE_MARKER).read_bytes()
    except OSError as error:
        raise DeployError("bundle_source") from error
    if marker not in {
        expected_source_sha.encode("ascii"),
        (expected_source_sha + "\n").encode("ascii"),
    }:
        raise DeployError("bundle_source")


def _dotenv_values(content: bytes, *, stage: str) -> dict[str, str]:
    try:
        text = content.decode("utf-8")
    except UnicodeError as error:
        raise DeployError(stage) from error
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise DeployError(stage)
        label, value = line.split("=", 1)
        if not label or label in values:
            raise DeployError(stage)
        values[label] = value
    return values


def _runtime_images(content: bytes, *, stage: str) -> dict[str, str]:
    values = _dotenv_values(content, stage=stage)
    images: dict[str, str] = {}
    for component, label in IMAGE_LABELS.items():
        value = values.get(label, "")
        if (
            not IMAGE_PATTERN.fullmatch(value)
            or "dummy" in value.lower()
            or value.endswith("0" * 64)
        ):
            raise DeployError(stage)
        images[component] = value
    digests = [value.rsplit("@", 1)[1] for value in images.values()]
    if len(set(digests)) != len(ARTIFACTS):
        raise DeployError(stage)
    return images


def _replace_assignments(
    content: bytes, replacements: dict[str, str], *, stage: str
) -> bytes:
    try:
        lines = content.decode("utf-8").splitlines(keepends=True)
    except UnicodeError as error:
        raise DeployError(stage) from error
    seen = {label: 0 for label in replacements}
    result: list[str] = []
    for line in lines:
        body = line.rstrip("\r\n")
        ending = line[len(body) :]
        label, separator, _value = body.partition("=")
        if separator and label in replacements:
            seen[label] += 1
            result.append(f"{label}={replacements[label]}{ending}")
        else:
            result.append(line)
    if any(count != 1 for count in seen.values()):
        raise DeployError(stage)
    return "".join(result).encode("utf-8")


def _digest(reference: str) -> str:
    return reference.rsplit("@", 1)[1]


def _canonical_local_image_reference(reference: str) -> str:
    named, digest = reference.rsplit("@", 1)
    last_slash = named.rfind("/")
    last_colon = named.rfind(":")
    repository = named[:last_colon] if last_colon > last_slash else named
    return f"{repository}@{digest}"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _accepted_record_path(paths: DeployPaths, release: Path) -> Path:
    return paths.history_dir / f"{release.name}.json"


def _validate_accepted_current(
    paths: DeployPaths,
    current_release: Path,
    public_runtime: bytes,
    private_runtime: bytes,
    expected_uid: int,
) -> dict[str, object]:
    """Require current, runtime state, and its root-owned acceptance record to agree."""

    if not RELEASE_ID_PATTERN.fullmatch(current_release.name):
        raise DeployError("accepted_record")
    current_snapshot = _secure_read_bytes(
        current_release / ".env",
        stage="runtime_snapshot",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    if current_snapshot != public_runtime:
        raise DeployError("runtime_snapshot")
    record_path = _accepted_record_path(paths, current_release)
    content = _secure_read_bytes(
        record_path,
        stage="accepted_record",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    value = _json_record(content, stage="accepted_record")
    if not isinstance(value, dict) or set(value) != ACCEPTED_RECORD_KEYS:
        raise DeployError("accepted_record")
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or value.get("status") != "accepted"
        or value.get("release_id") != current_release.name
        or value.get("platform") != "linux/amd64"
        or value.get("database_schema_rollback") != "not_attempted"
    ):
        raise DeployError("accepted_record")
    source_commit = value.get("source_commit")
    if (
        not isinstance(source_commit, str)
        or not SOURCE_COMMIT_PATTERN.fullmatch(source_commit)
        or source_commit != _release_source_sha(current_release, expected_uid)
    ):
        raise DeployError("accepted_record")
    accepted_at = value.get("accepted_at")
    try:
        accepted_time = datetime.fromisoformat(accepted_at)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise DeployError("accepted_record") from error
    if accepted_time.tzinfo is None:
        raise DeployError("accepted_record")
    previous_release = value.get("previous_release")
    if previous_release is not None and (
        not isinstance(previous_release, str)
        or not RELEASE_ID_PATTERN.fullmatch(previous_release)
    ):
        raise DeployError("accepted_record")

    references = value.get("effective_runtime_references")
    digests = value.get("digests")
    if (
        not isinstance(references, dict)
        or set(references) != set(ARTIFACTS)
        or not isinstance(digests, dict)
        or set(digests) != set(ARTIFACTS)
    ):
        raise DeployError("accepted_record")
    runtime_images = _runtime_images(public_runtime, stage="accepted_record")
    for component in ARTIFACTS:
        reference = references.get(component)
        digest = digests.get(component)
        if (
            not isinstance(reference, str)
            or not IMAGE_PATTERN.fullmatch(reference)
            or not reference.startswith(f"{EXPECTED_REPOSITORY}/")
            or runtime_images[component] != reference
            or not isinstance(digest, str)
            or digest != _digest(reference)
        ):
            raise DeployError("accepted_record")
    private_values = _dotenv_values(private_runtime, stage="accepted_record")
    if private_values.get("CADDY_IMAGE") != runtime_images["caddy"]:
        raise DeployError("accepted_record")
    return value


def _accepted_record(
    release: Release,
    *,
    effective_references: dict[str, str],
    previous_release: str,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "status": "accepted",
        "release_id": release.release_id,
        "source_commit": release.source_commit,
        "platform": "linux/amd64",
        "accepted_at": _utc_now(),
        "previous_release": previous_release,
        "digests": {
            component: _digest(effective_references[component])
            for component in ARTIFACTS
        },
        "effective_runtime_references": effective_references,
        "database_schema_rollback": "not_attempted",
    }


def _accepted_pending_path(paths: DeployPaths, release_id: str) -> Path:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise DeployError("history")
    return paths.history_dir / f".pending-accepted-{release_id}.json"


def _cleanup_accepted_pending(paths: DeployPaths, expected_uid: int) -> None:
    _secure_directory(paths.history_dir, stage="gc_history", expected_uid=expected_uid)
    try:
        pending_entries = [
            entry
            for entry in paths.history_dir.iterdir()
            if ACCEPTED_PENDING_PATTERN.fullmatch(entry.name)
        ]
    except OSError as error:
        raise DeployError("gc_history") from error
    if len(pending_entries) > 1:
        raise DeployError("gc_history")
    for pending in pending_entries:
        match = ACCEPTED_PENDING_PATTERN.fullmatch(pending.name)
        if match is None:  # pragma: no cover - guarded by the comprehension
            raise DeployError("gc_history")
        release_id = match.group("release_id")
        pending_info = _trusted_pending_file(
            pending, expected_uid=expected_uid, stage="gc_history"
        )
        final = paths.history_dir / f"{release_id}.json"
        if final.exists() or final.is_symlink():
            _read_accepted_record(paths, release_id, expected_uid)
            final_info = _trusted_pending_file(
                final, expected_uid=expected_uid, stage="gc_history"
            )
            if (
                not os.path.samestat(pending_info, final_info)
                or pending_info.st_nlink != 2
                or final_info.st_nlink != 2
            ):
                raise DeployError("gc_history")
        elif pending_info.st_nlink != 1:
            raise DeployError("gc_history")
        try:
            pending.unlink()
            _fsync_directory(paths.history_dir)
        except OSError as error:
            raise DeployError("gc_history") from error


def _publish_accepted_record(
    paths: DeployPaths,
    *,
    release_id: str,
    value: dict[str, object],
    expected_uid: int,
) -> None:
    pending = _accepted_pending_path(paths, release_id)
    final = paths.history_dir / f"{release_id}.json"
    if final.exists() or final.is_symlink() or pending.exists() or pending.is_symlink():
        raise DeployError("history")
    try:
        _write_pending_file(
            pending,
            (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        )
        os.link(pending, final, follow_symlinks=False)
        _fsync_directory(paths.history_dir)
        published = _read_accepted_record(paths, release_id, expected_uid)
        pending_info = _trusted_pending_file(
            pending, expected_uid=expected_uid, stage="history"
        )
        final_info = _trusted_pending_file(
            final, expected_uid=expected_uid, stage="history"
        )
        if (
            published != value
            or not os.path.samestat(pending_info, final_info)
            or pending_info.st_nlink != 2
            or final_info.st_nlink != 2
        ):
            raise DeployError("history")
        pending.unlink()
        _fsync_directory(paths.history_dir)
    except DeployError:
        raise
    except OSError as error:
        raise DeployError("history") from error


def _remove_interrupted_acceptance(
    paths: DeployPaths, release_id: str, expected_uid: int
) -> None:
    pending = _accepted_pending_path(paths, release_id)
    final = paths.history_dir / f"{release_id}.json"
    pending_info: os.stat_result | None = None
    final_info: os.stat_result | None = None
    if pending.exists() or pending.is_symlink():
        pending_info = _trusted_pending_file(
            pending, expected_uid=expected_uid, stage="history_cleanup"
        )
    if final.exists() or final.is_symlink():
        final_info = _trusted_pending_file(
            final, expected_uid=expected_uid, stage="history_cleanup"
        )
    if pending_info is not None and final_info is not None:
        if (
            not os.path.samestat(pending_info, final_info)
            or pending_info.st_nlink != 2
            or final_info.st_nlink != 2
        ):
            raise DeployError("history_cleanup")
    elif (pending_info is not None and pending_info.st_nlink != 1) or (
        final_info is not None and final_info.st_nlink != 1
    ):
        raise DeployError("history_cleanup")
    try:
        if pending_info is not None:
            pending.unlink()
        if final_info is not None:
            final.unlink()
        if pending_info is not None or final_info is not None:
            _fsync_directory(paths.history_dir)
    except OSError as error:
        raise DeployError("history_cleanup") from error


def _attempt_record_path(paths: DeployPaths, release_id: str) -> Path:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise DeployError("attempt_record")
    return paths.attempts_dir / f"{release_id}.json"


def _attempt_pending_path(paths: DeployPaths, release_id: str) -> Path:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise DeployError("attempt_record")
    return paths.attempts_dir / f".pending-{release_id}.json"


def _validate_attempt_record(
    value: object, *, expected_release_id: str, stage: str
) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != ATTEMPT_RECORD_KEYS:
        raise DeployError(stage)
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or value.get("event") != "release.attempt"
        or value.get("release_id") != expected_release_id
    ):
        raise DeployError(stage)
    source_commit = value.get("source_commit")
    if not isinstance(source_commit, str) or not SOURCE_COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        raise DeployError(stage)
    recorded_at = value.get("recorded_at")
    try:
        recorded_time = datetime.fromisoformat(recorded_at)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise DeployError(stage) from error
    if recorded_time.tzinfo is None:
        raise DeployError(stage)
    references = value.get("application_references")
    if not isinstance(references, dict) or set(references) != set(
        APPLICATION_ARTIFACTS
    ):
        raise DeployError(stage)
    for component in APPLICATION_ARTIFACTS:
        reference = references.get(component)
        if (
            not isinstance(reference, str)
            or not IMAGE_PATTERN.fullmatch(reference)
            or not reference.startswith(f"{EXPECTED_REPOSITORY}/")
        ):
            raise DeployError(stage)
    return value


def _read_attempt_record(
    paths: DeployPaths,
    release_id: str,
    expected_uid: int,
    *,
    stage: str = "gc_attempt",
) -> dict[str, object]:
    content = _secure_read_bytes(
        _attempt_record_path(paths, release_id),
        stage=stage,
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    return _validate_attempt_record(
        _json_record(content, stage=stage),
        expected_release_id=release_id,
        stage=stage,
    )


def _trusted_pending_file(
    path: Path, *, expected_uid: int, stage: str
) -> os.stat_result:
    _secure_regular_file(
        path,
        stage=stage,
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    return _lstat(path, stage=stage)


def _recover_attempt_pending(
    paths: DeployPaths,
    release_id: str,
    expected_uid: int,
    *,
    stage: str,
) -> None:
    pending = _attempt_pending_path(paths, release_id)
    pending_info = _trusted_pending_file(
        pending, expected_uid=expected_uid, stage=stage
    )
    final = _attempt_record_path(paths, release_id)
    if not final.exists() and not final.is_symlink():
        # Publication could not have returned, so no pull was authorized. A
        # partial or fully flushed pending inode is safe to discard and retry.
        if pending_info.st_nlink != 1:
            raise DeployError(stage)
        try:
            pending.unlink()
            _fsync_directory(paths.attempts_dir)
        except OSError as error:
            raise DeployError(stage) from error
        return
    final_value = _read_attempt_record(paths, release_id, expected_uid, stage=stage)
    final_info = _trusted_pending_file(final, expected_uid=expected_uid, stage=stage)
    if (
        not os.path.samestat(pending_info, final_info)
        or pending_info.st_nlink != 2
        or final_info.st_nlink != 2
        or final_value["release_id"] != release_id
    ):
        raise DeployError(stage)
    try:
        pending.unlink()
        _fsync_directory(paths.attempts_dir)
    except OSError as error:
        raise DeployError(stage) from error


def _attempt_directory_entries(
    paths: DeployPaths, expected_uid: int, *, stage: str
) -> tuple[dict[str, Path], dict[str, Path]]:
    _secure_directory(paths.attempts_dir, stage=stage, expected_uid=expected_uid)
    try:
        entries = tuple(paths.attempts_dir.iterdir())
    except OSError as error:
        raise DeployError(stage) from error
    if len(entries) > MAX_ATTEMPT_RECORDS + 1:
        raise DeployError("attempt_capacity")
    finals: dict[str, Path] = {}
    pending: dict[str, Path] = {}
    for entry in entries:
        pending_match = ATTEMPT_PENDING_PATTERN.fullmatch(entry.name)
        if pending_match is not None:
            release_id = pending_match.group("release_id")
            pending[release_id] = entry
            continue
        if entry.is_symlink() or entry.suffix != ".json":
            raise DeployError(stage)
        release_id = entry.stem
        if not RELEASE_ID_PATTERN.fullmatch(release_id):
            raise DeployError(stage)
        finals[release_id] = entry
    if len(pending) > 1 or len(finals) > MAX_ATTEMPT_RECORDS:
        raise DeployError("attempt_capacity")
    return finals, pending


def _scan_attempt_records(
    paths: DeployPaths, expected_uid: int, *, stage: str = "gc_attempt"
) -> dict[str, dict[str, object]]:
    _finals, pending = _attempt_directory_entries(paths, expected_uid, stage=stage)
    for release_id in pending:
        _recover_attempt_pending(
            paths,
            release_id,
            expected_uid,
            stage=stage,
        )
    finals, remaining_pending = _attempt_directory_entries(
        paths, expected_uid, stage=stage
    )
    if remaining_pending:
        raise DeployError(stage)
    records: dict[str, dict[str, object]] = {}
    for release_id in finals:
        records[release_id] = _read_attempt_record(
            paths, release_id, expected_uid, stage=stage
        )
    return records


def _write_pending_file(path: Path, content: bytes) -> None:
    flags = os.O_CREAT | os.O_EXCL | os.O_WRONLY
    flags |= getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.fchmod(descriptor, 0o600)
        remaining = memoryview(content)
        while remaining:
            written = os.write(descriptor, remaining)
            if written <= 0:
                raise OSError(errno.EIO, "attempt pending write made no progress")
            remaining = remaining[written:]
        os.fsync(descriptor)
        info = os.fstat(descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or (os.name != "nt" and stat.S_IMODE(info.st_mode) != 0o600)
            or info.st_nlink != 1
        ):
            raise OSError(errno.EPERM, "attempt pending inode is unsafe")
    finally:
        os.close(descriptor)


def _attempt_identity_matches(
    value: dict[str, object], *, source_commit: str, references: dict[str, str]
) -> bool:
    return (
        value["source_commit"] == source_commit
        and value["application_references"] == references
    )


def _publish_attempt_record(
    paths: DeployPaths,
    *,
    release_id: str,
    value: dict[str, object],
    expected_uid: int,
) -> None:
    pending = _attempt_pending_path(paths, release_id)
    final = _attempt_record_path(paths, release_id)
    content = (json.dumps(value, sort_keys=True) + "\n").encode()
    _write_pending_file(pending, content)
    try:
        try:
            os.link(pending, final, follow_symlinks=False)
        except FileExistsError:
            existing = _read_attempt_record(
                paths, release_id, expected_uid, stage="attempt_record"
            )
            if not _attempt_identity_matches(
                existing,
                source_commit=str(value["source_commit"]),
                references=value["application_references"],  # type: ignore[arg-type]
            ):
                raise DeployError("attempt_record")
            pending_info = _trusted_pending_file(
                pending, expected_uid=expected_uid, stage="attempt_record"
            )
            if pending_info.st_nlink != 1:
                raise DeployError("attempt_record")
            pending.unlink()
            _fsync_directory(paths.attempts_dir)
            return
        _fsync_directory(paths.attempts_dir)
        published = _read_attempt_record(
            paths, release_id, expected_uid, stage="attempt_record"
        )
        pending_info = _trusted_pending_file(
            pending, expected_uid=expected_uid, stage="attempt_record"
        )
        final_info = _trusted_pending_file(
            final, expected_uid=expected_uid, stage="attempt_record"
        )
        if (
            published != value
            or not os.path.samestat(pending_info, final_info)
            or pending_info.st_nlink != 2
            or final_info.st_nlink != 2
        ):
            raise DeployError("attempt_record")
        pending.unlink()
        _fsync_directory(paths.attempts_dir)
    except DeployError:
        raise
    except OSError as error:
        raise DeployError("attempt_record") from error


def _record_release_attempt(
    paths: DeployPaths, release: Release, expected_uid: int
) -> None:
    records = _scan_attempt_records(paths, expected_uid, stage="attempt_record")
    references = {
        component: release.references[component] for component in APPLICATION_ARTIFACTS
    }
    existing = records.get(release.release_id)
    if existing is not None:
        if not _attempt_identity_matches(
            existing,
            source_commit=release.source_commit,
            references=references,
        ):
            raise DeployError("attempt_record")
        return
    if len(records) >= MAX_ATTEMPT_RECORDS:
        raise DeployError("attempt_capacity")
    value = {
        "schema_version": 1,
        "event": "release.attempt",
        "release_id": release.release_id,
        "source_commit": release.source_commit,
        "recorded_at": _utc_now(),
        "application_references": references,
    }
    _validate_attempt_record(
        value,
        expected_release_id=release.release_id,
        stage="attempt_record",
    )
    try:
        _publish_attempt_record(
            paths,
            release_id=release.release_id,
            value=value,
            expected_uid=expected_uid,
        )
    except OSError as error:
        raise DeployError("attempt_record") from error


def _transaction_exists(paths: DeployPaths) -> bool:
    try:
        info = paths.transaction_dir.lstat()
    except FileNotFoundError:
        return False
    except OSError as error:
        raise DeployError("incomplete_transaction") from error
    if not stat.S_ISDIR(info.st_mode) or paths.transaction_dir.is_symlink():
        raise DeployError("incomplete_transaction")
    return True


def _assert_no_incomplete_transaction(paths: DeployPaths) -> None:
    if _transaction_exists(paths):
        raise DeployError("incomplete_transaction")


def _create_transaction(
    paths: DeployPaths,
    *,
    release: Release,
    previous_release: str,
    previous_current_target: str,
    old_public: bytes,
    old_private: bytes,
    expected_uid: int,
) -> dict[str, object]:
    _assert_no_incomplete_transaction(paths)
    temporary = paths.transaction_dir.parent / f".deploy-transaction-{os.getpid()}"
    try:
        temporary.mkdir(mode=0o700)
        _secure_directory(temporary, stage="transaction", expected_uid=expected_uid)
        metadata: dict[str, object] = {
            "schema_version": 1,
            "state": "prepared",
            "release_id": release.release_id,
            "source_commit": release.source_commit,
            "previous_release": previous_release,
            "previous_current_target": previous_current_target,
        }
        _exclusive_write(temporary / TRANSACTION_PUBLIC, old_public, 0o600)
        _exclusive_write(temporary / TRANSACTION_PRIVATE, old_private, 0o600)
        _exclusive_write(
            temporary / TRANSACTION_METADATA,
            (json.dumps(metadata, sort_keys=True) + "\n").encode(),
            0o600,
        )
        _fsync_directory(temporary)
        os.replace(temporary, paths.transaction_dir)
        _fsync_directory(paths.transaction_dir.parent)
        return metadata
    except Exception:
        shutil.rmtree(temporary, ignore_errors=True)
        raise


def _transaction_metadata_pending(paths: DeployPaths) -> Path:
    return paths.transaction_dir.parent / TRANSACTION_METADATA_PENDING


def _cleanup_transaction_metadata_pending(
    paths: DeployPaths, expected_uid: int
) -> None:
    pending = _transaction_metadata_pending(paths)
    removed_parent = False
    if pending.exists() or pending.is_symlink():
        info = _trusted_pending_file(
            pending,
            expected_uid=expected_uid,
            stage="transaction_metadata_pending",
        )
        if info.st_nlink != 1:
            raise DeployError("transaction_metadata_pending")
        try:
            pending.unlink()
            _fsync_directory(pending.parent)
        except OSError as error:
            raise DeployError("transaction_metadata_pending") from error
        removed_parent = True
    if not _transaction_exists(paths):
        return
    _secure_directory(
        paths.transaction_dir,
        stage="transaction_metadata_pending",
        expected_uid=expected_uid,
    )
    try:
        legacy = [
            entry
            for entry in paths.transaction_dir.iterdir()
            if LEGACY_TRANSACTION_PENDING_PATTERN.fullmatch(entry.name)
        ]
    except OSError as error:
        raise DeployError("transaction_metadata_pending") from error
    if len(legacy) > 1:
        raise DeployError("transaction_metadata_pending")
    for entry in legacy:
        info = _trusted_pending_file(
            entry,
            expected_uid=expected_uid,
            stage="transaction_metadata_pending",
        )
        if info.st_nlink != 1:
            raise DeployError("transaction_metadata_pending")
        try:
            entry.unlink()
            _fsync_directory(paths.transaction_dir)
        except OSError as error:
            raise DeployError("transaction_metadata_pending") from error
    if removed_parent:
        _fsync_directory(paths.transaction_dir.parent)


def _mark_transaction_live(
    paths: DeployPaths, metadata: dict[str, object], expected_uid: int
) -> None:
    _secure_directory(
        paths.transaction_dir, stage="transaction", expected_uid=expected_uid
    )
    updated = dict(metadata)
    updated["state"] = "live_mutated"
    pending = _transaction_metadata_pending(paths)
    _cleanup_transaction_metadata_pending(paths, expected_uid)
    try:
        _write_pending_file(
            pending,
            (json.dumps(updated, sort_keys=True) + "\n").encode(),
        )
        os.replace(pending, paths.transaction_dir / TRANSACTION_METADATA)
        _fsync_directory(paths.transaction_dir)
        _fsync_directory(paths.transaction_dir.parent)
    except OSError as error:
        raise DeployError("transaction_metadata") from error


def _load_transaction(
    paths: DeployPaths,
    expected_uid: int,
    *,
    directory: Path | None = None,
) -> tuple[dict[str, object], bytes, bytes]:
    transaction_dir = directory or paths.transaction_dir
    if directory is None:
        _cleanup_transaction_metadata_pending(paths, expected_uid)
        if not _transaction_exists(paths):
            raise DeployError("incomplete_transaction")
    _secure_directory(
        transaction_dir,
        stage="incomplete_transaction",
        expected_uid=expected_uid,
    )
    try:
        names = {entry.name for entry in transaction_dir.iterdir()}
    except OSError as error:
        raise DeployError("incomplete_transaction") from error
    if names != {TRANSACTION_METADATA, TRANSACTION_PUBLIC, TRANSACTION_PRIVATE}:
        raise DeployError("incomplete_transaction")
    metadata_content = _secure_read_bytes(
        transaction_dir / TRANSACTION_METADATA,
        stage="incomplete_transaction",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    metadata = _json_record(metadata_content, stage="incomplete_transaction")
    if not isinstance(metadata, dict) or set(metadata) != TRANSACTION_KEYS:
        raise DeployError("incomplete_transaction")
    if (
        metadata.get("schema_version") != 1
        or isinstance(metadata.get("schema_version"), bool)
        or metadata.get("state") not in {"prepared", "live_mutated"}
    ):
        raise DeployError("incomplete_transaction")
    for key in ("release_id", "previous_release"):
        value = metadata.get(key)
        if not isinstance(value, str) or not RELEASE_ID_PATTERN.fullmatch(value):
            raise DeployError("incomplete_transaction")
    source_commit = metadata.get("source_commit")
    if not isinstance(source_commit, str) or not SOURCE_COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        raise DeployError("incomplete_transaction")
    previous_target = metadata.get("previous_current_target")
    previous_release = metadata["previous_release"]
    expected_previous_target = (
        PurePosixPath(paths.releases_dir.name) / str(previous_release)
    ).as_posix()
    if (
        not isinstance(previous_target, str)
        or "\x00" in previous_target
        or Path(previous_target).is_absolute()
        or ".." in Path(previous_target).parts
        or previous_target != expected_previous_target
    ):
        raise DeployError("incomplete_transaction")
    old_public = _secure_read_bytes(
        transaction_dir / TRANSACTION_PUBLIC,
        stage="incomplete_transaction",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    old_private = _secure_read_bytes(
        transaction_dir / TRANSACTION_PRIVATE,
        stage="incomplete_transaction",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    _runtime_images(old_public, stage="incomplete_transaction")
    _dotenv_values(old_private, stage="incomplete_transaction")
    return metadata, old_public, old_private


def _transaction_tombstone(paths: DeployPaths) -> Path:
    return paths.transaction_dir.with_name(f"{paths.transaction_dir.name}.completed")


def _delete_transaction_directory(directory: Path) -> None:
    try:
        for filename in (
            TRANSACTION_METADATA,
            TRANSACTION_PUBLIC,
            TRANSACTION_PRIVATE,
        ):
            (directory / filename).unlink(missing_ok=True)
        directory.rmdir()
    except OSError as error:
        raise DeployError("transaction_cleanup") from error


def _cleanup_transaction_tombstone(paths: DeployPaths, expected_uid: int) -> None:
    tombstone = _transaction_tombstone(paths)
    if not tombstone.exists() and not tombstone.is_symlink():
        return
    _secure_directory(
        tombstone,
        stage="transaction_tombstone",
        expected_uid=expected_uid,
    )
    try:
        entries = {entry.name: entry for entry in tombstone.iterdir()}
    except OSError as error:
        raise DeployError("transaction_tombstone") from error
    allowed = {TRANSACTION_METADATA, TRANSACTION_PUBLIC, TRANSACTION_PRIVATE}
    if not set(entries).issubset(allowed):
        raise DeployError("transaction_tombstone")
    for entry in entries.values():
        _secure_regular_file(
            entry,
            stage="transaction_tombstone",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=MAX_RECORD_BYTES,
        )
    _delete_transaction_directory(tombstone)
    _fsync_directory(tombstone.parent)


def _remove_transaction(paths: DeployPaths, expected_uid: int) -> None:
    _cleanup_transaction_metadata_pending(paths, expected_uid)
    _cleanup_transaction_tombstone(paths, expected_uid)
    _load_transaction(paths, expected_uid)
    tombstone = _transaction_tombstone(paths)
    try:
        os.replace(paths.transaction_dir, tombstone)
        _fsync_directory(paths.transaction_dir.parent)
    except OSError as error:
        raise DeployError("transaction_cleanup") from error
    try:
        _delete_transaction_directory(tombstone)
        _fsync_directory(tombstone.parent)
    except DeployError:
        # The canonical journal removal is already durably committed. A later
        # start, boot-recovery invocation, or GC pass validates and removes the
        # root-owned tombstone without replaying compensation.
        return


def _current_release(paths: DeployPaths, expected_uid: int) -> tuple[Path, str]:
    info = _lstat(paths.current_link, stage="current_release")
    if not stat.S_ISLNK(info.st_mode):
        raise DeployError("current_release")
    try:
        raw_target = os.readlink(paths.current_link)
        resolved = paths.current_link.resolve(strict=True)
        releases = paths.releases_dir.resolve(strict=True)
    except OSError as error:
        raise DeployError("current_release") from error
    raw_path = Path(raw_target)
    normalized_target = os.path.relpath(resolved, paths.current_link.parent)
    if (
        raw_path.is_absolute()
        or ".." in raw_path.parts
        or raw_target != normalized_target
        or resolved.parent != releases
        or resolved == releases
    ):
        raise DeployError("current_release")
    _secure_directory(resolved, stage="current_release", expected_uid=expected_uid)
    for filename in REQUIRED_BUNDLE_FILES:
        release_file = resolved / filename
        _secure_regular_file(
            release_file,
            stage="current_release",
            expected_uid=expected_uid,
            sensitive=False,
        )
        if (
            os.name != "nt"
            and filename in EXECUTABLE_BUNDLE_FILES
            and stat.S_IMODE(_lstat(release_file, stage="current_release").st_mode)
            != 0o755
        ):
            raise DeployError("current_release")
    _secure_regular_file(
        resolved / ".env",
        stage="current_release",
        expected_uid=expected_uid,
        sensitive=True,
    )
    return resolved, raw_target


def _release_source_sha(release: Path, expected_uid: int) -> str:
    marker = release / SOURCE_MARKER
    _secure_regular_file(
        marker,
        stage="current_source",
        expected_uid=expected_uid,
        sensitive=False,
        maximum_bytes=65,
    )
    try:
        content = marker.read_text(encoding="ascii")
    except (OSError, UnicodeError) as error:
        raise DeployError("current_source") from error
    source_sha = content.removesuffix("\n")
    if content != f"{source_sha}\n" or not SOURCE_COMMIT_PATTERN.fullmatch(source_sha):
        raise DeployError("current_source")
    return source_sha


def _cleanup_runtime_atomic_temps(paths: DeployPaths, expected_uid: int) -> int:
    if paths.public_runtime.parent != paths.private_runtime.parent:
        raise DeployError("runtime_pending")
    return _cleanup_atomic_write_temps(
        paths.public_runtime.parent,
        target_names={paths.public_runtime.name, paths.private_runtime.name},
        expected_uid=expected_uid,
        stage="runtime_pending",
    )


def _atomic_write_runtime(
    paths: DeployPaths, path: Path, content: bytes, expected_uid: int
) -> None:
    if path not in {paths.public_runtime, paths.private_runtime}:
        raise DeployError("runtime_pending")
    _cleanup_runtime_atomic_temps(paths, expected_uid)
    _atomic_write(path, content, 0o600)


def report_current_source_sha(
    paths: DeployPaths,
    *,
    expected_uid: int = 0,
    require_root: bool = True,
    lock_factory: Callable[[], AbstractContextManager[object]] | None = None,
) -> str:
    """Return the validated active source commit without exposing runtime data."""

    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    acquire_lock = lock_factory or (
        lambda: ProductionLock(paths.lock_file, expected_uid)
    )
    with acquire_lock():
        _assert_no_incomplete_transaction(paths)
        _cleanup_runtime_atomic_temps(paths, expected_uid)
        for directory in (
            paths.releases_dir,
            paths.history_dir,
            paths.current_link.parent,
            paths.public_runtime.parent,
        ):
            _secure_directory(
                directory,
                stage="current_release",
                expected_uid=expected_uid,
            )
        current_release, _target = _current_release(paths, expected_uid)
        public_runtime = _secure_read_bytes(
            paths.public_runtime,
            stage="runtime",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=MAX_RECORD_BYTES,
        )
        private_runtime = _secure_read_bytes(
            paths.private_runtime,
            stage="runtime",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=MAX_RECORD_BYTES,
        )
        accepted = _validate_accepted_current(
            paths,
            current_release,
            public_runtime,
            private_runtime,
            expected_uid,
        )
        return str(accepted["source_commit"])


def _assert_platform_unchanged(candidate: Path, current: Path, uid: int) -> None:
    for filename in BASELINE_LOCKED_FILES:
        current_file = current / filename
        candidate_file = candidate / filename
        _secure_regular_file(
            current_file,
            stage="platform_baseline",
            expected_uid=uid,
            sensitive=False,
        )
        _secure_regular_file(
            candidate_file,
            stage="platform_candidate",
            expected_uid=uid,
            sensitive=False,
        )
        try:
            current_hash = hashlib.sha256(current_file.read_bytes()).digest()
            candidate_hash = hashlib.sha256(candidate_file.read_bytes()).digest()
        except OSError as error:
            raise DeployError("platform_drift") from error
        if current_hash != candidate_hash:
            raise DeployError("platform_drift")


def _switch_current(path: Path, target: str) -> None:
    temporary = path.parent / f".{path.name}-{os.getpid()}"
    try:
        temporary.unlink(missing_ok=True)
        os.symlink(target, temporary, target_is_directory=True)
        os.replace(temporary, path)
        _fsync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _remove_unactivated_candidate(
    candidate: Path,
    *,
    releases_dir: Path,
    release_id: str,
    expected_uid: int,
) -> None:
    try:
        resolved_releases = releases_dir.resolve(strict=True)
        resolved_candidate_parent = candidate.parent.resolve(strict=True)
    except OSError as error:
        raise DeployError("candidate_cleanup") from error
    if (
        candidate.name != release_id
        or resolved_candidate_parent != resolved_releases
        or candidate.is_symlink()
    ):
        raise DeployError("candidate_cleanup")
    _secure_directory(
        candidate,
        stage="candidate_cleanup",
        expected_uid=expected_uid,
    )
    try:
        shutil.rmtree(candidate)
        _fsync_directory(releases_dir)
    except OSError as error:
        raise DeployError("candidate_cleanup") from error


def _compose(env: Path, compose: Path) -> list[str]:
    return ["docker", "compose", "--env-file", str(env), "-f", str(compose)]


def _validate_recovery_compose_contract(
    content: str,
    *,
    public_runtime: bytes,
) -> None:
    encoded = content.encode("utf-8")
    if len(encoded) > MAX_RECORD_BYTES:
        raise DeployError("recovery_compose_contract")
    value = _json_record(encoded, stage="recovery_compose_contract")
    if not isinstance(value, dict):
        raise DeployError("recovery_compose_contract")
    services = value.get("services")
    expected_services = EXPECTED_DEFAULT_SERVICES | EXPECTED_OPERATION_SERVICES
    if not isinstance(services, dict) or set(services) != expected_services:
        raise DeployError("recovery_compose_contract")

    for name, expected_dependencies in EXPECTED_PUBLIC_SERVICE_DEPENDENCIES.items():
        record = services.get(name)
        if not isinstance(record, dict):
            raise DeployError("recovery_compose_contract")
        profiles = record.get("profiles", [])
        expected_profiles = (
            ["operations"] if name in EXPECTED_OPERATION_SERVICES else []
        )
        if profiles != expected_profiles:
            raise DeployError("recovery_compose_contract")
        dependencies = record.get("depends_on", {})
        if (
            not isinstance(dependencies, dict)
            or set(dependencies) != expected_dependencies
        ):
            raise DeployError("recovery_compose_contract")

    runtime_images = _runtime_images(public_runtime, stage="recovery_compose_contract")
    for service, component in EXPECTED_PUBLIC_SERVICE_IMAGES.items():
        record = services[service]
        if (
            not isinstance(record, dict)
            or record.get("image") != runtime_images[component]
        ):
            raise DeployError("recovery_compose_contract")

    recovery_services = (
        *RECOVERY_STATEFUL_SERVICES,
        *RECOVERY_INITIALIZER_SERVICES,
        *RECOVERY_APPLICATION_SERVICES,
        *RECOVERY_EDGE_SERVICES,
    )
    if (
        len(recovery_services) != len(set(recovery_services))
        or set(recovery_services) | RECOVERY_FORBIDDEN_SERVICES
        != EXPECTED_DEFAULT_SERVICES
        or set(recovery_services) & RECOVERY_FORBIDDEN_SERVICES
    ):
        raise DeployError("recovery_compose_contract")


class Deployer:
    def __init__(
        self,
        paths: DeployPaths,
        *,
        runner: CommandRunner | None = None,
        expected_uid: int = 0,
        require_root: bool = True,
        lock_factory: Callable[[], AbstractContextManager[object]] | None = None,
        input_root: Path | None = None,
        input_owner_uid: int | None = None,
    ) -> None:
        self.paths = paths
        self.runner = runner or CommandRunner()
        self.expected_uid = expected_uid
        self.require_root = require_root
        self.lock_factory = lock_factory or (
            lambda: ProductionLock(paths.lock_file, expected_uid)
        )
        self.input_root = input_root or paths.incoming_root
        self.input_owner_uid = input_owner_uid

    def _control_preflight(
        self,
        bundle: Path,
        manifest: Path,
        checksum: Path,
        expected_release_id: str,
    ) -> None:
        if self.require_root and _effective_uid() != 0:
            raise DeployError("root")
        for directory in (
            self.paths.releases_dir,
            self.paths.history_dir,
            self.paths.attempts_dir,
            self.paths.current_link.parent,
            self.paths.launch_marker.parent,
            self.paths.public_runtime.parent,
            self.paths.private_runtime.parent,
            self.input_root.parent,
        ):
            _secure_directory(
                directory, stage="control_directory", expected_uid=self.expected_uid
            )
        _secure_directory(
            self.input_root,
            stage="incoming",
            expected_uid=self.input_owner_uid,
        )
        incoming_info = _lstat(self.input_root, stage="incoming")
        incoming_uid = incoming_info.st_uid
        expected_input_uid = self.input_owner_uid
        if os.name != "nt" and expected_input_uid is None and incoming_uid == 0:
            raise DeployError("incoming")
        if expected_input_uid is not None and incoming_uid != expected_input_uid:
            raise DeployError("incoming")
        if os.name != "nt" and stat.S_IMODE(incoming_info.st_mode) != 0o700:
            raise DeployError("incoming")
        _secure_regular_file(
            self.paths.launch_marker,
            stage="launch_marker",
            expected_uid=self.expected_uid,
            sensitive=False,
        )
        try:
            marker_content = self.paths.launch_marker.read_text(encoding="ascii")
        except (OSError, UnicodeError) as error:
            raise DeployError("launch_marker") from error
        if marker_content != LAUNCH_MARKER_CONTENT:
            raise DeployError("launch_marker")
        _cleanup_runtime_atomic_temps(self.paths, self.expected_uid)
        for runtime in (self.paths.public_runtime, self.paths.private_runtime):
            _secure_regular_file(
                runtime,
                stage="runtime",
                expected_uid=self.expected_uid,
                sensitive=True,
            )

        expected_parent = self.input_root / expected_release_id
        _secure_directory(expected_parent, stage="incoming", expected_uid=incoming_uid)
        if os.name != "nt" and stat.S_IMODE(expected_parent.stat().st_mode) != 0o700:
            raise DeployError("incoming")
        try:
            expected_parent_resolved = expected_parent.resolve(strict=True)
        except OSError as error:
            raise DeployError("incoming") from error
        for path, size in (
            (bundle, MAX_ARCHIVE_BYTES * 2),
            (manifest, MAX_MANIFEST_BYTES),
            (checksum, 1024),
        ):
            _secure_regular_file(
                path,
                stage="incoming",
                expected_uid=incoming_uid,
                sensitive=True,
                maximum_bytes=size,
            )
            try:
                if path.resolve(strict=True).parent != expected_parent_resolved:
                    raise DeployError("incoming")
            except OSError as error:
                raise DeployError("incoming") from error
        if len({bundle.resolve(), manifest.resolve(), checksum.resolve()}) != 3:
            raise DeployError("incoming")

    def _prepare_candidate(
        self,
        bundle_content: bytes,
        release: Release,
        manifest_name: str,
        manifest_content: bytes,
        checksum_name: str,
        checksum_content: bytes,
        target_public: bytes,
        target_private: bytes,
        current_release: Path,
    ) -> Path:
        final = self.paths.releases_dir / release.release_id
        history = self.paths.history_dir / f"{release.release_id}.json"
        if (
            final.exists()
            or final.is_symlink()
            or history.exists()
            or history.is_symlink()
        ):
            raise DeployError("release_reuse")

        staging = Path(
            tempfile.mkdtemp(
                prefix=f".incoming-{release.release_id}-",
                dir=self.paths.releases_dir,
            )
        )
        promoted = False
        try:
            os.chmod(staging, 0o755)
            extract_bundle(bundle_content, staging, release.source_commit)
            _assert_platform_unchanged(staging, current_release, self.expected_uid)
            _atomic_write(staging / ".env", target_public, 0o600)

            evidence = staging / ".release"
            evidence.mkdir(mode=0o700)
            _atomic_write(evidence / manifest_name, manifest_content, 0o600)
            _atomic_write(evidence / checksum_name, checksum_content, 0o600)

            validation = staging / ".validation"
            validation.mkdir(mode=0o700)
            public_validation = validation / "production.env"
            private_validation = validation / "private-studio.env"
            topology_model = validation / "compose.json"
            _atomic_write(public_validation, target_public, 0o600)
            _atomic_write(private_validation, target_private, 0o600)

            hostinger = staging / HOSTINGER
            private_root = staging / PRIVATE_STUDIO
            self.runner.run(
                "validate_runtime",
                [
                    sys.executable,
                    str(hostinger / "prepare_vps_env.py"),
                    "validate-runtime",
                    "--input",
                    str(public_validation),
                ],
                timeout=120,
            )
            self.runner.run(
                "render_monitoring",
                [
                    sys.executable,
                    str(hostinger / "render_monitoring.py"),
                    "--mode",
                    "deploy",
                    "--input",
                    str(public_validation),
                    "--output",
                    str(hostinger / "prometheus.local.yml"),
                    "--targets-output",
                    str(hostinger / "blackbox-targets.local.yml"),
                ],
                timeout=120,
            )
            for filename in GENERATED_RUNTIME_FILES:
                _secure_regular_file(
                    staging / filename,
                    stage="render_monitoring",
                    expected_uid=self.expected_uid,
                    sensitive=True,
                )
            model = self.runner.run(
                "compose_config",
                [
                    *_compose(public_validation, hostinger / "compose.yml"),
                    "config",
                    "--format",
                    "json",
                ],
                capture=True,
                timeout=180,
            )
            _atomic_write(topology_model, model.encode("utf-8"), 0o600)
            self.runner.run(
                "validate_topology",
                [
                    sys.executable,
                    str(hostinger / "validate_topology.py"),
                    "--input",
                    str(topology_model),
                ],
                timeout=120,
            )
            self.runner.run(
                "validate_coupling_artifacts",
                [
                    sys.executable,
                    str(hostinger / "validate_caddy_coupling.py"),
                    "--public-env",
                    str(public_validation),
                    "--private-env",
                    str(private_validation),
                    "--public-compose",
                    str(hostinger / "compose.yml"),
                    "--private-compose",
                    str(private_root / "compose.yml"),
                ],
                timeout=120,
            )
            shutil.rmtree(validation)
            os.replace(staging, final)
            _fsync_directory(self.paths.releases_dir)
            promoted = True
            return final
        finally:
            if not promoted:
                shutil.rmtree(staging, ignore_errors=True)

    def _commands(self, release_root: Path) -> dict[str, list[str]]:
        public_compose_file = release_root / HOSTINGER / "compose.yml"
        private_compose_file = release_root / PRIVATE_STUDIO / "compose.yml"
        public = _compose(self.paths.public_runtime, public_compose_file)
        private = _compose(self.paths.private_runtime, private_compose_file)

        def recovery_up(services: tuple[str, ...], *, wait_timeout: int) -> list[str]:
            if not services or set(services) & RECOVERY_FORBIDDEN_SERVICES:
                raise DeployError("recovery_compose_contract")
            return [
                *public,
                "up",
                "-d",
                "--no-build",
                "--no-deps",
                "--wait",
                "--wait-timeout",
                str(wait_timeout),
                *services,
            ]

        return {
            "backup": [
                "/bin/sh",
                str(release_root / HOSTINGER / "operations.sh"),
                "backup",
            ],
            "public_up": [
                *public,
                "up",
                "-d",
                "--no-build",
                "--remove-orphans",
                "--wait",
                "--wait-timeout",
                "600",
            ],
            "recovery_compose_config": [
                *public,
                "--profile",
                "operations",
                "config",
                "--format",
                "json",
            ],
            "recovery_migrate_remove": [
                *public,
                "rm",
                "--stop",
                "--force",
                "migrate",
            ],
            "recovery_stateful_up": recovery_up(
                RECOVERY_STATEFUL_SERVICES, wait_timeout=600
            ),
            # `minio-init` is an idempotent one-shot. A detached `--wait`
            # command can reject its successful exited state, so run only
            # this explicitly named initializer and propagate its exit code.
            "recovery_initializer_up": [
                *public,
                "up",
                "--no-build",
                "--no-deps",
                "--exit-code-from",
                "minio-init",
                "minio-init",
            ],
            "recovery_application_up": recovery_up(
                RECOVERY_APPLICATION_SERVICES, wait_timeout=600
            ),
            "recovery_edge_up": recovery_up(RECOVERY_EDGE_SERVICES, wait_timeout=180),
            "private_up": [
                *private,
                "up",
                "-d",
                "--no-build",
                "--remove-orphans",
                "--wait",
                "--wait-timeout",
                "120",
            ],
            "preflight": [
                "/bin/sh",
                str(release_root / HOSTINGER / "operations.sh"),
                "preflight",
            ],
            "coupling": [
                sys.executable,
                str(release_root / HOSTINGER / "validate_caddy_coupling.py"),
                "--public-env",
                str(self.paths.public_runtime),
                "--private-env",
                str(self.paths.private_runtime),
                "--public-compose",
                str(public_compose_file),
                "--private-compose",
                str(private_compose_file),
                "--check-running",
            ],
            "smoke": [
                sys.executable,
                str(release_root / PUBLIC_EDGE_SMOKE),
                "--environment",
                "production",
            ],
        }

    def _smoke_environment(self) -> dict[str, str]:
        try:
            content = self.paths.public_runtime.read_bytes()
        except OSError as error:
            raise DeployError("smoke_configuration") from error
        hostname = _dotenv_values(content, stage="smoke_configuration").get(
            "WEB_HOSTNAME", ""
        )
        if not HOSTNAME_PATTERN.fullmatch(hostname):
            raise DeployError("smoke_configuration")
        return {"SMOKE_WEB_ORIGIN": f"https://{hostname}"}

    def _compensate(
        self,
        *,
        old_public: bytes,
        old_private: bytes,
        old_current_target: str,
    ) -> str | None:
        first_failure: str | None = None

        def attempt(stage: str, operation: Callable[[], None]) -> bool:
            nonlocal first_failure
            try:
                operation()
                return True
            except Exception:
                if first_failure is None:
                    first_failure = stage
                return False

        public_ok = attempt(
            "recovery_public_runtime",
            lambda: _atomic_write_runtime(
                self.paths,
                self.paths.public_runtime,
                old_public,
                self.expected_uid,
            ),
        )
        private_ok = attempt(
            "recovery_private_runtime",
            lambda: _atomic_write_runtime(
                self.paths,
                self.paths.private_runtime,
                old_private,
                self.expected_uid,
            ),
        )
        current_ok = attempt(
            "recovery_current_release",
            lambda: _switch_current(self.paths.current_link, old_current_target),
        )
        if not (public_ok and private_ok and current_ok):
            return first_failure

        commands = self._commands(self.paths.current_link)

        def validate_recovery_contract() -> None:
            content = self.runner.run(
                "recovery_compose_contract",
                commands["recovery_compose_config"],
                capture=True,
                timeout=180,
            )
            _validate_recovery_compose_contract(
                content,
                public_runtime=old_public,
            )

        if not attempt(
            "recovery_compose_contract",
            validate_recovery_contract,
        ):
            return first_failure
        # A timed-out target rollout can leave its migration container alive.
        # Stop and remove that exact project service before any predecessor
        # application starts. `compose rm` cannot create or execute migration.
        if not attempt(
            "recovery_migrate_remove",
            lambda: self.runner.run(
                "recovery_migrate_remove",
                commands["recovery_migrate_remove"],
                timeout=120,
            ),
        ):
            return first_failure
        recovery_phases = (
            (
                "recovery_stateful_rollout",
                "recovery_stateful_up",
                720,
            ),
            (
                "recovery_initializer_rollout",
                "recovery_initializer_up",
                240,
            ),
            (
                "recovery_application_rollout",
                "recovery_application_up",
                720,
            ),
            ("recovery_edge_rollout", "recovery_edge_up", 240),
        )
        for stage, command_name, timeout in recovery_phases:
            if not attempt(
                stage,
                lambda stage=stage, command_name=command_name, timeout=timeout: (
                    self.runner.run(
                        stage,
                        commands[command_name],
                        timeout=timeout,
                    )
                ),
            ):
                return first_failure
        if not attempt(
            "recovery_private_rollout",
            lambda: self.runner.run(
                "recovery_private_rollout", commands["private_up"], timeout=240
            ),
        ):
            return first_failure
        if not attempt(
            "recovery_preflight",
            lambda: self.runner.run(
                "recovery_preflight", commands["preflight"], timeout=600
            ),
        ):
            return first_failure
        if not attempt(
            "recovery_coupling",
            lambda: self.runner.run(
                "recovery_coupling", commands["coupling"], timeout=120
            ),
        ):
            return first_failure
        attempt(
            "recovery_public_smoke",
            lambda: self.runner.run(
                "recovery_public_smoke",
                commands["smoke"],
                environment=self._smoke_environment(),
                timeout=120,
            ),
        )
        return first_failure

    def _recover_incomplete_transaction_locked(
        self, *, remove_journal: bool = True
    ) -> dict[str, object]:
        """Restore one journal while the caller owns the production lock."""

        metadata, old_public, old_private = _load_transaction(
            self.paths, self.expected_uid
        )
        previous_target = str(metadata["previous_current_target"])
        recovery_failure = self._compensate(
            old_public=old_public,
            old_private=old_private,
            old_current_target=previous_target,
        )
        if recovery_failure is not None:
            raise DeploymentExecutionError(
                "incomplete_transaction",
                "failed",
                recovery_failure,
            )
        _remove_interrupted_acceptance(
            self.paths,
            str(metadata["release_id"]),
            self.expected_uid,
        )
        restored_release, _target = _current_release(self.paths, self.expected_uid)
        if restored_release.name != metadata["previous_release"]:
            raise DeploymentExecutionError(
                "incomplete_transaction",
                "failed",
                "recovery_current_release",
            )
        _validate_accepted_current(
            self.paths,
            restored_release,
            old_public,
            old_private,
            self.expected_uid,
        )
        if remove_journal:
            _remove_transaction(self.paths, self.expected_uid)
        return {
            "event": "release.deploy",
            "status": "fail",
            "stage": "interrupted_transaction",
            "recovery_status": "completed",
            "release_id": metadata["release_id"],
            "source_commit": metadata["source_commit"],
        }

    def recover_incomplete_transaction(
        self, *, remove_journal: bool = True
    ) -> dict[str, object]:
        """Restore the accepted predecessor recorded before a lost worker."""

        if self.require_root and _effective_uid() != 0:
            raise DeployError("root")
        with self.lock_factory():
            return self._recover_incomplete_transaction_locked(
                remove_journal=remove_journal
            )

    def deploy(
        self,
        *,
        bundle: Path,
        manifest: Path,
        checksum: Path,
        expected_current_source_sha: str,
        expected_source_sha: str,
        expected_release_id: str,
    ) -> dict[str, object]:
        if self.require_root and _effective_uid() != 0:
            raise DeployError("root")
        if not SOURCE_COMMIT_PATTERN.fullmatch(expected_current_source_sha):
            raise DeployError("expected_current_source")
        with self.lock_factory():
            _assert_no_incomplete_transaction(self.paths)
            self._control_preflight(bundle, manifest, checksum, expected_release_id)
            current_release, old_current_target = _current_release(
                self.paths, self.expected_uid
            )
            try:
                manifest_content = manifest.read_bytes()
                checksum_content = checksum.read_bytes()
                bundle_content = bundle.read_bytes()
            except OSError as error:
                raise DeployError("incoming") from error
            if not manifest_content or not bundle_content:
                raise DeployError("incoming")
            validate_checksum(
                manifest,
                bundle,
                checksum,
                manifest_content,
                bundle_content,
            )
            release = validate_manifest(
                manifest_content,
                expected_source_sha=expected_source_sha,
                expected_release_id=expected_release_id,
            )

            try:
                old_public = self.paths.public_runtime.read_bytes()
                old_private = self.paths.private_runtime.read_bytes()
                current_snapshot = (current_release / ".env").read_bytes()
            except OSError as error:
                raise DeployError("runtime") from error
            accepted_current = _validate_accepted_current(
                self.paths,
                current_release,
                old_public,
                old_private,
                self.expected_uid,
            )
            if accepted_current["source_commit"] != expected_current_source_sha:
                raise DeployError("current_source_drift")
            if current_snapshot != old_public:
                raise DeployError("runtime_snapshot")
            current_images = _runtime_images(old_public, stage="runtime")
            current_private = _dotenv_values(old_private, stage="private_runtime")
            if current_private.get("CADDY_IMAGE") != current_images["caddy"]:
                raise DeployError("caddy_coupling")
            for component in UNATTENDED_INFRA:
                if _digest(current_images[component]) != release.digests[component]:
                    raise DeployError(f"{component}_drift")

            effective_references = {
                component: (
                    current_images[component]
                    if component in UNATTENDED_INFRA
                    else release.references[component]
                )
                for component in ARTIFACTS
            }
            target_public = _replace_assignments(
                old_public,
                {
                    IMAGE_LABELS[component]: effective_references[component]
                    for component in ARTIFACTS
                },
                stage="runtime_update",
            )
            target_private = _replace_assignments(
                old_private,
                {"CADDY_IMAGE": effective_references["caddy"]},
                stage="private_runtime_update",
            )
            _runtime_images(target_public, stage="target_runtime")

            candidate = self._prepare_candidate(
                bundle_content,
                release,
                manifest.name,
                manifest_content,
                checksum.name,
                checksum_content,
                target_public,
                target_private,
                current_release,
            )

            # This backup is the last operation before registry or live-state
            # mutation.  It uses the currently active release and credentials.
            try:
                # Persist the exact application references before the first
                # pull. GC can then account for images left by a failed or
                # interrupted attempt even after its candidate is removed.
                _record_release_attempt(self.paths, release, self.expected_uid)
                old_commands = self._commands(self.paths.current_link)
                self.runner.run(
                    "predeploy_backup", old_commands["backup"], timeout=1200
                )
                for component in ARTIFACTS:
                    self.runner.run(
                        f"pull_{component}",
                        ["docker", "pull", release.references[component]],
                        timeout=300,
                    )
                self.runner.run(
                    "inspect_images",
                    ["docker", "image", "inspect", *release.references.values()],
                    timeout=120,
                )
            except Exception:
                _remove_unactivated_candidate(
                    candidate,
                    releases_dir=self.paths.releases_dir,
                    release_id=release.release_id,
                    expected_uid=self.expected_uid,
                )
                raise

            try:
                transaction = _create_transaction(
                    self.paths,
                    release=release,
                    previous_release=current_release.name,
                    previous_current_target=old_current_target,
                    old_public=old_public,
                    old_private=old_private,
                    expected_uid=self.expected_uid,
                )
            except Exception:
                _remove_unactivated_candidate(
                    candidate,
                    releases_dir=self.paths.releases_dir,
                    release_id=release.release_id,
                    expected_uid=self.expected_uid,
                )
                raise
            live_mutated = False
            acceptance_published = False
            failed_stage = "runtime_update"
            try:
                _mark_transaction_live(self.paths, transaction, self.expected_uid)
                live_mutated = True
                _atomic_write_runtime(
                    self.paths,
                    self.paths.public_runtime,
                    target_public,
                    self.expected_uid,
                )
                failed_stage = "private_runtime_update"
                _atomic_write_runtime(
                    self.paths,
                    self.paths.private_runtime,
                    target_private,
                    self.expected_uid,
                )
                failed_stage = "current_release_update"
                relative_candidate = os.path.relpath(
                    candidate, self.paths.current_link.parent
                )
                _switch_current(self.paths.current_link, relative_candidate)

                commands = self._commands(self.paths.current_link)
                failed_stage = "public_rollout"
                self.runner.run("public_rollout", commands["public_up"], timeout=720)
                failed_stage = "private_rollout"
                self.runner.run("private_rollout", commands["private_up"], timeout=240)
                failed_stage = "target_preflight"
                self.runner.run("target_preflight", commands["preflight"], timeout=600)
                failed_stage = "target_coupling"
                self.runner.run("target_coupling", commands["coupling"], timeout=120)
                failed_stage = "target_public_smoke"
                self.runner.run(
                    "target_public_smoke",
                    commands["smoke"],
                    environment=self._smoke_environment(),
                    timeout=120,
                )

                failed_stage = "history"
                history = _accepted_record(
                    release,
                    effective_references=effective_references,
                    previous_release=current_release.name,
                )
                _publish_accepted_record(
                    self.paths,
                    release_id=release.release_id,
                    value=history,
                    expected_uid=self.expected_uid,
                )
                acceptance_published = True
                failed_stage = "transaction_cleanup"
                _remove_transaction(self.paths, self.expected_uid)
            except Exception as error:
                if not live_mutated:
                    try:
                        if _transaction_exists(self.paths):
                            _remove_transaction(self.paths, self.expected_uid)
                        _remove_unactivated_candidate(
                            candidate,
                            releases_dir=self.paths.releases_dir,
                            release_id=release.release_id,
                            expected_uid=self.expected_uid,
                        )
                    except Exception:
                        raise DeploymentExecutionError(
                            failed_stage,
                            "failed",
                            "pre_live_cleanup",
                        ) from error
                    raise
                history_cleanup_failed = False
                if failed_stage == "history" or acceptance_published:
                    try:
                        _remove_interrupted_acceptance(
                            self.paths,
                            release.release_id,
                            self.expected_uid,
                        )
                    except DeployError:
                        history_cleanup_failed = True
                recovery_failure = self._compensate(
                    old_public=old_public,
                    old_private=old_private,
                    old_current_target=old_current_target,
                )
                if recovery_failure is None and history_cleanup_failed:
                    recovery_failure = "history_cleanup"
                if recovery_failure is None:
                    try:
                        _remove_transaction(self.paths, self.expected_uid)
                    except Exception:
                        recovery_failure = "transaction_cleanup"
                raise DeploymentExecutionError(
                    failed_stage,
                    "completed" if recovery_failure is None else "failed",
                    recovery_failure,
                ) from error

            return {
                "event": "release.deploy",
                "status": "pass",
                "release_id": release.release_id,
                "source_commit": release.source_commit,
            }


def _read_accepted_record(
    paths: DeployPaths, release_id: str, expected_uid: int
) -> dict[str, object]:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise DeployError("gc_history")
    content = _secure_read_bytes(
        paths.history_dir / f"{release_id}.json",
        stage="gc_history",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    value = _json_record(content, stage="gc_history")
    if not isinstance(value, dict) or set(value) != ACCEPTED_RECORD_KEYS:
        raise DeployError("gc_history")
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or value.get("status") != "accepted"
        or value.get("release_id") != release_id
        or value.get("platform") != "linux/amd64"
        or value.get("database_schema_rollback") != "not_attempted"
    ):
        raise DeployError("gc_history")
    source = value.get("source_commit")
    if not isinstance(source, str) or not SOURCE_COMMIT_PATTERN.fullmatch(source):
        raise DeployError("gc_history")
    try:
        accepted_at = datetime.fromisoformat(value["accepted_at"])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as error:
        raise DeployError("gc_history") from error
    if accepted_at.tzinfo is None:
        raise DeployError("gc_history")
    previous = value.get("previous_release")
    if previous is not None and (
        not isinstance(previous, str) or not RELEASE_ID_PATTERN.fullmatch(previous)
    ):
        raise DeployError("gc_history")
    references = value.get("effective_runtime_references")
    digests = value.get("digests")
    if (
        not isinstance(references, dict)
        or set(references) != set(ARTIFACTS)
        or not isinstance(digests, dict)
        or set(digests) != set(ARTIFACTS)
    ):
        raise DeployError("gc_history")
    for component in ARTIFACTS:
        reference = references.get(component)
        digest = digests.get(component)
        if (
            not isinstance(reference, str)
            or not IMAGE_PATTERN.fullmatch(reference)
            or not reference.startswith(f"{EXPECTED_REPOSITORY}/")
            or not isinstance(digest, str)
            or digest != _digest(reference)
        ):
            raise DeployError("gc_history")
    return value


def _validate_accepted_release_snapshot(
    paths: DeployPaths,
    release_id: str,
    record: dict[str, object],
    expected_uid: int,
) -> Path:
    release = paths.releases_dir / release_id
    try:
        if release.parent.resolve(strict=True) != paths.releases_dir.resolve(
            strict=True
        ):
            raise DeployError("gc_release")
    except OSError as error:
        raise DeployError("gc_release") from error
    _secure_directory(release, stage="gc_release", expected_uid=expected_uid)
    for filename in REQUIRED_BUNDLE_FILES:
        _secure_regular_file(
            release / filename,
            stage="gc_release",
            expected_uid=expected_uid,
            sensitive=False,
        )
    runtime = _secure_read_bytes(
        release / ".env",
        stage="gc_release",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    if _release_source_sha(release, expected_uid) != record["source_commit"]:
        raise DeployError("gc_release")
    images = _runtime_images(runtime, stage="gc_release")
    if images != record["effective_runtime_references"]:
        raise DeployError("gc_release")
    return release


def _validate_root_tree(
    root: Path, *, parent: Path, expected_uid: int, stage: str
) -> None:
    try:
        if root.parent.resolve(strict=True) != parent.resolve(strict=True):
            raise DeployError(stage)
    except OSError as error:
        raise DeployError(stage) from error
    stack = [root]
    while stack:
        entry = stack.pop()
        info = _lstat(entry, stage=stage)
        if (
            entry.is_symlink()
            or info.st_uid != expected_uid
            or (os.name != "nt" and stat.S_IMODE(info.st_mode) & 0o022)
        ):
            raise DeployError(stage)
        if stat.S_ISDIR(info.st_mode):
            try:
                stack.extend(entry.iterdir())
            except OSError as error:
                raise DeployError(stage) from error
        elif not stat.S_ISREG(info.st_mode):
            raise DeployError(stage)


def _safe_remove_root_tree(
    root: Path, *, parent: Path, expected_uid: int, stage: str
) -> None:
    _validate_root_tree(
        root,
        parent=parent,
        expected_uid=expected_uid,
        stage=stage,
    )
    stack = [root]
    directories: list[Path] = []
    while stack:
        entry = stack.pop()
        info = _lstat(entry, stage=stage)
        if stat.S_ISDIR(info.st_mode):
            directories.append(entry)
            try:
                stack.extend(entry.iterdir())
            except OSError as error:
                raise DeployError(stage) from error
    try:
        for directory in reversed(directories):
            for child in tuple(directory.iterdir()):
                if child.is_dir() and not child.is_symlink():
                    continue
                child.unlink()
            directory.rmdir()
        _fsync_directory(parent)
    except OSError as error:
        raise DeployError(stage) from error


def _validate_flat_payload(
    directory: Path,
    *,
    parent: Path,
    expected_uid: int,
    expected_names: set[str],
    stage: str,
) -> dict[str, Path]:
    try:
        if directory.parent.resolve(strict=True) != parent.resolve(strict=True):
            raise DeployError(stage)
    except OSError as error:
        raise DeployError(stage) from error
    _secure_directory(directory, stage=stage, expected_uid=expected_uid)
    try:
        entries = {entry.name: entry for entry in directory.iterdir()}
    except OSError as error:
        raise DeployError(stage) from error
    if not set(entries).issubset(expected_names):
        raise DeployError(stage)
    for entry in entries.values():
        _secure_regular_file(
            entry,
            stage=stage,
            expected_uid=expected_uid,
            sensitive=True,
        )
    return entries


def _safe_remove_flat_payload(
    directory: Path,
    *,
    parent: Path,
    expected_uid: int,
    expected_names: set[str],
    stage: str,
) -> None:
    entries = _validate_flat_payload(
        directory,
        parent=parent,
        expected_uid=expected_uid,
        expected_names=expected_names,
        stage=stage,
    )
    try:
        for entry in entries.values():
            entry.unlink()
        directory.rmdir()
        _fsync_directory(parent)
    except OSError as error:
        raise DeployError(stage) from error


def _scan_accepted_records(
    paths: DeployPaths, expected_uid: int
) -> dict[str, dict[str, object]]:
    _cleanup_accepted_pending(paths, expected_uid)
    _secure_directory(paths.history_dir, stage="gc_history", expected_uid=expected_uid)
    records: dict[str, dict[str, object]] = {}
    try:
        entries = tuple(paths.history_dir.iterdir())
    except OSError as error:
        raise DeployError("gc_history") from error
    if len(entries) > 10000:
        raise DeployError("gc_history")
    for entry in entries:
        if entry.is_symlink() or entry.suffix != ".json":
            raise DeployError("gc_history")
        release_id = entry.stem
        records[release_id] = _read_accepted_record(paths, release_id, expected_uid)
    return records


def _release_cleanup_candidates(
    paths: DeployPaths,
    *,
    records: dict[str, dict[str, object]],
    protected: set[str],
    now_timestamp: float,
    expected_uid: int,
) -> tuple[list[Path], list[Path], set[str]]:
    try:
        entries = tuple(paths.releases_dir.iterdir())
    except OSError as error:
        raise DeployError("gc_release") from error
    if len(entries) > 10000:
        raise DeployError("gc_release")
    candidates: list[Path] = []
    tombstones: list[Path] = []
    orphans: set[str] = set()
    for entry in entries:
        info = _lstat(entry, stage="gc_release")
        tombstone_match = RELEASE_TOMBSTONE_PATTERN.fullmatch(entry.name)
        if tombstone_match is not None:
            original_name = tombstone_match.group("original")
            original_temporary = TEMPORARY_RELEASE_PATTERN.fullmatch(original_name)
            original_release_id = (
                original_temporary.group("release_id")
                if original_temporary is not None
                else original_name
            )
            canonical = paths.releases_dir / original_name
            if (
                entry.is_symlink()
                or not stat.S_ISDIR(info.st_mode)
                or not RELEASE_ID_PATTERN.fullmatch(original_release_id)
                or (original_temporary is None and original_release_id in protected)
                or canonical.exists()
                or canonical.is_symlink()
            ):
                raise DeployError("gc_release_tombstone")
            _secure_directory(
                entry,
                stage="gc_release_tombstone",
                expected_uid=expected_uid,
            )
            _validate_root_tree(
                entry,
                parent=paths.releases_dir,
                expected_uid=expected_uid,
                stage="gc_release_tombstone",
            )
            tombstones.append(entry)
            continue
        temporary_match = TEMPORARY_RELEASE_PATTERN.fullmatch(entry.name)
        release_id = (
            temporary_match.group("release_id")
            if temporary_match is not None
            else entry.name
        )
        if (
            entry.is_symlink()
            or not stat.S_ISDIR(info.st_mode)
            or not RELEASE_ID_PATTERN.fullmatch(release_id)
        ):
            raise DeployError("gc_release")
        _secure_directory(entry, stage="gc_release", expected_uid=expected_uid)
        if temporary_match is None and release_id in protected:
            _validate_root_tree(
                entry,
                parent=paths.releases_dir,
                expected_uid=expected_uid,
                stage="gc_release",
            )
            continue
        if temporary_match is None and release_id in records:
            _validate_accepted_release_snapshot(
                paths, release_id, records[release_id], expected_uid
            )
        elif now_timestamp - info.st_mtime < GC_ABANDONED_MIN_AGE_SECONDS:
            continue
        else:
            orphans.add(entry.name)
        _validate_root_tree(
            entry,
            parent=paths.releases_dir,
            expected_uid=expected_uid,
            stage="gc_release_remove",
        )
        candidates.append(entry)
    return candidates, tombstones, orphans


def _release_tombstone(paths: DeployPaths, release_path: Path) -> Path:
    temporary_match = TEMPORARY_RELEASE_PATTERN.fullmatch(release_path.name)
    if temporary_match is None and not RELEASE_ID_PATTERN.fullmatch(release_path.name):
        raise DeployError("gc_release_remove")
    return paths.releases_dir / f".gc-removed-{release_path.name}"


def _remove_release_tree_crash_consistent(
    paths: DeployPaths, release_path: Path, expected_uid: int
) -> None:
    _validate_root_tree(
        release_path,
        parent=paths.releases_dir,
        expected_uid=expected_uid,
        stage="gc_release_remove",
    )
    tombstone = _release_tombstone(paths, release_path)
    if tombstone.exists() or tombstone.is_symlink():
        raise DeployError("gc_release_tombstone")
    try:
        os.replace(release_path, tombstone)
        _fsync_directory(paths.releases_dir)
    except OSError as error:
        raise DeployError("gc_release_remove") from error
    _safe_remove_root_tree(
        tombstone,
        parent=paths.releases_dir,
        expected_uid=expected_uid,
        stage="gc_release_tombstone",
    )


def _local_stale_application_references(
    runner: CommandRunner, stale_references: set[str]
) -> list[str]:
    if not stale_references:
        return []
    inventory = runner.run(
        "gc_image_inventory",
        [
            "docker",
            "image",
            "ls",
            "--digests",
            "--no-trunc",
            "--format",
            "{{.Repository}}\t{{.Tag}}\t{{.Digest}}",
        ],
        capture=True,
        timeout=120,
    )
    if len(inventory.encode("utf-8")) > GC_MAX_INVENTORY_BYTES:
        raise DeployError("gc_image_inventory")
    lines = inventory.splitlines()
    if len(lines) > GC_MAX_INVENTORY_LINES:
        raise DeployError("gc_image_inventory")
    local: set[str] = set()
    for line in lines:
        fields = line.split("\t")
        if len(fields) != 3 or any(not field or "\x00" in field for field in fields):
            raise DeployError("gc_image_inventory")
        repository, _tag, digest = fields
        if repository == "<none>" or digest == "<none>":
            continue
        # Docker records a digest pull canonically as repository@digest and
        # commonly reports Tag=<none>. Tags are publication metadata, not a
        # stable local cleanup identity.
        reference = f"{repository}@{digest}"
        if reference in stale_references:
            local.add(reference)
    return sorted(local)


def _remove_application_images(runner: CommandRunner, references: list[str]) -> None:
    for offset in range(0, len(references), GC_IMAGE_REMOVE_BATCH):
        runner.run(
            "gc_images",
            [
                "docker",
                "image",
                "rm",
                *references[offset : offset + GC_IMAGE_REMOVE_BATCH],
            ],
            timeout=900,
        )


def _remove_attempt_records(
    paths: DeployPaths,
    release_ids: set[str],
    expected_uid: int,
) -> None:
    for release_id in sorted(release_ids):
        _read_attempt_record(paths, release_id, expected_uid)
        try:
            _attempt_record_path(paths, release_id).unlink()
            _fsync_directory(paths.attempts_dir)
        except OSError as error:
            raise DeployError("gc_attempt_remove") from error


def _record_time(record: dict[str, object], key: str) -> float:
    try:
        value = datetime.fromisoformat(record[key])  # type: ignore[arg-type]
    except (KeyError, TypeError, ValueError) as error:
        raise DeployError("gc_record_time") from error
    if value.tzinfo is None:
        raise DeployError("gc_record_time")
    return value.timestamp()


def _status_atomic_target_names(directory: Path, *, stage: str) -> set[str]:
    try:
        entries = tuple(directory.iterdir())
    except OSError as error:
        raise DeployError(stage) from error
    targets: set[str] = set()
    for entry in entries:
        if entry.suffix == ".json" and not entry.name.startswith("."):
            if RELEASE_ID_PATTERN.fullmatch(entry.stem):
                targets.add(entry.name)
            continue
        if not entry.name.startswith(".") or "-" not in entry.name:
            continue
        target_name, suffix = entry.name[1:].rsplit("-", 1)
        if (
            ATOMIC_TEMP_SUFFIX_PATTERN.fullmatch(suffix)
            and target_name.endswith(".json")
            and RELEASE_ID_PATTERN.fullmatch(Path(target_name).stem)
        ):
            targets.add(target_name)
    return targets


def _root_control_lock(path: Path, expected_uid: int) -> AbstractContextManager[object]:
    return nullcontext() if fcntl is None else ProductionLock(path, expected_uid)


def _status_publication_lock(
    paths: DeployPaths, expected_uid: int
) -> AbstractContextManager[object]:
    return _root_control_lock(paths.status_dir / ".status.lock", expected_uid)


def _remove_old_statuses_locked(
    paths: DeployPaths,
    *,
    protected: set[str],
    current_release: Path,
    service_release: Callable[[], str | None],
    now_timestamp: float,
    expected_uid: int,
) -> tuple[int, int]:
    _secure_directory(paths.status_dir, stage="gc_status", expected_uid=expected_uid)
    _cleanup_atomic_write_temps(
        paths.status_dir,
        target_names=_status_atomic_target_names(
            paths.status_dir, stage="gc_status_pending"
        ),
        expected_uid=expected_uid,
        stage="gc_status_pending",
    )
    statuses: list[tuple[str, Path, dict[str, object]]] = []
    try:
        entries = tuple(paths.status_dir.iterdir())
    except OSError as error:
        raise DeployError("gc_status") from error
    for entry in entries:
        if entry.name in {".start.lock", ".status.lock"}:
            continue
        if entry.is_symlink() or entry.suffix != ".json":
            raise DeployError("gc_status")
        release_id = entry.stem
        status_value = report_deployment_status(
            paths,
            expected_release_id=release_id,
            expected_uid=expected_uid,
            require_root=False,
        )
        statuses.append((release_id, entry, status_value))
    active_owner = (
        service_release()
        if any(value["state"] in {"queued", "running"} for _, _, value in statuses)
        else None
    )
    current_source = _release_source_sha(current_release, expected_uid)
    terminal: list[tuple[float, str, Path]] = []
    reconciled = 0
    for release_id, entry, status_value in statuses:
        updated = _record_time(status_value, "updated_at")
        if status_value["state"] in {"queued", "running"}:
            if release_id == active_owner:
                continue
            if now_timestamp - updated < GC_ABANDONED_MIN_AGE_SECONDS:
                continue
            accepted_current = (
                release_id == current_release.name
                and status_value["source_commit"] == current_source
            )
            status_value = _write_status_locked(
                paths,
                release_id=release_id,
                source_commit=str(status_value["source_commit"]),
                state="pass" if accepted_current else "fail",
                stage="complete" if accepted_current else "abandoned",
                expected_uid=expected_uid,
            )
            updated = _record_time(status_value, "updated_at")
            reconciled += 1
        terminal.append((updated, release_id, entry))
    terminal.sort(reverse=True)
    retained = {release_id for _time, release_id, _path in terminal[:GC_AUDIT_RECORDS]}
    removed = 0
    for updated, release_id, entry in terminal[GC_AUDIT_RECORDS:]:
        if (
            release_id in protected
            or release_id in retained
            or now_timestamp - updated < GC_STATUS_MIN_AGE_SECONDS
        ):
            continue
        try:
            entry.unlink()
            _fsync_directory(paths.status_dir)
        except OSError as error:
            raise DeployError("gc_status") from error
        removed += 1
    return removed, reconciled


def _remove_old_statuses(
    paths: DeployPaths,
    *,
    protected: set[str],
    current_release: Path,
    service_release: Callable[[], str | None],
    now_timestamp: float,
    expected_uid: int,
) -> tuple[int, int]:
    with _status_publication_lock(paths, expected_uid):
        return _remove_old_statuses_locked(
            paths,
            protected=protected,
            current_release=current_release,
            service_release=service_release,
            now_timestamp=now_timestamp,
            expected_uid=expected_uid,
        )


def _remove_abandoned_payloads(
    paths: DeployPaths,
    *,
    now_timestamp: float,
    expected_uid: int,
) -> tuple[int, int]:
    removed_jobs = 0
    removed_incoming = 0
    candidates: list[tuple[Path, Path, int, set[str], str, bool]] = []
    for root, owner, stage, is_job in (
        (paths.jobs_dir, expected_uid, "gc_job", True),
        (paths.incoming_root, None, "gc_incoming", False),
    ):
        _secure_directory(root, stage=stage, expected_uid=owner)
        root_owner = _lstat(root, stage=stage).st_uid
        try:
            entries = tuple(root.iterdir())
        except OSError as error:
            raise DeployError(stage) from error
        if len(entries) > 10000:
            raise DeployError(stage)
        for entry in entries:
            info = _lstat(entry, stage=stage)
            if entry.is_symlink() or not stat.S_ISDIR(info.st_mode):
                raise DeployError(stage)
            temporary_match = (
                TEMPORARY_JOB_PATTERN.fullmatch(entry.name) if is_job else None
            )
            release_id = (
                temporary_match.group("release_id")
                if temporary_match is not None
                else entry.name
            )
            if not RELEASE_ID_PATTERN.fullmatch(release_id) or (
                is_job and entry.name.startswith(".job-") and temporary_match is None
            ):
                raise DeployError(stage)
            if now_timestamp - info.st_mtime < GC_ABANDONED_MIN_AGE_SECONDS:
                continue
            status_path = _status_path(paths, release_id)
            if status_path.exists() or status_path.is_symlink():
                status_value = report_deployment_status(
                    paths,
                    expected_release_id=release_id,
                    expected_uid=expected_uid,
                    require_root=False,
                )
                if status_value["state"] in {"queued", "running"}:
                    continue
            expected_names = {
                f"{release_id}{JOB_BUNDLE_SUFFIX}",
                f"{release_id}{JOB_MANIFEST_SUFFIX}",
                f"{release_id}{JOB_CHECKSUM_SUFFIX}",
            }
            entry_owner = expected_uid if is_job else root_owner
            _validate_flat_payload(
                entry,
                parent=root,
                expected_uid=entry_owner,
                expected_names=expected_names,
                stage=stage,
            )
            candidates.append((entry, root, entry_owner, expected_names, stage, is_job))
    for entry, root, entry_owner, expected_names, stage, is_job in candidates:
        _safe_remove_flat_payload(
            entry,
            parent=root,
            expected_uid=entry_owner,
            expected_names=expected_names,
            stage=stage,
        )
        if is_job:
            removed_jobs += 1
        else:
            removed_incoming += 1
    return removed_jobs, removed_incoming


def garbage_collect(
    paths: DeployPaths,
    *,
    runner: CommandRunner | None = None,
    expected_uid: int = 0,
    require_root: bool = True,
    lock_factory: Callable[[], AbstractContextManager[object]] | None = None,
    service_release: Callable[[], str | None] | None = None,
    now_timestamp: float | None = None,
    disk_usage: Callable[[Path], object] = shutil.disk_usage,
) -> dict[str, object]:
    _reject_sudo_internal_mode("gc_invocation")
    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    acquire_lock = lock_factory or (
        lambda: RetryingProductionLock(paths.lock_file, expected_uid)
    )
    command_runner = runner or CommandRunner()
    timestamp = now_timestamp if now_timestamp is not None else time.time()
    with acquire_lock():
        _cleanup_transaction_metadata_pending(paths, expected_uid)
        _cleanup_transaction_tombstone(paths, expected_uid)
        _assert_no_incomplete_transaction(paths)
        usage_before = disk_usage(paths.current_link.parent)
        low_disk_before = int(getattr(usage_before, "free")) < GC_MIN_FREE_BYTES
        for directory in (
            paths.releases_dir,
            paths.history_dir,
            paths.attempts_dir,
            paths.status_dir,
            paths.jobs_dir,
            paths.current_link.parent,
        ):
            _secure_directory(directory, stage="gc_control", expected_uid=expected_uid)
        _cleanup_runtime_atomic_temps(paths, expected_uid)
        current_release, _target = _current_release(paths, expected_uid)
        public_runtime = _secure_read_bytes(
            paths.public_runtime,
            stage="gc_runtime",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=MAX_RECORD_BYTES,
        )
        private_runtime = _secure_read_bytes(
            paths.private_runtime,
            stage="gc_runtime",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=MAX_RECORD_BYTES,
        )
        _validate_accepted_current(
            paths, current_release, public_runtime, private_runtime, expected_uid
        )
        records = _scan_accepted_records(paths, expected_uid)
        attempt_records = _scan_attempt_records(paths, expected_uid)
        protected: list[str] = []
        cursor: str | None = current_release.name
        while cursor is not None and len(protected) < 3:
            if cursor in protected or cursor not in records:
                raise DeployError("gc_chain")
            record = records[cursor]
            _validate_accepted_release_snapshot(paths, cursor, record, expected_uid)
            protected.append(cursor)
            previous = record["previous_release"]
            cursor = str(previous) if previous is not None else None
        protected_set = set(protected)

        accepted_order = sorted(
            records,
            key=lambda release_id: _record_time(records[release_id], "accepted_at"),
            reverse=True,
        )
        audit_records = set(accepted_order[:GC_AUDIT_RECORDS]) | protected_set
        (
            release_directories,
            release_tombstones,
            orphan_releases,
        ) = _release_cleanup_candidates(
            paths,
            records=records,
            protected=protected_set,
            now_timestamp=timestamp,
            expected_uid=expected_uid,
        )

        retained_app_refs = {
            _canonical_local_image_reference(
                str(records[release_id]["effective_runtime_references"][component])
            )
            for release_id in protected_set
            for component in APPLICATION_ARTIFACTS
        }
        retained_app_digests = {_digest(reference) for reference in retained_app_refs}
        accepted_app_refs = {
            release_id: {
                _canonical_local_image_reference(
                    str(record["effective_runtime_references"][component])
                )
                for component in APPLICATION_ARTIFACTS
            }
            for release_id, record in records.items()
            if release_id not in protected_set
        }
        attempt_app_refs = {
            release_id: {
                _canonical_local_image_reference(
                    str(record["application_references"][component])
                )
                for component in APPLICATION_ARTIFACTS
            }
            for release_id, record in attempt_records.items()
        }
        accepted_stale_refs = {
            reference
            for references in accepted_app_refs.values()
            for reference in references
        } - retained_app_refs
        attempt_stale_refs = {
            reference
            for references in attempt_app_refs.values()
            for reference in references
            if _digest(reference) not in retained_app_digests
        }
        stale_app_refs = accepted_stale_refs | attempt_stale_refs
        local_stale_refs = _local_stale_application_references(
            command_runner, stale_app_refs
        )
        _remove_application_images(command_runner, local_stale_refs)
        # Protected/shared-digest refs need no removal. Once every remaining
        # exact ref is absent or removed, the entire attempt has been accounted
        # for and must not pin ledger capacity.
        consumed_attempts = set(attempt_records)
        _remove_attempt_records(paths, consumed_attempts, expected_uid)

        for tombstone in release_tombstones:
            _safe_remove_root_tree(
                tombstone,
                parent=paths.releases_dir,
                expected_uid=expected_uid,
                stage="gc_release_tombstone",
            )
        for release_path in release_directories:
            _remove_release_tree_crash_consistent(
                paths,
                release_path,
                expected_uid,
            )
        removed_history = 0
        for release_id in set(records) - audit_records:
            history_path = paths.history_dir / f"{release_id}.json"
            try:
                history_path.unlink()
                _fsync_directory(paths.history_dir)
            except OSError as error:
                raise DeployError("gc_history_remove") from error
            removed_history += 1
        with _root_control_lock(paths.status_dir / ".start.lock", expected_uid):
            removed_status, reconciled_status = _remove_old_statuses(
                paths,
                protected=protected_set,
                current_release=current_release,
                service_release=service_release or _transient_service_release,
                now_timestamp=timestamp,
                expected_uid=expected_uid,
            )
            removed_jobs, removed_incoming = _remove_abandoned_payloads(
                paths,
                now_timestamp=timestamp,
                expected_uid=expected_uid,
            )
        usage = disk_usage(paths.current_link.parent)
        free_bytes = int(getattr(usage, "free"))
        if free_bytes < GC_MIN_FREE_BYTES:
            raise DeployError("low_disk")
        return {
            "event": "release.gc",
            "status": "pass",
            "protected_releases": protected,
            "removed_release_directories": len(release_directories),
            "completed_release_tombstones": len(release_tombstones),
            "removed_orphan_release_directories": len(orphan_releases),
            "removed_attempt_records": len(consumed_attempts),
            "removed_history_records": removed_history,
            "removed_status_records": removed_status,
            "reconciled_abandoned_statuses": reconciled_status,
            "removed_jobs": removed_jobs,
            "removed_incoming": removed_incoming,
            "removed_application_images": len(local_stale_refs),
            "low_disk_before": low_disk_before,
        }


def _status_path(paths: DeployPaths, release_id: str) -> Path:
    if not RELEASE_ID_PATTERN.fullmatch(release_id):
        raise DeployError("expected_release")
    return paths.status_dir / f"{release_id}.json"


def _status_payload(
    *,
    release_id: str,
    source_commit: str,
    state: str,
    stage: str | None,
    recovery_status: str | None,
) -> dict[str, object]:
    return {
        "schema_version": 1,
        "event": "release.deploy",
        "release_id": release_id,
        "source_commit": source_commit,
        "state": state,
        "stage": stage,
        "recovery_status": recovery_status,
        "updated_at": _utc_now(),
    }


def _validate_status(value: object, expected_release_id: str) -> dict[str, object]:
    if not isinstance(value, dict) or set(value) != STATUS_KEYS:
        raise DeployError("status")
    if (
        value.get("schema_version") != 1
        or isinstance(value.get("schema_version"), bool)
        or value.get("event") != "release.deploy"
        or value.get("release_id") != expected_release_id
        or value.get("state") not in {"queued", "running", "pass", "fail"}
    ):
        raise DeployError("status")
    source_commit = value.get("source_commit")
    if not isinstance(source_commit, str) or not SOURCE_COMMIT_PATTERN.fullmatch(
        source_commit
    ):
        raise DeployError("status")
    stage = value.get("stage")
    recovery_status = value.get("recovery_status")
    if stage is not None and (
        not isinstance(stage, str) or not re.fullmatch(r"[a-z0-9_]{1,64}", stage)
    ):
        raise DeployError("status")
    if recovery_status not in {None, "completed", "failed"}:
        raise DeployError("status")
    updated_at = value.get("updated_at")
    try:
        updated = datetime.fromisoformat(updated_at)  # type: ignore[arg-type]
    except (TypeError, ValueError) as error:
        raise DeployError("status") from error
    if updated.tzinfo is None:
        raise DeployError("status")
    return value


def _write_status_locked(
    paths: DeployPaths,
    *,
    release_id: str,
    source_commit: str,
    state: str,
    stage: str | None = None,
    recovery_status: str | None = None,
    expected_uid: int = 0,
) -> dict[str, object]:
    _secure_directory(paths.status_dir, stage="status", expected_uid=expected_uid)
    payload = _status_payload(
        release_id=release_id,
        source_commit=source_commit,
        state=state,
        stage=stage,
        recovery_status=recovery_status,
    )
    _validate_status(payload, release_id)
    status_path = _status_path(paths, release_id)
    _cleanup_atomic_write_temps(
        paths.status_dir,
        target_names={status_path.name},
        expected_uid=expected_uid,
        stage="status_pending",
    )
    _atomic_write(
        status_path,
        (json.dumps(payload, sort_keys=True) + "\n").encode(),
        0o600,
    )
    return payload


def _write_status(
    paths: DeployPaths,
    *,
    release_id: str,
    source_commit: str,
    state: str,
    stage: str | None = None,
    recovery_status: str | None = None,
    expected_uid: int = 0,
) -> dict[str, object]:
    with _status_publication_lock(paths, expected_uid):
        return _write_status_locked(
            paths,
            release_id=release_id,
            source_commit=source_commit,
            state=state,
            stage=stage,
            recovery_status=recovery_status,
            expected_uid=expected_uid,
        )


def report_deployment_status(
    paths: DeployPaths,
    *,
    expected_release_id: str,
    expected_uid: int = 0,
    require_root: bool = True,
) -> dict[str, object]:
    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    _secure_directory(paths.status_dir, stage="status", expected_uid=expected_uid)
    content = _secure_read_bytes(
        _status_path(paths, expected_release_id),
        stage="status",
        expected_uid=expected_uid,
        sensitive=True,
        maximum_bytes=MAX_RECORD_BYTES,
    )
    return _validate_status(_json_record(content, stage="status"), expected_release_id)


def _job_paths(paths: DeployPaths, release_id: str) -> tuple[Path, Path, Path]:
    job = paths.jobs_dir / release_id
    return (
        job / f"{release_id}{JOB_BUNDLE_SUFFIX}",
        job / f"{release_id}{JOB_MANIFEST_SUFFIX}",
        job / f"{release_id}{JOB_CHECKSUM_SUFFIX}",
    )


def _remove_job(paths: DeployPaths, release_id: str, expected_uid: int) -> None:
    job = paths.jobs_dir / release_id
    try:
        resolved_jobs = paths.jobs_dir.resolve(strict=True)
        resolved_parent = job.parent.resolve(strict=True)
    except OSError as error:
        raise DeployError("job_cleanup") from error
    if job.name != release_id or resolved_parent != resolved_jobs or job.is_symlink():
        raise DeployError("job_cleanup")
    _secure_directory(job, stage="job_cleanup", expected_uid=expected_uid)
    expected_names = {path.name for path in _job_paths(paths, release_id)}
    try:
        if {entry.name for entry in job.iterdir()} != expected_names:
            raise DeployError("job_cleanup")
        for path in _job_paths(paths, release_id):
            _secure_regular_file(
                path,
                stage="job_cleanup",
                expected_uid=expected_uid,
                sensitive=True,
            )
            path.unlink()
        job.rmdir()
        _fsync_directory(paths.jobs_dir)
    except OSError as error:
        raise DeployError("job_cleanup") from error


def _stage_job(
    paths: DeployPaths,
    *,
    bundle: Path,
    manifest: Path,
    checksum: Path,
    expected_release_id: str,
    expected_uid: int,
) -> None:
    expected_names = (
        f"{expected_release_id}{JOB_BUNDLE_SUFFIX}",
        f"{expected_release_id}{JOB_MANIFEST_SUFFIX}",
        f"{expected_release_id}{JOB_CHECKSUM_SUFFIX}",
    )
    if (bundle.name, manifest.name, checksum.name) != expected_names:
        raise DeployError("incoming")
    validator = Deployer(paths, expected_uid=expected_uid, require_root=False)
    validator._control_preflight(bundle, manifest, checksum, expected_release_id)
    incoming_uid = paths.incoming_root.stat().st_uid
    contents = (
        _secure_read_bytes(
            bundle,
            stage="incoming",
            expected_uid=incoming_uid,
            sensitive=True,
            maximum_bytes=MAX_ARCHIVE_BYTES * 2,
        ),
        _secure_read_bytes(
            manifest,
            stage="incoming",
            expected_uid=incoming_uid,
            sensitive=True,
            maximum_bytes=MAX_MANIFEST_BYTES,
        ),
        _secure_read_bytes(
            checksum,
            stage="incoming",
            expected_uid=incoming_uid,
            sensitive=True,
            maximum_bytes=1024,
        ),
    )
    _secure_directory(paths.jobs_dir, stage="job", expected_uid=expected_uid)
    final = paths.jobs_dir / expected_release_id
    temporary = paths.jobs_dir / f".job-{expected_release_id}-{os.getpid()}"
    if final.exists() or final.is_symlink() or temporary.exists():
        raise DeployError("job_reuse")
    promoted = False
    try:
        temporary.mkdir(mode=0o700)
        os.chmod(temporary, 0o700)
        for target, content in zip(
            (
                temporary / expected_names[0],
                temporary / expected_names[1],
                temporary / expected_names[2],
            ),
            contents,
            strict=True,
        ):
            _exclusive_write(target, content, 0o600)
        _fsync_directory(temporary)
        os.replace(temporary, final)
        _fsync_directory(paths.jobs_dir)
        promoted = True
    finally:
        if not promoted:
            shutil.rmtree(temporary, ignore_errors=True)


def _launch_transient_service(
    *,
    expected_current_source_sha: str,
    expected_source_sha: str,
    expected_release_id: str,
) -> None:
    command = [
        str(SYSTEMD_RUN_PATH),
        "--quiet",
        "--collect",
        "--no-block",
        f"--unit={SYSTEMD_UNIT}",
        "--property=Type=exec",
        "--property=User=root",
        "--property=Group=root",
        "--property=UMask=0077",
        "--property=Restart=on-failure",
        "--property=RestartSec=5s",
        "--property=RuntimeMaxSec=3h",
        "--property=TimeoutStopSec=30min",
        "--property=RefuseManualStop=yes",
        "--property=NoNewPrivileges=yes",
        "--property=PrivateTmp=yes",
        "--property=ProtectSystem=full",
        "--property=ReadWritePaths=/opt/aperture -/var/lib/aperture",
        str(CONTROLLER_PATH),
        "--worker",
        "--expected-current-source-sha",
        expected_current_source_sha,
        "--expected-source-sha",
        expected_source_sha,
        "--expected-release-id",
        expected_release_id,
    ]
    try:
        completed = subprocess.run(
            command,
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DeployError("service_start") from error
    if completed.returncode != 0:
        raise DeployError("service_start")


def _transient_service_release() -> str | None:
    """Return the release owned by the fixed transient unit, if it is active."""

    try:
        completed = subprocess.run(
            [
                str(SYSTEMCTL_PATH),
                "show",
                f"{SYSTEMD_UNIT}.service",
                "--property=LoadState",
                "--property=ActiveState",
                "--property=ExecStart",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DeployError("service_status") from error
    if len(completed.stdout) > 65536:
        raise DeployError("service_status")
    properties: dict[str, str] = {}
    for line in completed.stdout.splitlines():
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key in properties or key not in {"LoadState", "ActiveState", "ExecStart"}:
            raise DeployError("service_status")
        properties[key] = value
    load_state = properties.get("LoadState")
    if load_state == "not-found":
        return None
    if completed.returncode != 0 or load_state != "loaded":
        raise DeployError("service_status")
    active_state = properties.get("ActiveState")
    if active_state in {"inactive", "failed"}:
        return None
    if active_state not in {"active", "activating", "reloading", "deactivating"}:
        raise DeployError("service_status")
    exec_start = properties.get("ExecStart")
    if exec_start is None:
        raise DeployError("service_status")
    match = re.search(
        r"(?:^|\s)--expected-release-id(?:=|\s+)([a-z0-9][a-z0-9._-]*)(?:\s|;|$)",
        exec_start,
    )
    if match is None:
        raise DeployError("service_status")
    return match.group(1)


def _start_boot_recovery_service() -> None:
    try:
        completed = subprocess.run(
            [
                str(SYSTEMCTL_PATH),
                "start",
                "--no-block",
                "aperture-deploy-recovery.service",
            ],
            check=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise DeployError("recovery_service_start") from error
    if completed.returncode != 0:
        raise DeployError("recovery_service_start")


def _validate_staged_job(
    paths: DeployPaths, release_id: str, expected_uid: int
) -> None:
    job = paths.jobs_dir / release_id
    _secure_directory(job, stage="job", expected_uid=expected_uid)
    if os.name != "nt" and stat.S_IMODE(job.stat().st_mode) != 0o700:
        raise DeployError("job")
    bundle, manifest, checksum = _job_paths(paths, release_id)
    for path, maximum in (
        (bundle, MAX_ARCHIVE_BYTES * 2),
        (manifest, MAX_MANIFEST_BYTES),
        (checksum, 1024),
    ):
        _secure_regular_file(
            path,
            stage="job",
            expected_uid=expected_uid,
            sensitive=True,
            maximum_bytes=maximum,
        )
    try:
        names = {entry.name for entry in job.iterdir()}
    except OSError as error:
        raise DeployError("job") from error
    if names != {bundle.name, manifest.name, checksum.name}:
        raise DeployError("job")


def start_deployment(
    paths: DeployPaths,
    *,
    bundle: Path,
    manifest: Path,
    checksum: Path,
    expected_current_source_sha: str,
    expected_source_sha: str,
    expected_release_id: str,
    expected_uid: int = 0,
    require_root: bool = True,
) -> dict[str, object]:
    """Serialize idempotent public submissions without touching worker state."""

    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    if not SOURCE_COMMIT_PATTERN.fullmatch(expected_current_source_sha):
        raise DeployError("expected_current_source")
    if not SOURCE_COMMIT_PATTERN.fullmatch(expected_source_sha):
        raise DeployError("expected_source")
    if not RELEASE_ID_PATTERN.fullmatch(expected_release_id):
        raise DeployError("expected_release")
    start_lock = _root_control_lock(paths.status_dir / ".start.lock", expected_uid)
    with start_lock:
        return _start_deployment_locked(
            paths,
            bundle=bundle,
            manifest=manifest,
            checksum=checksum,
            expected_current_source_sha=expected_current_source_sha,
            expected_source_sha=expected_source_sha,
            expected_release_id=expected_release_id,
            expected_uid=expected_uid,
            require_root=False,
        )


def _transaction_recovery_needed(paths: DeployPaths) -> bool:
    if _transaction_exists(paths):
        return True
    for path in (
        _transaction_metadata_pending(paths),
        _transaction_tombstone(paths),
    ):
        try:
            path.lstat()
        except FileNotFoundError:
            continue
        except OSError as error:
            raise DeployError("incomplete_transaction") from error
        return True
    return False


def _start_deployment_locked(
    paths: DeployPaths,
    *,
    bundle: Path,
    manifest: Path,
    checksum: Path,
    expected_current_source_sha: str,
    expected_source_sha: str,
    expected_release_id: str,
    expected_uid: int = 0,
    require_root: bool = True,
) -> dict[str, object]:
    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    if not SOURCE_COMMIT_PATTERN.fullmatch(expected_current_source_sha):
        raise DeployError("expected_current_source")
    if not SOURCE_COMMIT_PATTERN.fullmatch(expected_source_sha):
        raise DeployError("expected_source")
    if not RELEASE_ID_PATTERN.fullmatch(expected_release_id):
        raise DeployError("expected_release")
    status_path = _status_path(paths, expected_release_id)
    job_path = paths.jobs_dir / expected_release_id
    if status_path.exists() or status_path.is_symlink():
        existing = report_deployment_status(
            paths,
            expected_release_id=expected_release_id,
            expected_uid=expected_uid,
            require_root=False,
        )
        if existing["source_commit"] != expected_source_sha:
            raise DeployError("status")
        service_release = _transient_service_release()
        if _transaction_recovery_needed(paths):
            if service_release is None:
                _start_boot_recovery_service()
            elif service_release != expected_release_id:
                raise DeployError("service_busy")
            raise DeployError("recovery_pending")
        if existing["state"] in {"pass", "fail"}:
            return existing
        if service_release == expected_release_id:
            return existing
        if service_release is not None:
            raise DeployError("service_busy")
        latest = report_deployment_status(
            paths,
            expected_release_id=expected_release_id,
            expected_uid=expected_uid,
            require_root=False,
        )
        if latest["state"] in {"pass", "fail"}:
            return latest
        _validate_staged_job(paths, expected_release_id, expected_uid)
        try:
            _launch_transient_service(
                expected_current_source_sha=expected_current_source_sha,
                expected_source_sha=expected_source_sha,
                expected_release_id=expected_release_id,
            )
        except Exception:
            if _transient_service_release() == expected_release_id:
                return existing
            latest = report_deployment_status(
                paths,
                expected_release_id=expected_release_id,
                expected_uid=expected_uid,
                require_root=False,
            )
            if latest["state"] in {"pass", "fail"}:
                return latest
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="fail",
                stage="service_start",
                expected_uid=expected_uid,
            )
            raise
        return existing
    service_release = _transient_service_release()
    if service_release is not None and service_release != expected_release_id:
        raise DeployError("service_busy")
    if _transaction_recovery_needed(paths):
        _start_boot_recovery_service()
        raise DeployError("recovery_pending")
    if job_path.exists() or job_path.is_symlink():
        _validate_staged_job(paths, expected_release_id, expected_uid)
    else:
        _stage_job(
            paths,
            bundle=bundle,
            manifest=manifest,
            checksum=checksum,
            expected_release_id=expected_release_id,
            expected_uid=expected_uid,
        )
    queued = _write_status(
        paths,
        release_id=expected_release_id,
        source_commit=expected_source_sha,
        state="queued",
        expected_uid=expected_uid,
    )
    try:
        if service_release != expected_release_id:
            _launch_transient_service(
                expected_current_source_sha=expected_current_source_sha,
                expected_source_sha=expected_source_sha,
                expected_release_id=expected_release_id,
            )
    except Exception:
        if _transient_service_release() == expected_release_id:
            return queued
        latest = report_deployment_status(
            paths,
            expected_release_id=expected_release_id,
            expected_uid=expected_uid,
            require_root=False,
        )
        if latest["state"] in {"pass", "fail"}:
            return latest
        _write_status(
            paths,
            release_id=expected_release_id,
            source_commit=expected_source_sha,
            state="fail",
            stage="service_start",
            expected_uid=expected_uid,
        )
        _remove_job(paths, expected_release_id, expected_uid)
        raise
    return queued


def _reject_sudo_internal_mode(stage: str) -> None:
    if any(
        os.environ.get(name)
        for name in ("SUDO_USER", "SUDO_UID", "SUDO_GID", "SUDO_COMMAND")
    ):
        raise DeployError(stage)


def _cleanup_job_if_present(
    paths: DeployPaths, release_id: str, expected_uid: int
) -> None:
    job = paths.jobs_dir / release_id
    if job.exists() or job.is_symlink():
        _remove_job(paths, release_id, expected_uid)


def run_boot_recovery(
    paths: DeployPaths,
    *,
    expected_uid: int = 0,
    require_root: bool = True,
) -> int:
    """Recover a journal left across reboot and publish its terminal status."""

    _reject_sudo_internal_mode("recovery_invocation")
    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    controller = Deployer(
        paths,
        expected_uid=expected_uid,
        require_root=require_root,
        lock_factory=lambda: nullcontext(),
    )
    recovery_lock: AbstractContextManager[object] = (
        nullcontext()
        if fcntl is None
        else RetryingProductionLock(paths.lock_file, expected_uid)
    )
    with recovery_lock:
        # Recheck only after owning the same lock as deploy, backup, and GC.
        # A live worker may be between writing and publishing journal metadata.
        _cleanup_transaction_metadata_pending(paths, expected_uid)
        _cleanup_transaction_tombstone(paths, expected_uid)
        if not _transaction_exists(paths):
            return 0
        metadata, _old_public, _old_private = _load_transaction(paths, expected_uid)
        release_id = str(metadata["release_id"])
        source_commit = str(metadata["source_commit"])
        _write_status(
            paths,
            release_id=release_id,
            source_commit=source_commit,
            state="running",
            stage="recovery",
            expected_uid=expected_uid,
        )
        try:
            controller._recover_incomplete_transaction_locked(remove_journal=False)
            _write_status(
                paths,
                release_id=release_id,
                source_commit=source_commit,
                state="fail",
                stage="interrupted_transaction",
                recovery_status="completed",
                expected_uid=expected_uid,
            )
            _cleanup_job_if_present(paths, release_id, expected_uid)
            _remove_transaction(paths, expected_uid)
        except DeploymentExecutionError:
            _write_status(
                paths,
                release_id=release_id,
                source_commit=source_commit,
                state="running",
                stage="recovery",
                recovery_status="failed",
                expected_uid=expected_uid,
            )
            raise
        except Exception:
            _write_status(
                paths,
                release_id=release_id,
                source_commit=source_commit,
                state="running",
                stage="recovery",
                recovery_status="failed",
                expected_uid=expected_uid,
            )
            raise
    return 0


def run_deployment_worker(
    paths: DeployPaths,
    *,
    expected_current_source_sha: str,
    expected_source_sha: str,
    expected_release_id: str,
    expected_uid: int = 0,
    require_root: bool = True,
) -> int:
    # The deploy account may sudo the public controller modes, but never either
    # internal foreground service mode. systemd's root ExecStart has no sudo
    # provenance and owns the process independently of the SSH session.
    _reject_sudo_internal_mode("worker_invocation")
    if require_root and _effective_uid() != 0:
        raise DeployError("root")
    existing = report_deployment_status(
        paths,
        expected_release_id=expected_release_id,
        expected_uid=expected_uid,
        require_root=False,
    )
    if existing["source_commit"] != expected_source_sha:
        raise DeployError("status")
    if existing["state"] in {"pass", "fail"} and not _transaction_exists(paths):
        _cleanup_job_if_present(paths, expected_release_id, expected_uid)
        return 0
    _write_status(
        paths,
        release_id=expected_release_id,
        source_commit=expected_source_sha,
        state="running",
        stage="recovery" if _transaction_exists(paths) else "deploy",
        expected_uid=expected_uid,
    )
    controller = Deployer(
        paths,
        expected_uid=expected_uid,
        require_root=require_root,
        input_root=paths.jobs_dir,
        input_owner_uid=expected_uid,
        lock_factory=lambda: RetryingProductionLock(paths.lock_file, expected_uid),
    )
    accepted_live = False
    try:
        if _transaction_exists(paths):
            recovered = controller.recover_incomplete_transaction()
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="fail",
                stage=str(recovered["stage"]),
                recovery_status="completed",
                expected_uid=expected_uid,
            )
        else:
            bundle, manifest, checksum = _job_paths(paths, expected_release_id)
            current_release, _current_target = _current_release(paths, expected_uid)
            if current_release.name == expected_release_id:
                public_runtime = _secure_read_bytes(
                    paths.public_runtime,
                    stage="runtime",
                    expected_uid=expected_uid,
                    sensitive=True,
                    maximum_bytes=MAX_RECORD_BYTES,
                )
                private_runtime = _secure_read_bytes(
                    paths.private_runtime,
                    stage="runtime",
                    expected_uid=expected_uid,
                    sensitive=True,
                    maximum_bytes=MAX_RECORD_BYTES,
                )
                accepted = _validate_accepted_current(
                    paths,
                    current_release,
                    public_runtime,
                    private_runtime,
                    expected_uid,
                )
                if accepted["source_commit"] != expected_source_sha:
                    raise DeployError("accepted_record")
            else:
                controller.deploy(
                    bundle=bundle,
                    manifest=manifest,
                    checksum=checksum,
                    expected_current_source_sha=expected_current_source_sha,
                    expected_source_sha=expected_source_sha,
                    expected_release_id=expected_release_id,
                )
            accepted_live = True
    except DeploymentExecutionError as error:
        if _transaction_exists(paths):
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="running",
                stage="recovery",
                recovery_status="failed",
                expected_uid=expected_uid,
            )
            raise
        _write_status(
            paths,
            release_id=expected_release_id,
            source_commit=expected_source_sha,
            state="fail",
            stage=error.stage,
            recovery_status=error.recovery_status,
            expected_uid=expected_uid,
        )
    except Exception as error:
        if _transaction_exists(paths):
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="running",
                stage="recovery",
                recovery_status="failed",
                expected_uid=expected_uid,
            )
            raise
        stage = error.stage if isinstance(error, DeployError) else "internal"
        _write_status(
            paths,
            release_id=expected_release_id,
            source_commit=expected_source_sha,
            state="fail",
            stage=stage,
            expected_uid=expected_uid,
        )
    else:
        if accepted_live:
            # Once current and its accepted record validate, a transient
            # publication failure is not a deployment failure. Let systemd
            # restart the worker and retry this idempotent terminal write.
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="pass",
                stage="complete",
                expected_uid=expected_uid,
            )
    finally:
        try:
            _cleanup_job_if_present(paths, expected_release_id, expected_uid)
        except Exception:
            if accepted_live:
                raise
            current = report_deployment_status(
                paths,
                expected_release_id=expected_release_id,
                expected_uid=expected_uid,
                require_root=False,
            )
            _write_status(
                paths,
                release_id=expected_release_id,
                source_commit=expected_source_sha,
                state="fail",
                stage="job_cleanup",
                recovery_status=current["recovery_status"],
                expected_uid=expected_uid,
            )
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--report-current-source-sha", action="store_true")
    mode.add_argument("--start", action="store_true")
    mode.add_argument("--status", action="store_true")
    mode.add_argument("--worker", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--recover", action="store_true", help=argparse.SUPPRESS)
    mode.add_argument("--gc", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--checksum", type=Path)
    parser.add_argument("--expected-current-source-sha")
    parser.add_argument("--expected-source-sha")
    parser.add_argument("--expected-release-id")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    deployment_values = (
        args.bundle,
        args.manifest,
        args.checksum,
        args.expected_current_source_sha,
        args.expected_source_sha,
        args.expected_release_id,
    )
    if args.report_current_source_sha or args.recover or args.gc:
        if any(value is not None for value in deployment_values):
            parser.error("this mode cannot be combined with deployment arguments")
    elif args.status:
        if args.expected_release_id is None or any(
            value is not None
            for value in (
                args.bundle,
                args.manifest,
                args.checksum,
                args.expected_current_source_sha,
                args.expected_source_sha,
            )
        ):
            parser.error("status requires only --expected-release-id")
    elif args.worker:
        if any(
            value is not None for value in (args.bundle, args.manifest, args.checksum)
        ) or any(
            value is None
            for value in (
                args.expected_current_source_sha,
                args.expected_source_sha,
                args.expected_release_id,
            )
        ):
            parser.error("worker requires the three expected identity arguments")
    elif any(value is None for value in deployment_values):
        parser.error("start requires all deployment arguments")
    try:
        if args.report_current_source_sha:
            result: dict[str, object] | str = report_current_source_sha(
                DeployPaths.production()
            )
        elif args.recover:
            return run_boot_recovery(DeployPaths.production())
        elif args.gc:
            result = garbage_collect(DeployPaths.production())
        elif args.status:
            result = report_deployment_status(
                DeployPaths.production(),
                expected_release_id=args.expected_release_id,
            )
        elif args.worker:
            return run_deployment_worker(
                DeployPaths.production(),
                expected_current_source_sha=args.expected_current_source_sha,
                expected_source_sha=args.expected_source_sha,
                expected_release_id=args.expected_release_id,
            )
        else:
            result = start_deployment(
                DeployPaths.production(),
                bundle=args.bundle,
                manifest=args.manifest,
                checksum=args.checksum,
                expected_current_source_sha=args.expected_current_source_sha,
                expected_source_sha=args.expected_source_sha,
                expected_release_id=args.expected_release_id,
            )
    except DeploymentExecutionError as error:
        payload: dict[str, object] = {
            "event": "release.deploy",
            "status": "fail",
            "stage": error.stage,
            "recovery_status": error.recovery_status,
        }
        if error.recovery_failure_stage is not None:
            payload["recovery_failure_stage"] = error.recovery_failure_stage
        print(json.dumps(payload, sort_keys=True), file=sys.stderr)
        return 1
    except Exception as error:
        stage = error.stage if isinstance(error, DeployError) else "internal"
        print(
            json.dumps(
                {"event": "release.deploy", "stage": stage, "status": "fail"},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1
    if isinstance(result, str):
        print(result)
    else:
        print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
