import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
PRODUCTION_ROOT = ROOT.parent
BUILD_SCRIPT = ROOT / "build_release.sh"
sys.path.insert(0, str(ROOT))

import hostinger_rollback as rollback  # noqa: E402
import pin_release as pinning  # noqa: E402
import prepare_vps_env as prepare  # noqa: E402
import release_artifact_contract as contract  # noqa: E402
import validate_config as config  # noqa: E402
import validate_topology as topology  # noqa: E402


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


launch_evidence = load_module(
    "release_contract_launch_evidence", PRODUCTION_ROOT / "launch_evidence.py"
)


def references(repository: str, release_id: str) -> dict[str, str]:
    tags = contract.expected_tags(repository, release_id)
    return {
        component: f"{tags[component]}@sha256:{index:064x}"
        for index, component in enumerate(contract.ARTIFACTS, start=1)
    }


def test_one_canonical_contract_covers_every_release_consumer():
    labels = contract.IMAGE_LABELS
    assert pinning.LABELS == labels
    assert rollback.IMAGE_KEYS == labels
    assert rollback.TARGET_KEYS == contract.ROLLBACK_IMAGE_LABELS
    assert tuple(labels.values()) == config.IMAGE_LABELS
    assert topology.ARTIFACT_IMAGE_SERVICES == contract.SERVICE_BINDINGS
    assert topology.RELEASE_SERVICES == set().union(*contract.SERVICE_BINDINGS.values())
    assert {
        label for label in prepare.COMPOSE_RUNTIME_LABELS if label.endswith("_IMAGE")
    } == set(labels.values())

    digests = {
        component: f"sha256:{index:064x}"
        for index, component in enumerate(contract.ARTIFACTS, start=1)
    }
    runtime_digests = {
        binding: digests[component]
        for binding, component in contract.RUNTIME_BINDINGS.items()
    }
    assert set(runtime_digests) == {
        "api",
        "media_worker",
        "scene_worker",
        "web",
        "backup",
        "caddy",
        "storage",
        "node_exporter",
        "blackbox",
    }
    assert runtime_digests["scene_worker"] == runtime_digests["api"]
    launch_evidence.validate_release(
        {
            "release": {
                "id": "release-contract-test",
                "infrastructure_version": "test-commit",
                "deployed_at": datetime.now(UTC).isoformat(),
                "migration_head": launch_evidence.MIGRATION_HEAD,
                "image_digests": runtime_digests,
            }
        },
        dummy=False,
    )


def test_commit_marker_requires_all_eight_distinct_valid_references(tmp_path: Path):
    repository = "registry.example/aperture"
    release_id = "release-123"
    valid = references(repository, release_id)
    invalid = dict(valid)
    invalid.pop("blackbox")
    contract.reserve_release(
        manifest_dir=tmp_path, repository=repository, release_id=release_id
    )

    with pytest.raises(contract.ReleaseContractError, match="exactly eight"):
        contract.commit_release(
            invalid,
            repository=repository,
            release_id=release_id,
            platform="linux/amd64",
            source_commit="a" * 40,
            manifest_dir=tmp_path,
        )
    assert not list(tmp_path.glob("*.release.json"))
    assert not list(tmp_path.glob("*.release.sha256"))

    invalid = dict(valid)
    invalid["blackbox"] = invalid["api"].replace("/api:", "/blackbox:")
    with pytest.raises(contract.ReleaseContractError, match="distinct"):
        contract.commit_release(
            invalid,
            repository=repository,
            release_id=release_id,
            platform="linux/amd64",
            source_commit="a" * 40,
            manifest_dir=tmp_path,
        )
    assert not list(tmp_path.glob("*.release.json"))
    assert not list(tmp_path.glob("*.release.sha256"))

    manifest_path, checksum_path = contract.commit_release(
        valid,
        repository=repository,
        release_id=release_id,
        platform="linux/amd64",
        source_commit="a" * 40,
        manifest_dir=tmp_path,
    )
    manifest = json.loads(manifest_path.read_text())
    assert tuple(manifest["artifacts"]) == tuple(sorted(contract.ARTIFACTS))
    assert len({item["digest"] for item in manifest["artifacts"].values()}) == 8
    assert (
        manifest["runtime_bindings"]["scene_worker"]
        == manifest["runtime_bindings"]["api"]
    )
    checksum, filename = checksum_path.read_text().split()
    assert filename == manifest_path.name
    assert checksum == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    with pytest.raises(contract.ReleaseContractError, match="already has"):
        contract.commit_release(
            valid,
            repository=repository,
            release_id=release_id,
            platform="linux/amd64",
            source_commit="a" * 40,
            manifest_dir=tmp_path,
        )


