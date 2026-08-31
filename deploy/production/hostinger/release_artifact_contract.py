"""Canonical production artifact contract and release-publication helpers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

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

# These platform images are deliberately reused for routine application releases.
# Rebuilding stateful storage or ingress as a side effect of an application push
# would turn a reversible code deployment into an infrastructure migration.
INFRASTRUCTURE_ARTIFACTS = (
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

ROLLBACK_IMAGE_LABELS = {
    component: f"HOSTINGER_ROLLBACK_{label}"
    for component, label in IMAGE_LABELS.items()
}

SERVICE_BINDINGS = {
    "api": {"api", "scene-worker", "migrate", "maintenance", "preflight"},
    "media_worker": {"media-worker"},
    "web": {"web"},
    "backup": {"backup", "restore"},
    "caddy": {"caddy"},
    "storage": {"minio"},
    "node_exporter": {"node-exporter"},
    "blackbox": {"blackbox"},
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

RELEASE_ID = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
REPOSITORY = re.compile(r"^[a-z0-9][a-z0-9./_-]*$")
SOURCE_COMMIT = re.compile(r"^[0-9a-f]{40}(?:[0-9a-f]{24})?$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
ABSENT_MARKERS = (
    "manifest unknown",
    "name unknown",
    "no such manifest",
    "not found",
)
DENIAL_MARKERS = (
    "access denied",
    "authentication required",
    "denied",
    "forbidden",
    "unauthorized",
)


class ReleaseContractError(ValueError):
    """A release does not satisfy the immutable publication contract."""


def clean_source_commit(root: Path, *, git: str = "git") -> str:
    """Return HEAD only when tracked and non-ignored untracked source is clean."""
    try:
        commit_result = subprocess.run(
            [git, "-C", str(root), "rev-parse", "--verify", "HEAD^{commit}"],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        status_result = subprocess.run(
            [
                git,
                "-C",
                str(root),
                "status",
                "--porcelain=v1",
                "--untracked-files=all",
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as error:
        raise ReleaseContractError("source integrity could not be verified") from error
    commit = commit_result.stdout.strip()
    if commit_result.returncode != 0 or not SOURCE_COMMIT.fullmatch(commit):
        raise ReleaseContractError("source commit could not be verified")
    if status_result.returncode != 0:
        raise ReleaseContractError("source state could not be verified")
    if status_result.stdout:
        raise ReleaseContractError("source tree contains unpublished changes")
    return commit


def exact_mapping(
    assignments: Iterable[str], *, label: str
) -> dict[str, str]:
    """Parse a complete set of ``component=value`` command-line assignments."""
    values: dict[str, str] = {}
    for assignment in assignments:
        component, separator, value = assignment.partition("=")
        if not separator or component not in ARTIFACTS or not value:
            raise ReleaseContractError(f"invalid {label} assignment")
        if component in values:
            raise ReleaseContractError(f"duplicate {label} assignment")
        values[component] = value
    if set(values) != set(ARTIFACTS):
        raise ReleaseContractError(f"{label} must contain exactly eight artifacts")
    return values


def expected_tags(repository: str, release_id: str) -> dict[str, str]:
    if not REPOSITORY.fullmatch(repository) or "/" not in repository:
        raise ReleaseContractError("repository must be a lowercase registry path")
    if not RELEASE_ID.fullmatch(release_id) or "latest" in release_id:
        raise ReleaseContractError("release ID must be immutable and non-dummy")
    if "dummy" in release_id or "dummy" in repository:
        raise ReleaseContractError("release identity must be non-dummy")
    return {
        component: f"{repository}/{TAG_NAMES[component]}:{release_id}"
        for component in ARTIFACTS
    }


def validate_tags(
    tags: dict[str, str], *, repository: str, release_id: str
) -> None:
    expected = expected_tags(repository, release_id)
    if tags != expected:
        raise ReleaseContractError("release tags do not match the canonical contract")
    if len(set(tags.values())) != len(ARTIFACTS):
        raise ReleaseContractError("release tags must be unique")


def marker_paths(manifest_dir: Path, release_id: str) -> tuple[Path, Path]:
    if not RELEASE_ID.fullmatch(release_id):
        raise ReleaseContractError("invalid release ID")
    return (
        manifest_dir / f"{release_id}.release.json",
        manifest_dir / f"{release_id}.release.sha256",
    )


def reservation_path(manifest_dir: Path, release_id: str) -> Path:
    if not RELEASE_ID.fullmatch(release_id):
        raise ReleaseContractError("invalid release ID")
    return manifest_dir / f"{release_id}.release.reserved.json"


def reservation_record(*, repository: str, release_id: str) -> dict[str, object]:
    expected_tags(repository, release_id)
    return {
        "schema_version": 1,
        "release_id": release_id,
        "repository": repository,
        "state": "reserved",
    }


def reserve_release(
    *, manifest_dir: Path, repository: str, release_id: str
) -> Path:
    """Atomically reserve a release ID before any registry mutation."""
    record = reservation_record(repository=repository, release_id=release_id)
    manifest_path, checksum_path = marker_paths(manifest_dir, release_id)
    reservation = reservation_path(manifest_dir, release_id)
    if manifest_path.exists() or checksum_path.exists():
        raise ReleaseContractError("release ID already has a local commit marker")
    content = (
        json.dumps(record, indent=2, sort_keys=True)
        + "\n"
    ).encode()
    try:
        _exclusive_write(reservation, content)
    except FileExistsError as error:
        raise ReleaseContractError("release ID is already locally reserved") from error
    return reservation


def preflight_tags(
    tags: dict[str, str],
    *,
    repository: str,
    release_id: str,
    manifest_dir: Path,
    docker: str = "docker",
) -> None:
    """Prove all exact tags and the local commit marker are absent before building."""
    validate_tags(tags, repository=repository, release_id=release_id)
    manifest_path, checksum_path = marker_paths(manifest_dir, release_id)
    if manifest_path.exists() or checksum_path.exists():
        raise ReleaseContractError("release ID already has a local commit marker")
    reserve_release(
        manifest_dir=manifest_dir, repository=repository, release_id=release_id
    )

    reused: list[str] = []
    ambiguous: list[str] = []
    for component in ARTIFACTS:
        try:
            result = subprocess.run(
                [docker, "buildx", "imagetools", "inspect", tags[component]],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.TimeoutExpired):
            ambiguous.append(component)
            continue
        if result.returncode == 0:
            reused.append(component)
            continue
        detail = f"{result.stdout}\n{result.stderr}".lower()
        if any(marker in detail for marker in DENIAL_MARKERS) or not any(
            marker in detail for marker in ABSENT_MARKERS
        ):
            ambiguous.append(component)

    if reused:
        raise ReleaseContractError(
            "release ID is already used by registry artifacts: "
            + ", ".join(reused)
        )
    if ambiguous:
        raise ReleaseContractError(
            "registry could not prove tag absence for: " + ", ".join(ambiguous)
        )


def validate_references(
    references: dict[str, str],
    *,
    repository: str,
    release_id: str,
) -> tuple[dict[str, str], dict[str, str]]:
    tags = expected_tags(repository, release_id)
    digests: dict[str, str] = {}
    for component in ARTIFACTS:
        prefix = f"{tags[component]}@"
        reference = references[component]
        if not reference.startswith(prefix):
            raise ReleaseContractError(
                f"{component} reference does not bind its exact release tag"
            )
        digest = reference.removeprefix(prefix)
        if not DIGEST.fullmatch(digest):
            raise ReleaseContractError(f"{component} has an invalid image digest")
        digests[component] = digest
    if len(set(digests.values())) != len(ARTIFACTS):
        raise ReleaseContractError("release artifact digests must be distinct")
    return tags, digests


def validate_reuse_reference(
    component: str,
    reference: str,
    *,
    repository: str,
) -> str:
    """Validate one accepted, digest-pinned platform artifact for retagging.

    Routine CI releases may carbon-copy an already accepted infrastructure
    manifest under the new immutable release tag.  The source must remain in
    this repository, must belong to the requested component, and must identify
    an immutable tag plus an exact sha256 digest.
    """
    if component not in INFRASTRUCTURE_ARTIFACTS:
        raise ReleaseContractError("only infrastructure artifacts may be reused")
    if not REPOSITORY.fullmatch(repository) or "/" not in repository:
        raise ReleaseContractError("repository must be a lowercase registry path")

    image, separator, digest = reference.rpartition("@")
    if not separator or not DIGEST.fullmatch(digest):
        raise ReleaseContractError("reused infrastructure reference must pin a digest")
    prefix = f"{repository}/{TAG_NAMES[component]}:"
    if not image.startswith(prefix):
        raise ReleaseContractError("reused infrastructure reference has the wrong component")
    source_tag = image.removeprefix(prefix)
    if (
        not RELEASE_ID.fullmatch(source_tag)
        or "latest" in source_tag
        or "dummy" in source_tag
    ):
        raise ReleaseContractError("reused infrastructure tag must be immutable")
    return digest


def release_manifest(
    references: dict[str, str],
    *,
    repository: str,
    release_id: str,
    platform: str,
    source_commit: str,
) -> dict[str, object]:
    if platform != "linux/amd64":
        raise ReleaseContractError("release platform must be linux/amd64")
    if not SOURCE_COMMIT.fullmatch(source_commit):
        raise ReleaseContractError("source commit must be a full Git object ID")
    tags, digests = validate_references(
        references, repository=repository, release_id=release_id
    )
    artifacts = {
        component: {
            "tag": tags[component],
            "digest": digests[component],
            "reference": references[component],
        }
        for component in ARTIFACTS
    }
    runtime = {
        binding: references[component]
        for binding, component in RUNTIME_BINDINGS.items()
    }
    return {
        "schema_version": 1,
        "release_id": release_id,
        "repository": repository,
        "platform": platform,
        "source_commit": source_commit,
        "artifacts": artifacts,
        "runtime_bindings": runtime,
        "registry_attestations": {
            "provenance": "buildx-mode-max",
            "sbom": "buildx-registry-referrer",
        },
    }


def _exclusive_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
        os.chmod(temporary, 0o644)
        # A hard link publishes the fully flushed inode atomically and refuses to
        # replace an existing reservation or marker.
        os.link(temporary, path)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        temporary.unlink(missing_ok=True)


def _commit_manifest(
    manifest: dict[str, object],
    *,
    manifest_dir: Path,
    repository: str,
    release_id: str,
) -> tuple[Path, Path]:
    """Create a non-overwritable manifest and checksum marker."""
    manifest_path, checksum_path = marker_paths(manifest_dir, release_id)
    reservation = reservation_path(manifest_dir, release_id)
    if not reservation.is_file():
        raise ReleaseContractError("release ID lacks its local reservation")
    try:
        reserved = json.loads(reservation.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise ReleaseContractError("release ID has an invalid local reservation") from error
    if reserved != reservation_record(repository=repository, release_id=release_id):
        raise ReleaseContractError("release ID reservation does not match publication")
    if manifest_path.exists() or checksum_path.exists():
        raise ReleaseContractError("release ID already has a local commit marker")

    content = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode()
    checksum = hashlib.sha256(content).hexdigest()
    checksum_content = f"{checksum}  {manifest_path.name}\n".encode()

    # Validate and serialize before either final path is created. If the checksum
    # write is interrupted, the manifest still burns the release ID fail-closed.
    _exclusive_write(manifest_path, content)
    try:
        _exclusive_write(checksum_path, checksum_content)
    except Exception:
        # Never erase the immutable manifest after publication has reached this step.
        raise
    return manifest_path, checksum_path


def commit_release(
    references: dict[str, str],
    *,
    repository: str,
    release_id: str,
    platform: str,
    source_commit: str,
    manifest_dir: Path,
) -> tuple[Path, Path]:
    """Validate all eight artifacts, then create the final local commit marker."""
    if set(references) != set(ARTIFACTS):
        raise ReleaseContractError("reference must contain exactly eight artifacts")
    manifest = release_manifest(
        references,
        repository=repository,
        release_id=release_id,
        platform=platform,
        source_commit=source_commit,
    )
    return _commit_manifest(
        manifest,
        manifest_dir=manifest_dir,
        repository=repository,
        release_id=release_id,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="action", required=True)

    source = subparsers.add_parser("source-preflight")
    source.add_argument("--root", type=Path, required=True)
    source.add_argument("--git", default="git")

    preflight = subparsers.add_parser("preflight")
    preflight.add_argument("--repository", required=True)
    preflight.add_argument("--release-id", required=True)
    preflight.add_argument("--manifest-dir", type=Path, required=True)
    preflight.add_argument("--docker", default="docker")
    preflight.add_argument("--tag", action="append", default=[])

    commit = subparsers.add_parser("commit")
    commit.add_argument("--repository", required=True)
    commit.add_argument("--release-id", required=True)
    commit.add_argument("--platform", required=True)
    commit.add_argument("--source-commit", required=True)
    commit.add_argument("--manifest-dir", type=Path, required=True)
    commit.add_argument("--reference", action="append", default=[])

    reuse = subparsers.add_parser("validate-reuse")
    reuse.add_argument("--component", required=True)
    reuse.add_argument("--repository", required=True)
    reuse.add_argument("--reference", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.action == "source-preflight":
            print(clean_source_commit(args.root, git=args.git))
            return 0
        if args.action == "preflight":
            tags = exact_mapping(args.tag, label="tag")
            preflight_tags(
                tags,
                repository=args.repository,
                release_id=args.release_id,
                manifest_dir=args.manifest_dir,
                docker=args.docker,
            )
            print("Eight release tags are confirmed unused.")
            return 0
        if args.action == "validate-reuse":
            print(
                validate_reuse_reference(
                    args.component,
                    args.reference,
                    repository=args.repository,
                )
            )
            return 0

        references = exact_mapping(args.reference, label="reference")
        manifest_path, _checksum_path = commit_release(
            references,
            repository=args.repository,
            release_id=args.release_id,
            platform=args.platform,
            source_commit=args.source_commit,
            manifest_dir=args.manifest_dir,
        )
        print(f"Release commit marker written: {manifest_path}")
        return 0
    except Exception:
        # Registry responses and image references are intentionally omitted.
        print("Release artifact contract failed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