def test_local_reservation_is_exclusive_and_burns_the_release_id(tmp_path: Path):
    def reserve() -> str:
        try:
            contract.reserve_release(
                manifest_dir=tmp_path,
                repository="registry.example/aperture",
                release_id="release-race",
            )
        except contract.ReleaseContractError:
            return "rejected"
        return "reserved"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: reserve(), range(2)))
    assert sorted(results) == ["rejected", "reserved"]
    reservation = tmp_path / "release-race.release.reserved.json"
    assert json.loads(reservation.read_text())["state"] == "reserved"


def test_reserved_release_rejects_reentry_before_registry_access(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    repository = "registry.example/aperture"
    release_id = "release-reserved"
    contract.reserve_release(
        manifest_dir=tmp_path, repository=repository, release_id=release_id
    )

    def unexpected_registry_access(*_args, **_kwargs):
        raise AssertionError("reserved release reached the registry")

    monkeypatch.setattr(contract.subprocess, "run", unexpected_registry_access)
    with pytest.raises(contract.ReleaseContractError, match="already locally reserved"):
        contract.preflight_tags(
            contract.expected_tags(repository, release_id),
            repository=repository,
            release_id=release_id,
            manifest_dir=tmp_path,
        )


def test_manifest_commit_precedes_environment_pin():
    script = BUILD_SCRIPT.read_text()
    commit = 'release_artifact_contract.py" commit'
    pin = 'pin_release.py"'
    assert script.index(commit) < script.index(pin)


FAKE_DOCKER = r'''import json
import os
import sys
from pathlib import Path

args = sys.argv[1:]
if args and args[0] == "buildx":
    args = args[1:]
log = Path(os.environ["FAKE_DOCKER_LOG"])
with log.open("a", encoding="utf-8") as handle:
    handle.write(json.dumps(args) + "\n")
mode = os.environ.get("FAKE_DOCKER_MODE", "success")

if args == ["version"]:
    raise SystemExit(0)

if args[:2] == ["imagetools", "inspect"]:
    tag = args[2]
    component = tag.rsplit("/", 1)[1].split(":", 1)[0]
    formatted = "--format" in args
    if not formatted:
        if mode == "reused" and component == "api":
            print("existing manifest")
            raise SystemExit(0)
        print("manifest unknown", file=sys.stderr)
        raise SystemExit(1)
    if mode == "digest-fail" and component == "web":
        print("registry unavailable", file=sys.stderr)
        raise SystemExit(31)
    components = [
        "api", "media-worker", "web", "backup", "caddy", "storage",
        "node-exporter", "blackbox",
    ]
    index = components.index(component) + 1
    if mode == "commit-fail" and component == "blackbox":
        reservation = Path(os.environ["APERTURE_RELEASE_MANIFEST_DIR"])
        reservation /= "release-123.release.reserved.json"
        reservation.unlink()
    print(json.dumps(f"sha256:{index:064x}"))
    raise SystemExit(0)

if args[:2] == ["imagetools", "create"]:
    raise SystemExit(0)

if args and args[0] == "build":
    tag = args[args.index("--tag") + 1]
    if mode == "build-fail" and "/web:" in tag:
        raise SystemExit(32)
    raise SystemExit(0)

raise SystemExit(97)
'''


def _shell() -> Path:
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidate /= "Git/bin/bash.exe"
        if candidate.is_file():
            return candidate
    resolved = shutil.which("sh")
    if resolved:
        return Path(resolved)
    pytest.skip("a POSIX shell is required for the release-script integration test")


def _fake_docker(directory: Path) -> Path:
    fake = directory / "fake-bin"
    fake.mkdir()
    script = directory / "fake_docker.py"
    script.write_text(FAKE_DOCKER)
    if os.name == "nt":
        shutil.copy2(sys.executable, fake / "docker.exe")
        # A renamed Python executable treats this file as its script because
        # ``buildx`` is Docker's first argument. Run from this directory below.
        (directory / "buildx").write_text(FAKE_DOCKER)
    else:
        wrapper = fake / "docker"
        wrapper.write_text(
            '#!/bin/sh\nexec python3 "$FAKE_DOCKER_SCRIPT" "$@"\n'
        )
        wrapper.chmod(0o755)
    return fake


def _release_project(directory: Path) -> tuple[Path, Path]:
    project = directory / "project"
    hostinger = project / "deploy/production/hostinger"
    hostinger.mkdir(parents=True)
    for name in (
        "build_release.sh",
        "pin_release.py",
        "read_env.py",
        "release_artifact_contract.py",
        "validate_config.py",
    ):
        shutil.copy2(ROOT / name, hostinger / name)
    (project / ".gitignore").write_text(".env\n")
    (project / ".dockerignore").write_text(".env\n")
    subprocess.run(
        ["git", "init", "--quiet", str(project)],
        check=True,
        capture_output=True,
        text=True,
    )
    for key, value in (("user.name", "Release Test"), ("user.email", "test@invalid")):
        subprocess.run(
            ["git", "-C", str(project), "config", key, value],
            check=True,
            capture_output=True,
            text=True,
        )
    subprocess.run(
        ["git", "-C", str(project), "add", "."],
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "-C", str(project), "commit", "--quiet", "-m", "release fixture"],
        check=True,
        capture_output=True,
        text=True,
    )
    # This represents the ignored owner runtime file that must not block release.
    (project / ".env").write_text("LOCAL_RUNTIME_SECRET=ignored\n")
    return project, hostinger / "build_release.sh"


def _release_input() -> str:
    return (
        "REGISTRY_REPOSITORY=registry.example/aperture\n"
        "RELEASE_ID=release-123\n"
        "RELEASE_PLATFORM=linux/amd64\n"
        "WEB_HOSTNAME=www.example.com\n"
        "STORAGE_HOSTNAME=storage.example.com\n"
        "CDN_HOSTNAME=cdn.example.com\n"
        "POLICY_REQUIRE_APPROVED=true\n"
        "CAPTCHA_REQUIRED=false\n"
        + "".join(
            f"{label}=dummy.registry/{component}@sha256:{'0' * 64}\n"
            for component, label in contract.IMAGE_LABELS.items()
        )
        + "SECRET=must-not-appear-in-release-manifest\n"
    )


def _run_release(
    mode: str,
    *,
    dirty_source: bool = False,
    reuse_infrastructure: bool = False,
) -> tuple[
    subprocess.CompletedProcess[str],
    Path,
    Path,
    str,
    tempfile.TemporaryDirectory[str],
]:
    temporary = tempfile.TemporaryDirectory()
    directory = Path(temporary.name)
    project, build_script = _release_project(directory)
    if dirty_source:
        (project / "untracked-build-context.txt").write_text("dirty\n")
    fake_bin = _fake_docker(directory)
    release_input = directory / "release.env"
    original = _release_input()
    release_input.write_text(original)
    manifest_dir = directory / "manifests"
    log = directory / "docker.log"
    environment = dict(os.environ)
    environment.update(
        {
            "PATH": str(fake_bin) + os.pathsep + environment.get("PATH", ""),
            "APERTURE_RELEASE_INPUT": str(release_input),
            "APERTURE_RELEASE_CREDENTIALS": str(release_input),
            "APERTURE_RELEASE_MANIFEST_DIR": str(manifest_dir),
            "FAKE_DOCKER_LOG": str(log),
            "FAKE_DOCKER_MODE": mode,
            "FAKE_DOCKER_SCRIPT": str(directory / "fake_docker.py"),
        }
    )
    if reuse_infrastructure:
        for index, component in enumerate(
            contract.INFRASTRUCTURE_ARTIFACTS, start=5
        ):
            label = component.upper()
            environment[f"APERTURE_REUSE_{label}_IMAGE"] = (
                "registry.example/aperture/"
                f"{contract.TAG_NAMES[component]}:accepted-platform@"
                f"sha256:{index:064x}"
            )
    result = subprocess.run(
        [str(_shell()), str(build_script)],
        cwd=directory,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result, release_input, log, original, temporary


def _docker_operations(path: Path) -> list[list[str]]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def test_source_preflight_allows_ignored_runtime_but_rejects_source_changes(
    tmp_path: Path,
):
    project, _build_script = _release_project(tmp_path)
    commit = contract.clean_source_commit(project)
    assert contract.SOURCE_COMMIT.fullmatch(commit)

    dockerignore = project / ".dockerignore"
    original = dockerignore.read_text()
    dockerignore.write_text(original + "temporary\n")
    with pytest.raises(contract.ReleaseContractError, match="unpublished changes"):
        contract.clean_source_commit(project)

    dockerignore.write_text(original)
    (project / "untracked-build-context.txt").write_text("dirty\n")
    with pytest.raises(contract.ReleaseContractError, match="unpublished changes"):
        contract.clean_source_commit(project)


def test_dirty_source_stops_before_reservation_registry_build_and_pin():
    result, release_input, log, original, _temporary = _run_release(
        "success", dirty_source=True
    )
    assert result.returncode != 0
    assert release_input.read_text() == original
    assert not log.exists()
    assert not (release_input.parent / "manifests").exists()


def test_reused_release_tag_stops_before_every_build_and_pin():
    result, release_input, log, original, _temporary = _run_release("reused")
    assert result.returncode != 0
    operations = _docker_operations(log)
    assert not [operation for operation in operations if operation[:1] == ["build"]]
    preflight = [
        operation
        for operation in operations
        if operation[:2] == ["imagetools", "inspect"]
        and "--format" not in operation
    ]
    assert len(preflight) == len(contract.ARTIFACTS)
    assert release_input.read_text() == original
    manifest_dir = release_input.parent / "manifests"
    assert (manifest_dir / "release-123.release.reserved.json").is_file()
    assert not (manifest_dir / "release-123.release.json").exists()
    assert not (manifest_dir / "release-123.release.sha256").exists()


@pytest.mark.parametrize("mode", ["build-fail", "digest-fail"])
def test_build_or_digest_failure_never_pins_or_commits(mode: str):
    result, release_input, log, original, _temporary = _run_release(mode)
    assert result.returncode != 0
    assert release_input.read_text() == original
    manifest_dir = release_input.parent / "manifests"
    assert (manifest_dir / "release-123.release.reserved.json").is_file()
    assert not (manifest_dir / "release-123.release.json").exists()
    assert not (manifest_dir / "release-123.release.sha256").exists()
    operations = _docker_operations(log)
    assert [operation for operation in operations if operation[:1] == ["build"]]


def test_commit_failure_after_valid_digests_never_pins_credentials():
    result, release_input, log, original, _temporary = _run_release("commit-fail")
    assert result.returncode != 0
    assert release_input.read_text() == original
    manifest_dir = release_input.parent / "manifests"
    assert not (manifest_dir / "release-123.release.json").exists()
    assert not (manifest_dir / "release-123.release.sha256").exists()
    operations = _docker_operations(log)
    formatted_inspects = [
        operation
        for operation in operations
        if operation[:2] == ["imagetools", "inspect"] and "--format" in operation
    ]
    assert len(formatted_inspects) == len(contract.ARTIFACTS)


def test_success_commits_only_after_eight_builds_and_valid_digests():
    result, release_input, log, original, _temporary = _run_release("success")
    assert result.returncode == 0, result.stderr
    assert release_input.read_text() != original
    operations = _docker_operations(log)
    builds = [operation for operation in operations if operation[:1] == ["build"]]
    formatted_inspects = [
        operation
        for operation in operations
        if operation[:2] == ["imagetools", "inspect"] and "--format" in operation
    ]
    assert len(builds) == len(contract.ARTIFACTS)
    assert len(formatted_inspects) == len(contract.ARTIFACTS)
    expected_tags = set(contract.expected_tags("registry.example/aperture", "release-123").values())
    build_tags = {operation[operation.index("--tag") + 1] for operation in builds}
    assert build_tags == expected_tags
    assert all("--provenance=mode=max" in operation for operation in builds)
    assert all("--sbom=true" in operation for operation in builds)
    manifest_path = release_input.parent / "manifests/release-123.release.json"
    manifest = json.loads(manifest_path.read_text())
    assert len(manifest["artifacts"]) == len(contract.ARTIFACTS)
    assert len({item["digest"] for item in manifest["artifacts"].values()}) == 8
    assert "must-not-appear" not in manifest_path.read_text()


def test_routine_release_retags_accepted_infrastructure_without_rebuilding_it():
    result, release_input, log, _original, _temporary = _run_release(
        "success", reuse_infrastructure=True
    )
    assert result.returncode == 0, result.stderr
    operations = _docker_operations(log)
    builds = [operation for operation in operations if operation[:1] == ["build"]]
    copies = [
        operation
        for operation in operations
        if operation[:2] == ["imagetools", "create"]
    ]
    assert len(builds) == 4
    assert {
        operation[operation.index("--tag") + 1].rsplit("/", 1)[1].split(":", 1)[0]
        for operation in builds
    } == {"api", "media-worker", "web", "backup"}
    assert len(copies) == len(contract.INFRASTRUCTURE_ARTIFACTS)
    assert all("--tag" in operation for operation in copies)
    manifest = json.loads(
        (release_input.parent / "manifests/release-123.release.json").read_text()
    )
    for index, component in enumerate(contract.INFRASTRUCTURE_ARTIFACTS, start=5):
        assert manifest["artifacts"][component]["digest"] == f"sha256:{index:064x}"


def test_reused_infrastructure_reference_is_component_and_digest_scoped():
    repository = "registry.example/aperture"
    valid = f"{repository}/storage:accepted-1@sha256:{'a' * 64}"
    assert (
        contract.validate_reuse_reference(
            "storage", valid, repository=repository
        )
        == f"sha256:{'a' * 64}"
    )
    with pytest.raises(contract.ReleaseContractError, match="wrong component"):
        contract.validate_reuse_reference(
            "storage",
            valid.replace("/storage:", "/caddy:"),
            repository=repository,
        )
    with pytest.raises(contract.ReleaseContractError, match="pin a digest"):
        contract.validate_reuse_reference(
            "storage", f"{repository}/storage:accepted-1", repository=repository
        )
    with pytest.raises(contract.ReleaseContractError, match="only infrastructure"):
        contract.validate_reuse_reference(
            "api",
            f"{repository}/api:accepted-1@sha256:{'b' * 64}",
            repository=repository,
        )
