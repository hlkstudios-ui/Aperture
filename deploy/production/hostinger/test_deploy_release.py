import errno
from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from contextlib import nullcontext
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
from types import SimpleNamespace
from typing import Callable
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "hostinger_deploy_release", ROOT / "deploy_release.py"
)
assert SPEC and SPEC.loader
deploy = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deploy
SPEC.loader.exec_module(deploy)


class BusyLock:
    def __enter__(self):
        raise deploy.LockUnavailable()

    def __exit__(self, *_args):
        return None


def _fake_recovery_compose_model(command: list[str]) -> dict[str, object]:
    env_path = Path(command[command.index("--env-file") + 1])
    runtime_images = deploy._runtime_images(
        env_path.read_bytes(), stage="test_recovery_compose"
    )
    services: dict[str, object] = {}
    for name, dependencies in deploy.EXPECTED_PUBLIC_SERVICE_DEPENDENCIES.items():
        record: dict[str, object] = {}
        if dependencies:
            record["depends_on"] = {
                dependency: {"condition": "service_started"}
                for dependency in dependencies
            }
        if name in deploy.EXPECTED_OPERATION_SERVICES:
            record["profiles"] = ["operations"]
        component = deploy.EXPECTED_PUBLIC_SERVICE_IMAGES.get(name)
        if component is not None:
            record["image"] = runtime_images[component]
        services[name] = record
    return {"services": services}


class FakeRunner:
    def __init__(
        self,
        fail_stage: str | None = None,
        recovery_model_mutator: (Callable[[dict[str, object]], None] | None) = None,
    ) -> None:
        self.fail_stage = fail_stage
        self.recovery_model_mutator = recovery_model_mutator
        self.events: list[str] = []
        self.commands: list[tuple[str, tuple[str, ...]]] = []
        self.environments: list[tuple[str, dict[str, str] | None]] = []
        self.timeouts: list[tuple[str, int]] = []

    def run(
        self,
        stage: str,
        command: list[str],
        *,
        capture: bool = False,
        timeout: int = 900,
        environment: dict[str, str] | None = None,
    ) -> str:
        self.events.append(stage)
        self.commands.append((stage, tuple(command)))
        self.environments.append((stage, environment))
        self.timeouts.append((stage, timeout))
        if stage == self.fail_stage:
            raise deploy.CommandFailure(stage)
        if stage == "render_monitoring":
            output = Path(command[command.index("--output") + 1])
            targets = Path(command[command.index("--targets-output") + 1])
            output.write_text("rendered without fixture secrets\n", encoding="utf-8")
            targets.write_text("[]\n", encoding="utf-8")
            os.chmod(output, 0o600)
            os.chmod(targets, 0o600)
        if stage == "compose_config" and capture:
            return '{"services": {}}\n'
        if stage == "recovery_compose_contract" and capture:
            value = _fake_recovery_compose_model(command)
            if self.recovery_model_mutator is not None:
                self.recovery_model_mutator(value)
            return json.dumps(value) + "\n"
        return ""


class MigrationTrackingRunner(FakeRunner):
    def __init__(self, *, fail_stage: str, target_migrate_state: str) -> None:
        super().__init__(fail_stage=fail_stage)
        self.target_migrate_state = target_migrate_state
        self.migrate_container_state: str | None = None
        self.migrate_remove_saw_state: str | None = None
        self.target_application_containers = False

    @property
    def target_api_image_collectible(self) -> bool:
        return (
            self.migrate_container_state is None
            and not self.target_application_containers
        )

    def run(
        self,
        stage: str,
        command: list[str],
        *,
        capture: bool = False,
        timeout: int = 900,
        environment: dict[str, str] | None = None,
    ) -> str:
        if stage == "public_rollout":
            # Model both a timed-out live target migration and a migration
            # which exited successfully before a later smoke failure.
            self.migrate_container_state = self.target_migrate_state
            self.target_application_containers = True
        if stage == "recovery_migrate_remove":
            self.migrate_remove_saw_state = self.migrate_container_state
            self.migrate_container_state = None
        if stage == "recovery_application_rollout":
            if self.migrate_container_state is not None:
                raise AssertionError("predecessor app started beside target migrate")
            self.target_application_containers = False
        return super().run(
            stage,
            command,
            capture=capture,
            timeout=timeout,
            environment=environment,
        )


class GCRunner(FakeRunner):
    def __init__(
        self,
        *,
        fail_stage: str | None = None,
        image_references: set[str] | None = None,
    ) -> None:
        super().__init__(fail_stage=fail_stage)
        self.image_references = image_references or set()

    def run(
        self,
        stage: str,
        command: list[str],
        *,
        capture: bool = False,
        timeout: int = 900,
        environment: dict[str, str] | None = None,
    ) -> str:
        result = super().run(
            stage,
            command,
            capture=capture,
            timeout=timeout,
            environment=environment,
        )
        if stage == "gc_image_inventory":
            lines = set()
            for reference in sorted(self.image_references):
                tagged, digest = reference.rsplit("@", 1)
                last_slash = tagged.rfind("/")
                last_colon = tagged.rfind(":")
                repository = tagged[:last_colon] if last_colon > last_slash else tagged
                lines.add(f"{repository}\t<none>\t{digest}")
            return "\n".join(sorted(lines)) + ("\n" if lines else "")
        return result


class DeployReleaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.uid = self.root.stat().st_uid
        opt = self.root / "opt/aperture"
        etc = self.root / "etc/aperture"
        var = self.root / "var/lib/aperture/incoming"
        lock = self.root / "var/lock"
        for directory in (
            opt / "shared",
            opt / "releases",
            opt / "release-history",
            opt / "deploy-attempts",
            opt / "deploy-jobs",
            opt / "deploy-status",
            etc,
            var,
            lock,
        ):
            directory.mkdir(parents=True, exist_ok=True)
            os.chmod(directory, 0o755)
        self.paths = deploy.DeployPaths(
            launch_marker=etc / "production-launch-enabled",
            public_runtime=opt / "shared/production.env",
            private_runtime=opt / "shared/private-studio.env",
            incoming_root=var,
            releases_dir=opt / "releases",
            current_link=opt / "current",
            history_dir=opt / "release-history",
            attempts_dir=opt / "deploy-attempts",
            lock_file=lock / "aperture-production-deploy.lock",
            jobs_dir=opt / "deploy-jobs",
            status_dir=opt / "deploy-status",
            transaction_dir=opt / "deploy-transaction",
        )
        os.chmod(self.paths.jobs_dir, 0o700)
        os.chmod(self.paths.status_dir, 0o700)
        os.chmod(self.paths.attempts_dir, 0o700)
        os.chmod(self.paths.incoming_root, 0o700)
        self.source_sha = "a" * 40
        self.current_source_sha = "f" * 40
        self.release_id = f"sha-{self.source_sha}"
        self.repository = "ghcr.io/hlkstudios-ui/aperture"
        self.current_digests = {
            component: f"sha256:{digit * 64}"
            for component, digit in zip(deploy.ARTIFACTS, "12345678", strict=True)
        }
        self.target_digests = {
            **self.current_digests,
            "api": "sha256:" + "a" * 64,
            "media_worker": "sha256:" + "b" * 64,
            "web": "sha256:" + "c" * 64,
            "backup": "sha256:" + "d" * 64,
        }
        self.current_references = {
            component: (
                f"{self.repository}/{deploy.TAG_NAMES[component]}:baseline@{digest}"
            )
            for component, digest in self.current_digests.items()
        }
        self.target_references = self._target_references(self.target_digests)
        self.current_public = self._public_runtime(self.current_references)
        self.current_private = (
            f"CADDY_IMAGE={self.current_references['caddy']}\n"
            "PUBLIC_APP_ORIGIN=https://apertures.online\n"
            "PUBLIC_APP_HOST=apertures.online\n"
            "ORIGIN_EDGE_SECRET=never-log-origin-secret\n"
            "STUDIO_EDGE_SECRET=never-log-studio-secret\n"
        ).encode()
        self.paths.public_runtime.write_bytes(self.current_public)
        self.paths.private_runtime.write_bytes(self.current_private)
        os.chmod(self.paths.public_runtime, 0o600)
        os.chmod(self.paths.private_runtime, 0o600)
        self.paths.launch_marker.write_text(deploy.LAUNCH_MARKER_CONTENT)
        os.chmod(self.paths.launch_marker, 0o644)

        self.current_release = self.paths.releases_dir / "baseline"
        self.current_release.mkdir()
        os.chmod(self.current_release, 0o755)
        self.source_files = {
            filename: f"fixture:{filename}\n".encode()
            for filename in deploy.REQUIRED_BUNDLE_FILES
        }
        self.source_files[deploy.SOURCE_MARKER] = (
            self.current_source_sha + "\n"
        ).encode()
        self._write_tree(self.current_release, self.source_files)
        (self.current_release / ".env").write_bytes(self.current_public)
        os.chmod(self.current_release / ".env", 0o600)
        accepted = {
            "schema_version": 1,
            "status": "accepted",
            "release_id": "baseline",
            "source_commit": self.current_source_sha,
            "platform": "linux/amd64",
            "accepted_at": "2026-08-30T00:00:00+00:00",
            "previous_release": None,
            "digests": self.current_digests,
            "effective_runtime_references": self.current_references,
            "database_schema_rollback": "not_attempted",
        }
        accepted_path = self.paths.history_dir / "baseline.json"
        accepted_path.write_text(json.dumps(accepted) + "\n", encoding="utf-8")
        os.chmod(accepted_path, 0o600)

        self.incoming = self.paths.incoming_root / self.release_id
        self.incoming.mkdir()
        os.chmod(self.incoming, 0o700)
        self.bundle = self.incoming / f"{self.release_id}.source.tar.gz"
        self.manifest = self.incoming / f"{self.release_id}.release.json"
        self.checksum = self.incoming / f"{self.release_id}.release.sha256"
        self._write_release_files()

    def tearDown(self) -> None:
        self.temporary.cleanup()

    @staticmethod
    def _write_tree(root: Path, files: dict[str, bytes]) -> None:
        for filename, content in files.items():
            path = root / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
            os.chmod(
                path,
                0o755 if filename in deploy.EXECUTABLE_BUNDLE_FILES else 0o644,
            )

    def _target_references(self, digests: dict[str, str]) -> dict[str, str]:
        return {
            component: (
                f"{self.repository}/{deploy.TAG_NAMES[component]}:"
                f"{self.release_id}@{digests[component]}"
            )
            for component in deploy.ARTIFACTS
        }

    @staticmethod
    def _public_runtime(references: dict[str, str]) -> bytes:
        values = [
            f"{deploy.IMAGE_LABELS[component]}={references[component]}"
            for component in deploy.ARTIFACTS
        ]
        values.extend(
            [
                "METRICS_BEARER_TOKEN=never-log-metrics-secret",
                "POSTGRES_PASSWORD=never-log-database-secret",
                "WEB_HOSTNAME=apertures.online",
            ]
        )
        return ("\n".join(values) + "\n").encode()

    def _add_accepted_release(
        self,
        release_id: str,
        *,
        previous_release: str | None,
        accepted_at: str,
    ) -> tuple[Path, dict[str, str], str]:
        source_sha = hashlib.sha1(
            release_id.encode(), usedforsecurity=False
        ).hexdigest()
        references: dict[str, str] = {}
        digests: dict[str, str] = {}
        for component in deploy.ARTIFACTS:
            digest = (
                "sha256:"
                + hashlib.sha256(f"{release_id}:{component}".encode()).hexdigest()
            )
            digests[component] = digest
            references[component] = (
                f"{self.repository}/{deploy.TAG_NAMES[component]}:{release_id}@{digest}"
            )
        release = self.paths.releases_dir / release_id
        release.mkdir()
        os.chmod(release, 0o755)
        files = dict(self.source_files)
        files[deploy.SOURCE_MARKER] = (source_sha + "\n").encode()
        self._write_tree(release, files)
        runtime = self._public_runtime(references)
        (release / ".env").write_bytes(runtime)
        os.chmod(release / ".env", 0o600)
        record = {
            "schema_version": 1,
            "status": "accepted",
            "release_id": release_id,
            "source_commit": source_sha,
            "platform": "linux/amd64",
            "accepted_at": accepted_at,
            "previous_release": previous_release,
            "digests": digests,
            "effective_runtime_references": references,
            "database_schema_rollback": "not_attempted",
        }
        record_path = self.paths.history_dir / f"{release_id}.json"
        record_path.write_text(json.dumps(record) + "\n", encoding="utf-8")
        os.chmod(record_path, 0o600)
        return release, references, source_sha

    def _prepare_gc_chain(
        self,
    ) -> tuple[Path, Path, Path, dict[str, str]]:
        predecessor, _predecessor_refs, _source = self._add_accepted_release(
            "release-predecessor",
            previous_release="baseline",
            accepted_at="2026-08-27T00:00:00+00:00",
        )
        previous, _previous_refs, _source = self._add_accepted_release(
            "release-previous",
            previous_release="release-predecessor",
            accepted_at="2026-08-28T00:00:00+00:00",
        )
        current, current_refs, _source = self._add_accepted_release(
            "release-current",
            previous_release="release-previous",
            accepted_at="2026-08-29T00:00:00+00:00",
        )
        current_public = self._public_runtime(current_refs)
        current_private = self.current_private.replace(
            self.current_references["caddy"].encode(),
            current_refs["caddy"].encode(),
        )
        self.paths.public_runtime.write_bytes(current_public)
        self.paths.private_runtime.write_bytes(current_private)
        os.chmod(self.paths.public_runtime, 0o600)
        os.chmod(self.paths.private_runtime, 0o600)
        return current, previous, predecessor, current_refs

    def _record_attempt(
        self, release_id: str, application_references: dict[str, str]
    ) -> Path:
        references = dict(self.current_references)
        references.update(application_references)
        release = deploy.Release(
            release_id=release_id,
            repository=self.repository,
            source_commit=hashlib.sha256(release_id.encode()).hexdigest()[:40],
            references=references,
            digests={
                component: deploy._digest(reference)
                for component, reference in references.items()
            },
        )
        deploy._record_release_attempt(self.paths, release, self.uid)
        return self.paths.attempts_dir / f"{release_id}.json"

    def _failed_application_references(self, release_id: str) -> dict[str, str]:
        return {
            component: (
                f"{self.repository}/{deploy.TAG_NAMES[component]}:{release_id}@sha256:"
                + hashlib.sha256(f"{release_id}:{component}".encode()).hexdigest()
            )
            for component in deploy.APPLICATION_ARTIFACTS
        }

    def _manifest_value(
        self, digests: dict[str, str] | None = None
    ) -> dict[str, object]:
        selected = digests or self.target_digests
        references = self._target_references(selected)
        artifacts = {}
        for component in deploy.ARTIFACTS:
            tag = references[component].rsplit("@", 1)[0]
            artifacts[component] = {
                "tag": tag,
                "digest": selected[component],
                "reference": references[component],
            }
        return {
            "schema_version": 1,
            "release_id": self.release_id,
            "repository": self.repository,
            "platform": "linux/amd64",
            "source_commit": self.source_sha,
            "artifacts": artifacts,
            "runtime_bindings": {
                binding: references[component]
                for binding, component in deploy.RUNTIME_BINDINGS.items()
            },
            "registry_attestations": dict(deploy.ATTESTATIONS),
        }

    def _bundle_bytes(
        self,
        *,
        files: dict[str, bytes] | None = None,
        extra_member: tarfile.TarInfo | None = None,
        extra_content: bytes = b"",
    ) -> bytes:
        selected = dict(self.source_files if files is None else files)
        selected[deploy.SOURCE_MARKER] = (self.source_sha + "\n").encode()
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for filename, content in sorted(selected.items()):
                info = tarfile.TarInfo(filename)
                info.size = len(content)
                info.mode = 0o644
                archive.addfile(info, io.BytesIO(content))
            if extra_member is not None:
                archive.addfile(extra_member, io.BytesIO(extra_content))
        return output.getvalue()

    def _write_release_files(
        self,
        *,
        manifest_value: dict[str, object] | None = None,
        bundle_bytes: bytes | None = None,
    ) -> None:
        manifest_content = (
            json.dumps(
                manifest_value or self._manifest_value(), indent=2, sort_keys=True
            )
            + "\n"
        ).encode()
        bundle_content = bundle_bytes or self._bundle_bytes()
        self.manifest.write_bytes(manifest_content)
        self.bundle.write_bytes(bundle_content)
        self.checksum.write_text(
            f"{hashlib.sha256(manifest_content).hexdigest()}  {self.manifest.name}\n"
            f"{hashlib.sha256(bundle_content).hexdigest()}  {self.bundle.name}\n",
            encoding="ascii",
        )
        for path in (self.manifest, self.bundle, self.checksum):
            os.chmod(path, 0o600)

    def _deployer(
        self,
        runner: FakeRunner | None = None,
        *,
        lock_factory=None,
    ) -> deploy.Deployer:
        return deploy.Deployer(
            self.paths,
            runner=runner or FakeRunner(),
            expected_uid=self.uid,
            require_root=False,
            lock_factory=lock_factory or (lambda: nullcontext()),
        )

    def _target_release(self) -> deploy.Release:
        return deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )

    def _create_target_transaction(self) -> dict[str, object]:
        return deploy._create_transaction(
            self.paths,
            release=self._target_release(),
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )

    def _run_successful_boot_recovery(self) -> tuple[int, list[str]]:
        switches: list[str] = []
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(deploy, "CommandRunner", return_value=FakeRunner()),
            patch.object(deploy, "ProductionLock", return_value=nullcontext()),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(
                deploy,
                "_switch_current",
                side_effect=lambda _path, target: switches.append(target),
            ),
        ):
            result = deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        return result, switches

    def _deploy(
        self,
        runner: FakeRunner | None = None,
        *,
        switch_events: list[str] | None = None,
        expected_current_source_sha: str | None = None,
    ) -> dict[str, object]:
        events = switch_events if switch_events is not None else []

        def switch(_path: Path, target: str) -> None:
            events.append(target)

        with (
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(deploy, "_switch_current", side_effect=switch),
        ):
            return self._deployer(runner).deploy(
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=(
                    expected_current_source_sha or self.current_source_sha
                ),
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
            )

    def test_current_source_report_and_deploy_compare_the_same_marker(self) -> None:
        with patch.object(
            deploy,
            "_current_release",
            return_value=(self.current_release, "releases/baseline"),
        ):
            reported = deploy.report_current_source_sha(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(reported, self.current_source_sha)

        runner = FakeRunner()
        with self.assertRaises(deploy.DeployError) as raised:
            self._deploy(
                runner,
                expected_current_source_sha="e" * 40,
            )
        self.assertEqual(raised.exception.stage, "current_source_drift")
        self.assertEqual(runner.events, [])

    def test_current_release_requires_matching_root_owned_accepted_record(
        self,
    ) -> None:
        (self.paths.history_dir / "baseline.json").unlink()
        with (
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.report_current_source_sha(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(raised.exception.stage, "accepted_record")

    @unittest.skipIf(os.name == "nt", "production symlink semantics are Linux-only")
    def test_current_release_rejects_absolute_or_non_normalized_target(self) -> None:
        os.symlink(self.current_release, self.paths.current_link)
        with self.assertRaises(deploy.DeployError) as absolute:
            deploy._current_release(self.paths, self.uid)
        self.assertEqual(absolute.exception.stage, "current_release")
        self.paths.current_link.unlink()
        os.symlink("releases/../releases/baseline", self.paths.current_link)
        with self.assertRaises(deploy.DeployError) as non_normalized:
            deploy._current_release(self.paths, self.uid)
        self.assertEqual(non_normalized.exception.stage, "current_release")

    def test_incomplete_transaction_blocks_source_reporting(self) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        transaction = deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        with self.assertRaises(deploy.DeployError) as raised:
            deploy.report_current_source_sha(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(raised.exception.stage, "incomplete_transaction")

    def test_transaction_live_metadata_crash_before_replace_recovers_on_boot(
        self,
    ) -> None:
        transaction = self._create_target_transaction()
        pending = deploy._transaction_metadata_pending(self.paths)
        with (
            patch.object(
                deploy.os,
                "replace",
                side_effect=SystemExit("simulated crash before metadata replace"),
            ),
            self.assertRaises(SystemExit),
        ):
            deploy._mark_transaction_live(self.paths, transaction, self.uid)

        self.assertTrue(pending.is_file())
        metadata = json.loads(
            (self.paths.transaction_dir / deploy.TRANSACTION_METADATA).read_text()
        )
        self.assertEqual(metadata["state"], "prepared")
        result, switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertEqual(switches, ["releases/baseline"])
        self.assertFalse(pending.exists())
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_transaction_live_metadata_enospc_debris_recovers_on_boot(self) -> None:
        transaction = self._create_target_transaction()
        pending = deploy._transaction_metadata_pending(self.paths)
        original_write = deploy.os.write
        calls = 0

        def partial_then_full(fd: int, content: object) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_write(fd, memoryview(content)[:7])
            raise OSError(errno.ENOSPC, "simulated full filesystem")

        with (
            patch.object(deploy.os, "write", side_effect=partial_then_full),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy._mark_transaction_live(self.paths, transaction, self.uid)
        self.assertEqual(raised.exception.stage, "transaction_metadata")
        self.assertEqual(pending.read_bytes(), b'{"previ')

        result, switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertEqual(switches, ["releases/baseline"])
        self.assertFalse(pending.exists())
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_boot_recovery_removes_atomic_accepted_record_after_publish_crash(
        self,
    ) -> None:
        transaction = self._create_target_transaction()
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        history = deploy._accepted_record(
            self._target_release(),
            effective_references=self.target_references,
            previous_release="baseline",
        )
        pending = deploy._accepted_pending_path(self.paths, self.release_id)
        final = self.paths.history_dir / f"{self.release_id}.json"
        with (
            patch.object(
                deploy,
                "_fsync_directory",
                side_effect=SystemExit("simulated crash after accepted link"),
            ),
            self.assertRaises(SystemExit),
        ):
            deploy._publish_accepted_record(
                self.paths,
                release_id=self.release_id,
                value=history,
                expected_uid=self.uid,
            )
        self.assertTrue(pending.is_file())
        self.assertTrue(final.is_file())
        self.assertTrue(os.path.samestat(pending.stat(), final.stat()))

        result, switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertEqual(switches, ["releases/baseline"])
        self.assertFalse(pending.exists())
        self.assertFalse(final.exists())

    def test_boot_recovery_removes_partial_legacy_accepted_record(self) -> None:
        transaction = self._create_target_transaction()
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        final = self.paths.history_dir / f"{self.release_id}.json"
        final.write_bytes(b'{"schema_version":')
        os.chmod(final, 0o600)

        result, switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertEqual(switches, ["releases/baseline"])
        self.assertFalse(final.exists())
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_restart_recovery_uses_durable_predecessor_and_clears_journal(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        transaction = deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        self.paths.public_runtime.write_bytes(
            self._public_runtime(self.target_references)
        )
        self.paths.private_runtime.write_bytes(
            self.current_private.replace(
                self.current_references["caddy"].encode(),
                self.target_references["caddy"].encode(),
            )
        )
        os.chmod(self.paths.public_runtime, 0o600)
        os.chmod(self.paths.private_runtime, 0o600)
        runner = FakeRunner()
        switches: list[str] = []
        with (
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(
                deploy,
                "_switch_current",
                side_effect=lambda _path, target: switches.append(target),
            ),
        ):
            result = self._deployer(runner).recover_incomplete_transaction()
        self.assertEqual(result["recovery_status"], "completed")
        self.assertEqual(switches, ["releases/baseline"])
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)
        self.assertEqual(self.paths.private_runtime.read_bytes(), self.current_private)
        self.assertFalse(self.paths.transaction_dir.exists())
        self.assertEqual(
            runner.events[-10:],
            [
                "recovery_compose_contract",
                "recovery_migrate_remove",
                "recovery_stateful_rollout",
                "recovery_initializer_rollout",
                "recovery_application_rollout",
                "recovery_edge_rollout",
                "recovery_private_rollout",
                "recovery_preflight",
                "recovery_coupling",
                "recovery_public_smoke",
            ],
        )

    def test_boot_recovery_publishes_failure_status_and_removes_root_job(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        transaction = deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        deploy._stage_job(
            self.paths,
            bundle=self.bundle,
            manifest=self.manifest,
            checksum=self.checksum,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
        )
        self.paths.public_runtime.write_bytes(
            self._public_runtime(self.target_references)
        )
        self.paths.private_runtime.write_bytes(
            self.current_private.replace(
                self.current_references["caddy"].encode(),
                self.target_references["caddy"].encode(),
            )
        )
        os.chmod(self.paths.public_runtime, 0o600)
        os.chmod(self.paths.private_runtime, 0o600)
        runner = FakeRunner()
        switches: list[str] = []
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(deploy, "CommandRunner", return_value=runner),
            patch.object(deploy, "ProductionLock", return_value=nullcontext()),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(
                deploy,
                "_switch_current",
                side_effect=lambda _path, target: switches.append(target),
            ),
        ):
            result = deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(result, 0)
        status = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(status["state"], "fail")
        self.assertEqual(status["stage"], "interrupted_transaction")
        self.assertEqual(status["recovery_status"], "completed")
        self.assertEqual(switches, ["releases/baseline"])
        self.assertFalse(self.paths.transaction_dir.exists())
        self.assertFalse((self.paths.jobs_dir / self.release_id).exists())

    def test_boot_recovery_leaves_malformed_journal_fail_closed(self) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        metadata = self.paths.transaction_dir / deploy.TRANSACTION_METADATA
        metadata.write_text('{"schema_version": 999}\n', encoding="utf-8")
        os.chmod(metadata, 0o600)
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "incomplete_transaction")
        self.assertTrue(self.paths.transaction_dir.is_dir())

    def test_boot_recovery_failure_stays_nonterminal_and_retries_without_reboot(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        transaction = deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        runner = FakeRunner(fail_stage="recovery_preflight")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(deploy, "CommandRunner", return_value=runner),
            patch.object(deploy, "ProductionLock", return_value=nullcontext()),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(deploy, "_switch_current"),
            self.assertRaises(deploy.DeploymentExecutionError),
        ):
            deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        status = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(status["state"], "running")
        self.assertEqual(status["stage"], "recovery")
        self.assertEqual(status["recovery_status"], "failed")
        self.assertTrue(self.paths.transaction_dir.is_dir())

        result, switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertEqual(switches, ["releases/baseline"])
        terminal = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(terminal["state"], "fail")
        self.assertEqual(terminal["recovery_status"], "completed")
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_transaction_rename_commit_survives_cleanup_crash_and_boot_cleans(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        with (
            patch.object(
                deploy,
                "_delete_transaction_directory",
                side_effect=SystemExit("simulated crash after rename"),
            ),
            self.assertRaises(SystemExit),
        ):
            deploy._remove_transaction(self.paths, self.uid)
        tombstone = deploy._transaction_tombstone(self.paths)
        self.assertFalse(self.paths.transaction_dir.exists())
        self.assertTrue(tombstone.is_dir())
        with patch.dict(os.environ, {}, clear=True):
            result = deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(result, 0)
        self.assertFalse(tombstone.exists())

    def test_partial_committed_tombstone_is_cleaned_without_recovery(self) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        tombstone = deploy._transaction_tombstone(self.paths)
        os.replace(self.paths.transaction_dir, tombstone)
        (tombstone / deploy.TRANSACTION_METADATA).unlink()
        (tombstone / deploy.TRANSACTION_PUBLIC).unlink()
        with patch.dict(os.environ, {}, clear=True):
            result = deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(result, 0)
        self.assertFalse(tombstone.exists())

    def test_committed_tombstone_with_unexpected_entry_fails_closed(self) -> None:
        tombstone = deploy._transaction_tombstone(self.paths)
        tombstone.mkdir()
        os.chmod(tombstone, 0o700)
        unexpected = tombstone / "unexpected"
        unexpected.write_bytes(b"not controller cleanup state")
        os.chmod(unexpected, 0o600)
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "transaction_tombstone")
        self.assertTrue(tombstone.is_dir())

    def test_start_delegates_committed_tombstone_cleanup_to_recovery(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        tombstone = deploy._transaction_tombstone(self.paths)
        os.replace(self.paths.transaction_dir, tombstone)
        with (
            patch.object(deploy, "_transient_service_release", return_value=None),
            patch.object(deploy, "_start_boot_recovery_service") as recovery,
            patch.object(deploy, "_launch_transient_service") as transient,
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "recovery_pending")
        recovery.assert_called_once_with()
        transient.assert_not_called()
        self.assertTrue(tombstone.exists())

    def test_start_copies_payload_before_launch_and_status_is_root_validated(
        self,
    ) -> None:
        with (
            patch.object(deploy, "_transient_service_release", return_value=None),
            patch.object(deploy, "_launch_transient_service") as launch,
        ):
            queued = deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(queued["state"], "queued")
        launch.assert_called_once()
        root_bundle, root_manifest, root_checksum = deploy._job_paths(
            self.paths, self.release_id
        )
        self.assertEqual(root_bundle.read_bytes(), self.bundle.read_bytes())
        self.assertEqual(root_manifest.read_bytes(), self.manifest.read_bytes())
        self.assertEqual(root_checksum.read_bytes(), self.checksum.read_bytes())
        self.bundle.unlink()
        status = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(status["source_commit"], self.source_sha)

    def test_retry_after_interruption_before_systemd_launch_reconciles_job(
        self,
    ) -> None:
        deploy._stage_job(
            self.paths,
            bundle=self.bundle,
            manifest=self.manifest,
            checksum=self.checksum,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
        )
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="queued",
            expected_uid=self.uid,
        )
        with (
            patch.object(deploy, "_transient_service_release", return_value=None),
            patch.object(deploy, "_launch_transient_service") as launch,
        ):
            status = deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(status["state"], "queued")
        launch.assert_called_once()

    def test_retry_does_not_fail_or_relaunch_active_fixed_unit(self) -> None:
        deploy._stage_job(
            self.paths,
            bundle=self.bundle,
            manifest=self.manifest,
            checksum=self.checksum,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
        )
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="running",
            stage="deploy",
            expected_uid=self.uid,
        )
        with (
            patch.object(
                deploy,
                "_transient_service_release",
                return_value=self.release_id,
            ),
            patch.object(deploy, "_launch_transient_service") as launch,
        ):
            status = deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(status["state"], "running")
        launch.assert_not_called()

    def test_retry_during_live_metadata_publication_never_unlinks_worker_pending(
        self,
    ) -> None:
        transaction = self._create_target_transaction()
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="running",
            stage="deploy",
            expected_uid=self.uid,
        )
        pending_written = threading.Event()
        allow_replace = threading.Event()
        failures: list[BaseException] = []
        original_pending_write = deploy._write_pending_file

        def pause_after_write(path: Path, content: bytes) -> None:
            original_pending_write(path, content)
            pending_written.set()
            if not allow_replace.wait(timeout=5):
                raise AssertionError("test did not release metadata publisher")

        def publish() -> None:
            try:
                deploy._mark_transaction_live(self.paths, transaction, self.uid)
            except BaseException as error:  # pragma: no branch - diagnostic capture
                failures.append(error)

        with patch.object(deploy, "_write_pending_file", side_effect=pause_after_write):
            publisher = threading.Thread(target=publish)
            publisher.start()
            self.assertTrue(pending_written.wait(timeout=5))
            pending = deploy._transaction_metadata_pending(self.paths)
            self.assertTrue(pending.is_file())
            with (
                patch.object(
                    deploy,
                    "_transient_service_release",
                    return_value=self.release_id,
                ),
                patch.object(deploy, "_launch_transient_service") as launch,
                self.assertRaises(deploy.DeployError) as raised,
            ):
                deploy.start_deployment(
                    self.paths,
                    bundle=self.bundle,
                    manifest=self.manifest,
                    checksum=self.checksum,
                    expected_current_source_sha=self.current_source_sha,
                    expected_source_sha=self.source_sha,
                    expected_release_id=self.release_id,
                    expected_uid=self.uid,
                    require_root=False,
                )
            self.assertEqual(raised.exception.stage, "recovery_pending")
            self.assertTrue(pending.is_file())
            launch.assert_not_called()
            allow_replace.set()
            publisher.join(timeout=5)
        self.assertFalse(publisher.is_alive())
        self.assertEqual(failures, [])
        self.assertFalse(pending.exists())
        metadata = json.loads(
            (self.paths.transaction_dir / deploy.TRANSACTION_METADATA).read_text()
        )
        self.assertEqual(metadata["state"], "live_mutated")

    def test_systemctl_transport_error_is_not_treated_as_unit_absence(self) -> None:
        with (
            patch.object(
                deploy.subprocess,
                "run",
                return_value=SimpleNamespace(returncode=1, stdout=""),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy._transient_service_release()
        self.assertEqual(raised.exception.stage, "service_status")

        with patch.object(
            deploy.subprocess,
            "run",
            return_value=SimpleNamespace(
                returncode=1,
                stdout="LoadState=not-found\nActiveState=inactive\nExecStart=\n",
            ),
        ):
            self.assertIsNone(deploy._transient_service_release())

    def test_status_gc_barrier_serializes_queued_running_and_final_writes(
        self,
    ) -> None:
        original_atomic_write = deploy._atomic_write
        for state in ("queued", "running", "pass"):
            with self.subTest(state=state):
                release_id = f"status-barrier-{state}"
                shared = threading.Lock()
                writer_paused = threading.Event()
                release_writer = threading.Event()
                cleanup_waiting = threading.Event()
                cleanup_done = threading.Event()
                errors: list[BaseException] = []

                class SharedStatusLock:
                    def __enter__(inner_self):
                        if threading.current_thread().name == "status-cleanup":
                            cleanup_waiting.set()
                        shared.acquire()
                        return inner_self

                    def __exit__(inner_self, *_args: object) -> None:
                        shared.release()

                def paused_atomic_write(path: Path, content: bytes, mode: int) -> None:
                    if path.name == f"{release_id}.json":
                        writer_paused.set()
                        if not release_writer.wait(timeout=5):
                            raise AssertionError("test did not release status writer")
                    original_atomic_write(path, content, mode)

                def write_status() -> None:
                    try:
                        deploy._write_status(
                            self.paths,
                            release_id=release_id,
                            source_commit="d" * 40,
                            state=state,
                            stage="complete" if state == "pass" else None,
                            expected_uid=self.uid,
                        )
                    except BaseException as error:  # pragma: no branch
                        errors.append(error)

                def clean_statuses() -> None:
                    try:
                        deploy._remove_old_statuses(
                            self.paths,
                            protected={"baseline"},
                            current_release=self.current_release,
                            service_release=(
                                (lambda: release_id)
                                if state in {"queued", "running"}
                                else (lambda: None)
                            ),
                            now_timestamp=2_000_000_000.0,
                            expected_uid=self.uid,
                        )
                    except BaseException as error:  # pragma: no branch
                        errors.append(error)
                    finally:
                        cleanup_done.set()

                with (
                    patch.object(
                        deploy,
                        "_status_publication_lock",
                        side_effect=lambda *_args: SharedStatusLock(),
                    ),
                    patch.object(
                        deploy, "_atomic_write", side_effect=paused_atomic_write
                    ),
                ):
                    writer = threading.Thread(target=write_status, name="status-writer")
                    cleaner = threading.Thread(
                        target=clean_statuses, name="status-cleanup"
                    )
                    writer.start()
                    self.assertTrue(writer_paused.wait(timeout=5))
                    cleaner.start()
                    self.assertTrue(cleanup_waiting.wait(timeout=5))
                    self.assertFalse(cleanup_done.is_set())
                    release_writer.set()
                    writer.join(timeout=5)
                    cleaner.join(timeout=5)
                self.assertFalse(writer.is_alive())
                self.assertFalse(cleaner.is_alive())
                self.assertEqual(errors, [])
                published = deploy.report_deployment_status(
                    self.paths,
                    expected_release_id=release_id,
                    expected_uid=self.uid,
                    require_root=False,
                )
                self.assertEqual(published["state"], state)

    def test_boot_recovery_never_touches_journal_before_shared_lock(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(deploy, "fcntl", SimpleNamespace()),
            patch.object(deploy, "RetryingProductionLock", return_value=BusyLock()),
            patch.object(deploy, "_cleanup_transaction_metadata_pending") as pending,
            patch.object(deploy, "_cleanup_transaction_tombstone") as tombstone,
            self.assertRaises(deploy.LockUnavailable),
        ):
            deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        pending.assert_not_called()
        tombstone.assert_not_called()

    def test_reconcile_starts_persistent_recovery_when_journal_survives_unit(
        self,
    ) -> None:
        release = deploy.Release(
            release_id=self.release_id,
            repository=self.repository,
            source_commit=self.source_sha,
            references=self.target_references,
            digests=self.target_digests,
        )
        transaction = deploy._create_transaction(
            self.paths,
            release=release,
            previous_release="baseline",
            previous_current_target="releases/baseline",
            old_public=self.current_public,
            old_private=self.current_private,
            expected_uid=self.uid,
        )
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="running",
            stage="deploy",
            expected_uid=self.uid,
        )
        with (
            patch.object(deploy, "_transient_service_release", return_value=None),
            patch.object(deploy, "_start_boot_recovery_service") as recovery,
            patch.object(deploy, "_launch_transient_service") as transient,
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "recovery_pending")
        recovery.assert_called_once_with()
        transient.assert_not_called()

    def test_terminal_status_cannot_short_circuit_surviving_journal(self) -> None:
        transaction = self._create_target_transaction()
        deploy._mark_transaction_live(self.paths, transaction, self.uid)
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="fail",
            stage="target_preflight",
            recovery_status="failed",
            expected_uid=self.uid,
        )
        with (
            patch.object(deploy, "_transient_service_release", return_value=None),
            patch.object(deploy, "_start_boot_recovery_service") as recovery,
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.start_deployment(
                self.paths,
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "recovery_pending")
        recovery.assert_called_once_with()

    def test_sudo_cannot_invoke_internal_foreground_worker(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"SUDO_USER": "aperture-deploy", "SUDO_UID": "1234"},
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.run_deployment_worker(
                self.paths,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "worker_invocation")

    def test_worker_retries_pass_publication_without_false_terminal_failure(
        self,
    ) -> None:
        self._deploy(FakeRunner())
        candidate = self.paths.releases_dir / self.release_id
        deploy._stage_job(
            self.paths,
            bundle=self.bundle,
            manifest=self.manifest,
            checksum=self.checksum,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
        )
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="running",
            stage="deploy",
            expected_uid=self.uid,
        )
        original_write_status = deploy._write_status
        pass_attempts = 0

        def fail_first_pass(*args: object, **kwargs: object) -> dict[str, object]:
            nonlocal pass_attempts
            if kwargs.get("state") == "pass":
                pass_attempts += 1
                if pass_attempts == 1:
                    raise deploy.DeployError("status")
            return original_write_status(*args, **kwargs)  # type: ignore[arg-type]

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(candidate, f"releases/{self.release_id}"),
            ),
            patch.object(deploy, "_write_status", side_effect=fail_first_pass),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.run_deployment_worker(
                self.paths,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "status")
        still_running = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(still_running["state"], "running")
        self.assertFalse((self.paths.jobs_dir / self.release_id).exists())

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(candidate, f"releases/{self.release_id}"),
            ),
        ):
            self.assertEqual(
                deploy.run_deployment_worker(
                    self.paths,
                    expected_current_source_sha=self.current_source_sha,
                    expected_source_sha=self.source_sha,
                    expected_release_id=self.release_id,
                    expected_uid=self.uid,
                    require_root=False,
                ),
                0,
            )
        terminal = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(terminal["state"], "pass")
        self.assertEqual(terminal["stage"], "complete")

    def test_worker_compensation_failure_retries_recovery_without_reboot(
        self,
    ) -> None:
        deploy._stage_job(
            self.paths,
            bundle=self.bundle,
            manifest=self.manifest,
            checksum=self.checksum,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
        )
        deploy._write_status(
            self.paths,
            release_id=self.release_id,
            source_commit=self.source_sha,
            state="queued",
            expected_uid=self.uid,
        )

        def fail_with_journal(
            _controller: deploy.Deployer, **_kwargs: object
        ) -> dict[str, object]:
            transaction = self._create_target_transaction()
            deploy._mark_transaction_live(self.paths, transaction, self.uid)
            raise deploy.DeploymentExecutionError(
                "target_preflight", "failed", "recovery_preflight"
            )

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(
                deploy.Deployer,
                "deploy",
                autospec=True,
                side_effect=fail_with_journal,
            ),
            self.assertRaises(deploy.DeploymentExecutionError),
        ):
            deploy.run_deployment_worker(
                self.paths,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
                expected_uid=self.uid,
                require_root=False,
            )
        recovering = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(recovering["state"], "running")
        self.assertEqual(recovering["stage"], "recovery")
        self.assertEqual(recovering["recovery_status"], "failed")
        self.assertTrue(self.paths.transaction_dir.is_dir())
        self.assertFalse((self.paths.jobs_dir / self.release_id).exists())

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(deploy, "CommandRunner", return_value=FakeRunner()),
            patch.object(deploy, "RetryingProductionLock", return_value=nullcontext()),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            patch.object(deploy, "_switch_current"),
        ):
            self.assertEqual(
                deploy.run_deployment_worker(
                    self.paths,
                    expected_current_source_sha=self.current_source_sha,
                    expected_source_sha=self.source_sha,
                    expected_release_id=self.release_id,
                    expected_uid=self.uid,
                    require_root=False,
                ),
                0,
            )
        terminal = deploy.report_deployment_status(
            self.paths,
            expected_release_id=self.release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(terminal["state"], "fail")
        self.assertEqual(terminal["recovery_status"], "completed")
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_sudo_cannot_invoke_internal_boot_recovery(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"SUDO_USER": "aperture-deploy", "SUDO_UID": "1234"},
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.run_boot_recovery(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
            )
        self.assertEqual(raised.exception.stage, "recovery_invocation")

    def test_sudo_cannot_invoke_internal_gc(self) -> None:
        with (
            patch.dict(
                os.environ,
                {"SUDO_USER": "aperture-deploy", "SUDO_UID": "1234"},
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(raised.exception.stage, "gc_invocation")

    def test_systemd_service_is_nonblocking_restartable_and_bounded(self) -> None:
        completed = subprocess.CompletedProcess([], 0)
        with patch.object(deploy.subprocess, "run", return_value=completed) as run:
            deploy._launch_transient_service(
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
            )
        command = run.call_args.args[0]
        self.assertEqual(command[0].replace("\\", "/"), "/usr/bin/systemd-run")
        self.assertIn("--no-block", command)
        self.assertIn("--collect", command)
        self.assertIn("--property=Restart=on-failure", command)
        self.assertIn("--property=RuntimeMaxSec=3h", command)
        self.assertIn("--property=RefuseManualStop=yes", command)
        self.assertIn(
            "--property=ReadWritePaths=/opt/aperture -/var/lib/aperture",
            command,
        )
        self.assertIn("--worker", command)

    def test_launch_marker_and_existing_baseline_are_both_required(self) -> None:
        self.paths.launch_marker.unlink()
        runner = FakeRunner()
        with self.assertRaisesRegex(
            deploy.DeployError, "production deployment"
        ) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "launch_marker")
        self.assertEqual(runner.events, [])

        self.paths.launch_marker.write_text(deploy.LAUNCH_MARKER_CONTENT)
        os.chmod(self.paths.launch_marker, 0o644)
        with self.assertRaises(deploy.DeployError) as no_baseline:
            self._deployer(runner).deploy(
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
            )
        self.assertEqual(no_baseline.exception.stage, "current_release")

    def test_current_release_env_must_match_shared_runtime(self) -> None:
        (self.current_release / ".env").write_bytes(
            self.current_public + b"DRIFT=not-active\n"
        )
        os.chmod(self.current_release / ".env", 0o600)
        runner = FakeRunner()
        with self.assertRaises(deploy.DeployError) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "runtime_snapshot")
        self.assertEqual(runner.events, [])
        with (
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as report_error,
        ):
            deploy.report_current_source_sha(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(report_error.exception.stage, "runtime_snapshot")

    def test_checksum_binds_exact_manifest_and_bundle_with_no_extra_records(
        self,
    ) -> None:
        original = self.checksum.read_text()
        variants = {
            "wrong_manifest": original.replace(original[:64], "f" * 64, 1),
            "wrong_bundle": original.replace(
                original.splitlines()[1][:64], "e" * 64, 1
            ),
            "extra": original + f"{'1' * 64}  extra.txt\n",
            "path": original.replace(self.bundle.name, f"../{self.bundle.name}"),
        }
        for label, content in variants.items():
            with self.subTest(label=label):
                self.checksum.write_text(content)
                with self.assertRaises(deploy.DeployError) as raised:
                    self._deploy(FakeRunner())
                self.assertEqual(raised.exception.stage, "checksum")
        self.checksum.write_text(original)

    def test_manifest_requires_exact_source_release_platform_and_schema(self) -> None:
        variants = []
        wrong_source = self._manifest_value()
        wrong_source["source_commit"] = "b" * 40
        variants.append(wrong_source)
        wrong_release = self._manifest_value()
        wrong_release["release_id"] = "different"
        variants.append(wrong_release)
        wrong_platform = self._manifest_value()
        wrong_platform["platform"] = "linux/arm64"
        variants.append(wrong_platform)
        wrong_repository = self._manifest_value()
        wrong_repository["repository"] = "ghcr.io/attacker/aperture"
        variants.append(wrong_repository)
        extra_key = self._manifest_value()
        extra_key["unexpected"] = True
        variants.append(extra_key)
        missing_artifact = self._manifest_value()
        del missing_artifact["artifacts"]["web"]
        variants.append(missing_artifact)

        for value in variants:
            with self.subTest(value=value.get("platform")):
                self._write_release_files(manifest_value=value)
                with self.assertRaises(deploy.DeployError) as raised:
                    self._deploy(FakeRunner())
                self.assertEqual(raised.exception.stage, "manifest")

    def test_bundle_rejects_traversal_symlink_and_unexpected_files(self) -> None:
        traversal = tarfile.TarInfo("../escape")
        traversal.size = 1
        symlink = tarfile.TarInfo(f"{deploy.HOSTINGER}/linked.yml")
        symlink.type = tarfile.SYMTYPE
        symlink.linkname = "/etc/shadow"
        unexpected = tarfile.TarInfo("README.md")
        unexpected.size = 1
        for label, member in (
            ("traversal", traversal),
            ("symlink", symlink),
            ("unexpected", unexpected),
        ):
            with self.subTest(label=label):
                content = self._bundle_bytes(extra_member=member, extra_content=b"x")
                self._write_release_files(bundle_bytes=content)
                with self.assertRaises(deploy.DeployError) as raised:
                    self._deploy(FakeRunner())
                self.assertEqual(raised.exception.stage, "bundle")
                self.assertFalse((self.root / "escape").exists())

    def test_bundle_rejects_highly_compressed_header_flood_incrementally(self) -> None:
        output = io.BytesIO()
        repeated = tarfile.TarInfo(deploy.SOURCE_MARKER)
        repeated.size = 0
        with tarfile.open(fileobj=output, mode="w:gz") as archive:
            for _index in range(10_000):
                archive.addfile(repeated)
        self.assertLess(len(output.getvalue()), 256 * 1024)

        destination = self.root / "header-flood"
        destination.mkdir()
        with self.assertRaises(deploy.DeployError) as raised:
            deploy.extract_bundle(output.getvalue(), destination, self.source_sha)
        self.assertEqual(raised.exception.stage, "bundle")

    def test_bundle_rejects_oversized_compressed_pax_metadata(self) -> None:
        output = io.BytesIO()
        member = tarfile.TarInfo(deploy.SOURCE_MARKER)
        member.size = 0
        member.pax_headers = {
            "comment": "x" * (deploy.MAX_DECOMPRESSED_ARCHIVE_BYTES + 1)
        }
        with tarfile.open(
            fileobj=output, mode="w:gz", format=tarfile.PAX_FORMAT
        ) as archive:
            archive.addfile(member)
        self.assertLess(len(output.getvalue()), 256 * 1024)

        destination = self.root / "pax-expansion"
        destination.mkdir()
        with self.assertRaises(deploy.DeployError) as raised:
            deploy.extract_bundle(output.getvalue(), destination, self.source_sha)
        self.assertEqual(raised.exception.stage, "bundle")

    @unittest.skipIf(os.name == "nt", "durable Unix mode ordering is Linux-only")
    def test_bundle_fchmods_final_modes_before_each_inode_fsync(self) -> None:
        destination = self.root / "mode-ordering"
        destination.mkdir()
        events: list[tuple[str, int | None]] = []
        original_fchmod = deploy.os.fchmod
        original_fsync = deploy.os.fsync

        def record_fchmod(descriptor: int, mode: int) -> None:
            events.append(("fchmod", mode))
            original_fchmod(descriptor, mode)

        def record_fsync(descriptor: int) -> None:
            events.append(("fsync", None))
            original_fsync(descriptor)

        with (
            patch.object(deploy.os, "fchmod", side_effect=record_fchmod),
            patch.object(deploy.os, "fsync", side_effect=record_fsync),
        ):
            deploy.extract_bundle(self._bundle_bytes(), destination, self.source_sha)
        self.assertEqual(len(events), 2 * len(deploy.REQUIRED_BUNDLE_FILES))
        for offset in range(0, len(events), 2):
            self.assertEqual(events[offset][0], "fchmod")
            self.assertEqual(events[offset + 1][0], "fsync")
        operations = destination / f"{deploy.HOSTINGER}/operations.sh"
        self.assertEqual(operations.stat().st_mode & 0o777, 0o755)
        self.assertEqual(
            deploy.EXECUTABLE_BUNDLE_FILES,
            {f"{deploy.HOSTINGER}/operations.sh"},
        )
        ordinary = destination / deploy.SOURCE_MARKER
        self.assertEqual(ordinary.stat().st_mode & 0o777, 0o644)

    def test_nonblocking_lock_stops_before_validation_or_commands(self) -> None:
        runner = FakeRunner()
        controller = self._deployer(runner, lock_factory=lambda: BusyLock())
        with self.assertRaises(deploy.LockUnavailable):
            controller.deploy(
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
            )
        self.assertEqual(runner.events, [])

    def test_service_lock_waits_until_shared_lock_is_released(self) -> None:
        now = [0.0]
        sleeps: list[float] = []
        attempts = [BusyLock(), BusyLock(), nullcontext()]

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        lock = deploy.RetryingProductionLock(
            self.paths.lock_file,
            self.uid,
            timeout=30,
            interval=5,
            clock=lambda: now[0],
            sleeper=sleep,
            attempt_factory=lambda: attempts.pop(0),
        )
        with lock:
            pass
        self.assertEqual(sleeps, [5, 5])
        self.assertEqual(attempts, [])

    def test_service_lock_fails_after_bounded_wait(self) -> None:
        now = [0.0]
        sleeps: list[float] = []

        def sleep(seconds: float) -> None:
            sleeps.append(seconds)
            now[0] += seconds

        lock = deploy.RetryingProductionLock(
            self.paths.lock_file,
            self.uid,
            timeout=6,
            interval=5,
            clock=lambda: now[0],
            sleeper=sleep,
            attempt_factory=lambda: BusyLock(),
        )
        with self.assertRaises(deploy.LockUnavailable):
            with lock:
                pass
        self.assertEqual(sleeps, [5, 1])

    def test_gc_retains_current_two_predecessors_and_never_removes_infra(
        self,
    ) -> None:
        current, previous, predecessor, _refs = self._prepare_gc_chain()
        stale_application_refs = {
            self.current_references[component]
            for component in deploy.APPLICATION_ARTIFACTS
        }
        runner = GCRunner(image_references=stale_application_refs)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=runner,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(
            result["protected_releases"],
            ["release-current", "release-previous", "release-predecessor"],
        )
        self.assertTrue(current.is_dir())
        self.assertTrue(previous.is_dir())
        self.assertTrue(predecessor.is_dir())
        self.assertFalse(self.current_release.exists())
        commands = dict(runner.commands)
        inventory_commands = [
            command
            for stage, command in runner.commands
            if stage == "gc_image_inventory"
        ]
        self.assertEqual(
            inventory_commands,
            [
                (
                    "docker",
                    "image",
                    "ls",
                    "--digests",
                    "--no-trunc",
                    "--format",
                    "{{.Repository}}\t{{.Tag}}\t{{.Digest}}",
                )
            ],
        )
        self.assertIn(("gc_image_inventory", 120), runner.timeouts)
        removal = commands["gc_images"]
        self.assertEqual(removal[:3], ("docker", "image", "rm"))
        for component in deploy.APPLICATION_ARTIFACTS:
            self.assertIn(
                deploy._canonical_local_image_reference(
                    self.current_references[component]
                ),
                removal,
            )
        for component in deploy.UNATTENDED_INFRA:
            self.assertNotIn(
                deploy._canonical_local_image_reference(
                    self.current_references[component]
                ),
                removal,
            )
        self.assertNotIn("prune", removal)
        self.assertNotIn("volume", removal)

    def test_gc_docker_refusal_precedes_release_or_history_deletion(self) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        runner = GCRunner(
            fail_stage="gc_images",
            image_references={
                self.current_references[component]
                for component in deploy.APPLICATION_ARTIFACTS
            },
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
            self.assertRaises(deploy.CommandFailure) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=runner,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(raised.exception.stage, "gc_images")
        self.assertTrue(self.current_release.is_dir())
        self.assertTrue((self.paths.history_dir / "baseline.json").is_file())

    def test_gc_removes_multiple_failed_attempt_refs_once_and_consumes_records(
        self,
    ) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        first_refs = self._failed_application_references("failed-one")
        second_refs = self._failed_application_references("failed-two")
        second_refs["api"] = first_refs["api"]
        first_record = self._record_attempt("failed-one", first_refs)
        second_record = self._record_attempt("failed-two", second_refs)
        local_refs = set(first_refs.values()) | set(second_refs.values())
        runner = GCRunner(image_references=local_refs)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=runner,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        removal = dict(runner.commands)["gc_images"]
        removed_refs = removal[3:]
        canonical_refs = {
            deploy._canonical_local_image_reference(reference)
            for reference in local_refs
        }
        self.assertEqual(set(removed_refs), canonical_refs)
        self.assertEqual(len(removed_refs), len(canonical_refs))
        self.assertFalse(first_record.exists())
        self.assertFalse(second_record.exists())
        self.assertEqual(result["removed_attempt_records"], 2)
        self.assertFalse((self.paths.history_dir / "failed-one.json").exists())
        self.assertFalse((self.paths.history_dir / "failed-two.json").exists())

    def test_gc_protects_shared_digests_without_pinning_attempt_capacity(self) -> None:
        current, _previous, _predecessor, current_refs = self._prepare_gc_chain()
        attempts: list[Path] = []
        aliases: set[str] = set()
        for suffix in ("one", "two", "three"):
            attempt_refs = {
                component: (
                    f"{self.repository}/{deploy.TAG_NAMES[component]}:"
                    f"failed-alias-{suffix}@{deploy._digest(current_refs[component])}"
                )
                for component in deploy.APPLICATION_ARTIFACTS
            }
            attempts.append(
                self._record_attempt(f"failed-alias-{suffix}", attempt_refs)
            )
            aliases.update(attempt_refs.values())
        runner = GCRunner(image_references=aliases)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=runner,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertNotIn("gc_images", runner.events)
        self.assertTrue(all(not attempt.exists() for attempt in attempts))
        self.assertEqual(result["removed_attempt_records"], 3)

    def test_attempt_record_count_is_bounded_before_new_pull_authority(self) -> None:
        with patch.object(deploy, "MAX_ATTEMPT_RECORDS", 1):
            self._record_attempt(
                "failed-capacity-one",
                self._failed_application_references("failed-capacity-one"),
            )
            with self.assertRaises(deploy.DeployError) as raised:
                self._record_attempt(
                    "failed-capacity-two",
                    self._failed_application_references("failed-capacity-two"),
                )
        self.assertEqual(raised.exception.stage, "attempt_capacity")
        self.assertEqual(len(tuple(self.paths.attempts_dir.glob("*.json"))), 1)

    def test_attempt_partial_enospc_is_discarded_before_retry_authorizes_pull(
        self,
    ) -> None:
        release_id = "failed-partial-write"
        references = self._failed_application_references(release_id)
        pending = deploy._attempt_pending_path(self.paths, release_id)
        final = deploy._attempt_record_path(self.paths, release_id)
        original_write = deploy.os.write
        calls = 0

        def partial_then_enospc(fd: int, content: object) -> int:
            nonlocal calls
            calls += 1
            if calls == 1:
                return original_write(fd, memoryview(content)[:11])
            raise OSError(errno.ENOSPC, "simulated full filesystem")

        with (
            patch.object(deploy.os, "write", side_effect=partial_then_enospc),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            self._record_attempt(release_id, references)
        self.assertEqual(raised.exception.stage, "attempt_record")
        self.assertTrue(pending.is_file())
        self.assertFalse(final.exists())

        record = self._record_attempt(release_id, references)
        self.assertTrue(record.is_file())
        self.assertFalse(pending.exists())

    def test_attempt_fsync_enospc_is_recoverable_on_retry(self) -> None:
        release_id = "failed-fsync"
        references = self._failed_application_references(release_id)
        pending = deploy._attempt_pending_path(self.paths, release_id)
        with (
            patch.object(
                deploy.os,
                "fsync",
                side_effect=OSError(errno.ENOSPC, "simulated fsync failure"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            self._record_attempt(release_id, references)
        self.assertEqual(raised.exception.stage, "attempt_record")
        self.assertTrue(pending.is_file())

        final = self._record_attempt(release_id, references)
        self.assertTrue(final.is_file())
        self.assertFalse(pending.exists())

    def test_attempt_linked_publication_survives_parent_fsync_crash(self) -> None:
        release_id = "failed-after-link"
        references = self._failed_application_references(release_id)
        pending = deploy._attempt_pending_path(self.paths, release_id)
        final = deploy._attempt_record_path(self.paths, release_id)
        with (
            patch.object(
                deploy,
                "_fsync_directory",
                side_effect=SystemExit("simulated crash before directory fsync"),
            ),
            self.assertRaises(SystemExit),
        ):
            self._record_attempt(release_id, references)
        self.assertTrue(pending.is_file())
        self.assertTrue(final.is_file())
        self.assertTrue(os.path.samestat(pending.stat(), final.stat()))

        record = self._record_attempt(release_id, references)
        self.assertEqual(record, final)
        self.assertTrue(final.is_file())
        self.assertFalse(pending.exists())

    def test_gc_discards_safe_partial_attempt_pending_after_reboot(self) -> None:
        release_id = "failed-reboot-pending"
        pending = deploy._attempt_pending_path(self.paths, release_id)
        pending.write_bytes(b'{"partial":')
        os.chmod(pending, 0o600)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(result["status"], "pass")
        self.assertFalse(pending.exists())

    def test_runtime_status_and_history_crash_temps_are_recovered(self) -> None:
        runtime_pending = self.paths.public_runtime.parent / ".production.env-abcdefgh"
        runtime_pending.write_bytes(b"partial secret runtime")
        os.chmod(runtime_pending, 0o600)
        with patch.object(
            deploy,
            "_current_release",
            return_value=(self.current_release, "releases/baseline"),
        ):
            reported = deploy.report_current_source_sha(
                self.paths,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
            )
        self.assertEqual(reported, self.current_source_sha)
        self.assertFalse(runtime_pending.exists())

        status_pending = self.paths.status_dir / ".crashed-status.json-abcdefgh"
        status_pending.write_bytes(b'{"partial":')
        os.chmod(status_pending, 0o600)
        history_pending = deploy._accepted_pending_path(
            self.paths, "crashed-acceptance"
        )
        history_pending.write_bytes(b'{"partial":')
        os.chmod(history_pending, 0o600)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(result["status"], "pass")
        self.assertFalse(status_pending.exists())
        self.assertFalse(history_pending.exists())

    @unittest.skipIf(os.name == "nt", "production mode checks are Linux-only")
    def test_gc_refuses_untrusted_status_crash_temp(self) -> None:
        pending = self.paths.status_dir / ".untrusted.json-abcdefgh"
        pending.write_bytes(b"partial")
        os.chmod(pending, 0o644)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(raised.exception.stage, "gc_status_pending")
        self.assertTrue(pending.exists())

    @unittest.skipIf(os.name == "nt", "production symlink semantics are Linux-only")
    def test_gc_refuses_untrusted_attempt_pending_state(self) -> None:
        release_id = "failed-untrusted-pending"
        pending = deploy._attempt_pending_path(self.paths, release_id)
        os.symlink("/etc/passwd", pending)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(raised.exception.stage, "gc_attempt")
        self.assertTrue(pending.is_symlink())

    def test_gc_removes_only_aged_unrecorded_release_directories(self) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        old_orphan = self.paths.releases_dir / "orphan-old"
        young_orphan = self.paths.releases_dir / "orphan-young"
        temporary_orphan = self.paths.releases_dir / ".incoming-orphan-temp-abcd1234"
        for orphan in (old_orphan, young_orphan, temporary_orphan):
            orphan.mkdir()
            os.chmod(orphan, 0o755)
            payload = orphan / "partial-candidate"
            payload.write_text("root-owned candidate\n", encoding="utf-8")
            os.chmod(payload, 0o600)
        now_timestamp = 2_000_000_000.0
        os.utime(
            old_orphan,
            (
                now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1,
                now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1,
            ),
        )
        os.utime(temporary_orphan, (stale := now_timestamp - 200000, stale))
        os.utime(young_orphan, (now_timestamp, now_timestamp))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                now_timestamp=now_timestamp,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertFalse(old_orphan.exists())
        self.assertFalse(temporary_orphan.exists())
        self.assertTrue(young_orphan.is_dir())
        self.assertEqual(result["removed_orphan_release_directories"], 2)

    def test_gc_release_rename_commit_survives_cleanup_crash(self) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        tombstone = deploy._release_tombstone(self.paths, self.current_release)
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
            patch.object(
                deploy,
                "_safe_remove_root_tree",
                side_effect=SystemExit("simulated crash after release rename"),
            ),
            self.assertRaises(SystemExit),
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertFalse(self.current_release.exists())
        self.assertTrue(tombstone.is_dir())
        self.assertTrue((self.paths.history_dir / "baseline.json").is_file())

        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertFalse(tombstone.exists())
        self.assertEqual(result["completed_release_tombstones"], 1)

    def test_gc_finishes_partially_deleted_release_tombstone(self) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        tombstone = deploy._release_tombstone(self.paths, self.current_release)
        os.replace(self.current_release, tombstone)
        (tombstone / ".env").unlink()
        (tombstone / deploy.SOURCE_MARKER).unlink()
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertFalse(tombstone.exists())
        self.assertTrue((self.paths.history_dir / "baseline.json").is_file())

    def test_gc_cleans_partial_payloads_but_preserves_active_job(self) -> None:
        partial_incoming = self.paths.incoming_root / "partial-upload"
        partial_incoming.mkdir()
        os.chmod(partial_incoming, 0o700)
        partial_file = partial_incoming / "partial-upload.release.json"
        partial_file.write_bytes(b"partial")
        os.chmod(partial_file, 0o600)

        temporary_job = self.paths.jobs_dir / ".job-temp-upload-123"
        temporary_job.mkdir()
        os.chmod(temporary_job, 0o700)

        active_release = "active-job"
        active_job = self.paths.jobs_dir / active_release
        active_job.mkdir()
        os.chmod(active_job, 0o700)
        active_file = active_job / f"{active_release}.source.tar.gz"
        active_file.write_bytes(b"partial")
        os.chmod(active_file, 0o600)
        deploy._write_status(
            self.paths,
            release_id=active_release,
            source_commit="d" * 40,
            state="queued",
            expected_uid=self.uid,
        )

        now_timestamp = 2_000_000_000.0
        stale = now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1
        for directory in (partial_incoming, temporary_job, active_job):
            os.utime(directory, (stale, stale))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                service_release=lambda: active_release,
                now_timestamp=now_timestamp,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertFalse(partial_incoming.exists())
        self.assertFalse(temporary_job.exists())
        self.assertTrue(active_job.is_dir())
        self.assertEqual(result["removed_incoming"], 2)
        self.assertEqual(result["removed_jobs"], 1)

    def test_gc_fails_aged_queued_job_with_no_unit_or_journal(self) -> None:
        release_id = "orphan-queued-job"
        job = self.paths.jobs_dir / release_id
        job.mkdir()
        os.chmod(job, 0o700)
        bundle = job / f"{release_id}{deploy.JOB_BUNDLE_SUFFIX}"
        bundle.write_bytes(b"abandoned partial bundle")
        os.chmod(bundle, 0o600)
        status = deploy._write_status(
            self.paths,
            release_id=release_id,
            source_commit="d" * 40,
            state="queued",
            expected_uid=self.uid,
        )
        now_timestamp = 2_000_000_000.0
        stale = now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1
        status["updated_at"] = datetime.fromtimestamp(stale, timezone.utc).isoformat()
        deploy._atomic_write(
            self.paths.status_dir / f"{release_id}.json",
            (json.dumps(status) + "\n").encode(),
            0o600,
        )
        os.utime(job, (stale, stale))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                service_release=lambda: None,
                now_timestamp=now_timestamp,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        terminal = deploy.report_deployment_status(
            self.paths,
            expected_release_id=release_id,
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(terminal["state"], "fail")
        self.assertEqual(terminal["stage"], "abandoned")
        self.assertFalse(job.exists())
        self.assertEqual(result["reconciled_abandoned_statuses"], 1)

    def test_gc_converts_aged_current_running_status_to_pass(self) -> None:
        status = deploy._write_status(
            self.paths,
            release_id="baseline",
            source_commit=self.current_source_sha,
            state="running",
            stage="deploy",
            expected_uid=self.uid,
        )
        now_timestamp = 2_000_000_000.0
        stale = now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1
        status["updated_at"] = datetime.fromtimestamp(stale, timezone.utc).isoformat()
        deploy._atomic_write(
            self.paths.status_dir / "baseline.json",
            (json.dumps(status) + "\n").encode(),
            0o600,
        )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            result = deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                service_release=lambda: None,
                now_timestamp=now_timestamp,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        terminal = deploy.report_deployment_status(
            self.paths,
            expected_release_id="baseline",
            expected_uid=self.uid,
            require_root=False,
        )
        self.assertEqual(terminal["state"], "pass")
        self.assertEqual(terminal["stage"], "complete")
        self.assertEqual(result["reconciled_abandoned_statuses"], 1)

    def test_gc_refuses_extra_abandoned_payload_entries(self) -> None:
        bad = self.paths.incoming_root / "bad-upload"
        bad.mkdir()
        os.chmod(bad, 0o700)
        extra = bad / "unexpected"
        extra.write_bytes(b"unsafe contract")
        os.chmod(extra, 0o600)
        now_timestamp = 2_000_000_000.0
        stale = now_timestamp - deploy.GC_ABANDONED_MIN_AGE_SECONDS - 1
        os.utime(bad, (stale, stale))
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                now_timestamp=now_timestamp,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(raised.exception.stage, "gc_incoming")
        self.assertTrue(bad.is_dir())

    def test_gc_lock_contention_stops_before_docker_or_deletion(self) -> None:
        runner = GCRunner()
        with (
            patch.dict(os.environ, {}, clear=True),
            self.assertRaises(deploy.LockUnavailable),
        ):
            deploy.garbage_collect(
                self.paths,
                runner=runner,
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: BusyLock(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(runner.events, [])
        self.assertTrue(self.current_release.is_dir())

    @unittest.skipIf(os.name == "nt", "production symlink semantics are Linux-only")
    def test_gc_refuses_symlink_before_tree_removal(self) -> None:
        current, _previous, _predecessor, _refs = self._prepare_gc_chain()
        os.symlink("/etc/passwd", self.current_release / "unsafe-link")
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(current, "releases/release-current"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(raised.exception.stage, "gc_release_remove")
        self.assertTrue(self.current_release.is_dir())

    def test_gc_bounds_history_and_only_old_terminal_statuses(self) -> None:
        baseline_record = json.loads(
            (self.paths.history_dir / "baseline.json").read_text()
        )
        for index in range(51):
            release_id = f"audit-{index:02d}"
            record = dict(baseline_record)
            record["release_id"] = release_id
            record["source_commit"] = hashlib.sha256(release_id.encode()).hexdigest()[
                :40
            ]
            record["accepted_at"] = f"2026-01-01T00:00:{index:02d}+00:00"
            record["previous_release"] = None
            path = self.paths.history_dir / f"{release_id}.json"
            path.write_text(json.dumps(record) + "\n", encoding="utf-8")
            os.chmod(path, 0o600)
            status = deploy._write_status(
                self.paths,
                release_id=release_id,
                source_commit=record["source_commit"],
                state="fail",
                stage="complete",
                expected_uid=self.uid,
            )
            status["updated_at"] = f"2026-01-01T00:00:{index:02d}+00:00"
            deploy._atomic_write(
                self.paths.status_dir / f"{release_id}.json",
                (json.dumps(status) + "\n").encode(),
                0o600,
            )
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                now_timestamp=2_000_000_000,
                disk_usage=lambda _path: SimpleNamespace(free=10 * 1024**3),
            )
        self.assertEqual(len(tuple(self.paths.history_dir.glob("*.json"))), 50)
        self.assertEqual(len(tuple(self.paths.status_dir.glob("*.json"))), 50)

    def test_gc_reports_low_disk_after_safe_cleanup_attempt(self) -> None:
        with (
            patch.dict(os.environ, {}, clear=True),
            patch.object(
                deploy,
                "_current_release",
                return_value=(self.current_release, "releases/baseline"),
            ),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            deploy.garbage_collect(
                self.paths,
                runner=GCRunner(),
                expected_uid=self.uid,
                require_root=False,
                lock_factory=lambda: nullcontext(),
                disk_usage=lambda _path: SimpleNamespace(free=0),
            )
        self.assertEqual(raised.exception.stage, "low_disk")

    def test_storage_and_other_infrastructure_digest_drift_are_refused(self) -> None:
        for component, digit in (
            ("storage", "e"),
            ("caddy", "f"),
            ("node_exporter", "9"),
        ):
            with self.subTest(component=component):
                digests = dict(self.target_digests)
                digests[component] = "sha256:" + digit * 64
                self._write_release_files(manifest_value=self._manifest_value(digests))
                runner = FakeRunner()
                with self.assertRaises(deploy.DeployError) as raised:
                    self._deploy(runner)
                self.assertEqual(raised.exception.stage, f"{component}_drift")
                self.assertEqual(runner.events, [])

    def test_platform_and_root_executed_support_file_drift_is_refused(self) -> None:
        for filename in (
            f"{deploy.PRIVATE_STUDIO}/Caddyfile",
            deploy.PUBLIC_EDGE_SMOKE,
        ):
            with self.subTest(filename=filename):
                files = dict(self.source_files)
                files[filename] = b"changed root-executed content\n"
                self._write_release_files(bundle_bytes=self._bundle_bytes(files=files))
                runner = FakeRunner()
                with self.assertRaises(deploy.DeployError) as raised:
                    self._deploy(runner)
                self.assertEqual(raised.exception.stage, "platform_drift")
                self.assertEqual(runner.events, [])

    def test_success_orders_backup_before_pulls_and_retains_infrastructure_refs(
        self,
    ) -> None:
        runner = FakeRunner()
        switches: list[str] = []
        result = self._deploy(runner, switch_events=switches)
        self.assertEqual(result["status"], "pass")
        self.assertLess(
            runner.events.index("predeploy_backup"), runner.events.index("pull_api")
        )
        self.assertLess(
            runner.events.index("inspect_images"), runner.events.index("public_rollout")
        )
        self.assertEqual(
            runner.events[-5:],
            [
                "public_rollout",
                "private_rollout",
                "target_preflight",
                "target_coupling",
                "target_public_smoke",
            ],
        )
        smoke_environment = dict(runner.environments)["target_public_smoke"]
        self.assertEqual(
            smoke_environment,
            {"SMOKE_WEB_ORIGIN": "https://apertures.online"},
        )
        commands = dict(runner.commands)
        self.assertEqual(commands["predeploy_backup"][0], "/bin/sh")
        self.assertTrue(commands["predeploy_backup"][1].endswith("operations.sh"))
        self.assertEqual(commands["predeploy_backup"][-1], "backup")
        self.assertEqual(commands["target_preflight"][-1], "preflight")
        timeouts = dict(runner.timeouts)
        self.assertEqual(timeouts["pull_api"], 300)
        self.assertEqual(timeouts["public_rollout"], 720)
        self.assertEqual(timeouts["target_public_smoke"], 120)
        self.assertEqual(len(switches), 1)
        active = deploy._runtime_images(
            self.paths.public_runtime.read_bytes(), stage="test"
        )
        for component in deploy.APPLICATION_ARTIFACTS:
            self.assertEqual(active[component], self.target_references[component])
        for component in deploy.UNATTENDED_INFRA:
            self.assertEqual(active[component], self.current_references[component])
        self.assertEqual(
            deploy._dotenv_values(
                self.paths.private_runtime.read_bytes(), stage="test"
            )["CADDY_IMAGE"],
            self.current_references["caddy"],
        )
        history_path = self.paths.history_dir / f"{self.release_id}.json"
        self.assertEqual(
            oct(history_path.stat().st_mode & 0o777),
            "0o666" if os.name == "nt" else "0o600",
        )
        history = json.loads(history_path.read_text())
        self.assertEqual(history["status"], "accepted")
        self.assertEqual(
            history["effective_runtime_references"]["storage"],
            self.current_references["storage"],
        )
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_failure_after_live_mutation_restores_env_current_and_redeploys(
        self,
    ) -> None:
        runner = FakeRunner(fail_stage="target_preflight")
        switches: list[str] = []
        with self.assertRaises(deploy.DeploymentExecutionError) as raised:
            self._deploy(runner, switch_events=switches)
        error = raised.exception
        self.assertEqual(error.stage, "target_preflight")
        self.assertEqual(error.recovery_status, "completed")
        self.assertIsNone(error.recovery_failure_stage)
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)
        self.assertEqual(self.paths.private_runtime.read_bytes(), self.current_private)
        self.assertEqual(switches[-1], "releases/baseline")
        self.assertEqual(
            runner.events[-10:],
            [
                "recovery_compose_contract",
                "recovery_migrate_remove",
                "recovery_stateful_rollout",
                "recovery_initializer_rollout",
                "recovery_application_rollout",
                "recovery_edge_rollout",
                "recovery_private_rollout",
                "recovery_preflight",
                "recovery_coupling",
                "recovery_public_smoke",
            ],
        )
        self.assertNotIn("schema_rollback", " ".join(runner.events))
        self.assertFalse((self.paths.history_dir / f"{self.release_id}.json").exists())
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_forward_migration_smoke_failure_recovers_without_old_migrate(
        self,
    ) -> None:
        runner = MigrationTrackingRunner(
            fail_stage="target_public_smoke",
            target_migrate_state="exited",
        )
        with self.assertRaises(deploy.DeploymentExecutionError) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "target_public_smoke")
        self.assertEqual(raised.exception.recovery_status, "completed")

        # The ordinary target rollout remains a full Compose rollout, so this
        # scenario models a successful forward migration followed by smoke
        # failure. Compensation never performs another migration.
        commands = dict(runner.commands)
        self.assertNotIn("--no-deps", commands["public_rollout"])
        self.assertEqual(
            commands["recovery_compose_contract"][-5:],
            ("--profile", "operations", "config", "--format", "json"),
        )
        self.assertEqual(
            commands["recovery_migrate_remove"][-4:],
            ("rm", "--stop", "--force", "migrate"),
        )
        self.assertEqual(runner.migrate_remove_saw_state, "exited")
        self.assertLess(
            runner.events.index("recovery_migrate_remove"),
            runner.events.index("recovery_application_rollout"),
        )

        phase_services = {
            "recovery_stateful_rollout": deploy.RECOVERY_STATEFUL_SERVICES,
            "recovery_initializer_rollout": deploy.RECOVERY_INITIALIZER_SERVICES,
            "recovery_application_rollout": deploy.RECOVERY_APPLICATION_SERVICES,
            "recovery_edge_rollout": deploy.RECOVERY_EDGE_SERVICES,
        }
        forbidden = deploy.RECOVERY_FORBIDDEN_SERVICES | set(
            deploy.EXPECTED_OPERATION_SERVICES
        )
        for stage, services in phase_services.items():
            command = commands[stage]
            self.assertIn("--no-deps", command)
            self.assertTrue(command[-len(services) :] == tuple(services))
            self.assertFalse(set(command) & forbidden)
        initializer = commands["recovery_initializer_rollout"]
        self.assertNotIn("-d", initializer)
        self.assertNotIn("--wait", initializer)
        self.assertEqual(
            initializer[-3:],
            ("--exit-code-from", "minio-init", "minio-init"),
        )
        for stage in (
            "recovery_stateful_rollout",
            "recovery_application_rollout",
            "recovery_edge_rollout",
        ):
            self.assertIn("--wait", commands[stage])
        self.assertNotIn("recovery_public_rollout", runner.events)
        self.assertTrue(runner.target_api_image_collectible)

    def test_timed_out_live_target_migration_is_removed_before_old_apps(
        self,
    ) -> None:
        runner = MigrationTrackingRunner(
            fail_stage="public_rollout",
            target_migrate_state="running",
        )
        with self.assertRaises(deploy.DeploymentExecutionError) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "public_rollout")
        self.assertEqual(raised.exception.recovery_status, "completed")
        self.assertEqual(runner.migrate_remove_saw_state, "running")
        self.assertLess(
            runner.events.index("recovery_migrate_remove"),
            runner.events.index("recovery_application_rollout"),
        )
        self.assertTrue(runner.target_api_image_collectible)

    def test_recovery_refuses_inexact_rendered_compose_before_mutation(
        self,
    ) -> None:
        def omit_profiled_service(value: dict[str, object]) -> None:
            services = value["services"]
            assert isinstance(services, dict)
            services.pop("backup")

        runner = FakeRunner(
            fail_stage="target_public_smoke",
            recovery_model_mutator=omit_profiled_service,
        )
        with self.assertRaises(deploy.DeploymentExecutionError) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "target_public_smoke")
        self.assertEqual(raised.exception.recovery_status, "failed")
        self.assertEqual(
            raised.exception.recovery_failure_stage,
            "recovery_compose_contract",
        )
        self.assertNotIn("recovery_migrate_remove", runner.events)
        self.assertNotIn("recovery_application_rollout", runner.events)
        self.assertTrue(self.paths.transaction_dir.is_dir())

    def test_failure_immediately_after_acceptance_removes_rolled_back_record(
        self,
    ) -> None:
        original_remove = deploy._remove_transaction
        calls = 0

        def fail_once(paths: deploy.DeployPaths, expected_uid: int) -> None:
            nonlocal calls
            calls += 1
            if calls == 1:
                raise deploy.DeployError("transaction_cleanup")
            original_remove(paths, expected_uid)

        with (
            patch.object(deploy, "_remove_transaction", side_effect=fail_once),
            self.assertRaises(deploy.DeploymentExecutionError) as raised,
        ):
            self._deploy(FakeRunner())
        self.assertEqual(raised.exception.stage, "transaction_cleanup")
        self.assertEqual(raised.exception.recovery_status, "completed")
        self.assertEqual(calls, 2)
        self.assertFalse((self.paths.history_dir / f"{self.release_id}.json").exists())
        self.assertFalse(
            deploy._accepted_pending_path(self.paths, self.release_id).exists()
        )
        self.assertFalse(self.paths.transaction_dir.exists())
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)

    def test_acceptance_cleanup_fsync_failure_retains_journal_fail_closed(
        self,
    ) -> None:
        original_remove = deploy._remove_transaction
        original_fsync = deploy._fsync_directory
        remove_calls = 0
        history_fsyncs = 0

        def fail_remove_once(paths: deploy.DeployPaths, expected_uid: int) -> None:
            nonlocal remove_calls
            remove_calls += 1
            if remove_calls == 1:
                raise deploy.DeployError("transaction_cleanup")
            original_remove(paths, expected_uid)

        def fail_history_cleanup(path: Path) -> None:
            nonlocal history_fsyncs
            if path == self.paths.history_dir:
                history_fsyncs += 1
                if history_fsyncs == 3:
                    raise OSError(errno.ENOSPC, "simulated history fsync failure")
            original_fsync(path)

        with (
            patch.object(deploy, "_remove_transaction", side_effect=fail_remove_once),
            patch.object(deploy, "_fsync_directory", side_effect=fail_history_cleanup),
            self.assertRaises(deploy.DeploymentExecutionError) as raised,
        ):
            self._deploy(FakeRunner())
        self.assertEqual(raised.exception.recovery_status, "failed")
        self.assertEqual(raised.exception.recovery_failure_stage, "history_cleanup")
        self.assertFalse((self.paths.history_dir / f"{self.release_id}.json").exists())
        self.assertTrue(self.paths.transaction_dir.is_dir())

        result, _switches = self._run_successful_boot_recovery()
        self.assertEqual(result, 0)
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_transaction_cleanup_fsync_fault_never_leaves_false_acceptance(
        self,
    ) -> None:
        original_publish = deploy._publish_accepted_record
        original_fsync = deploy._fsync_directory
        publication_complete = False
        cleanup_fsyncs = 0

        def publish_then_arm(*args: object, **kwargs: object) -> None:
            nonlocal publication_complete
            original_publish(*args, **kwargs)
            publication_complete = True

        def fail_cleanup_fsync(path: Path) -> None:
            nonlocal cleanup_fsyncs
            if publication_complete and path == self.paths.transaction_dir.parent:
                cleanup_fsyncs += 1
                if cleanup_fsyncs == 1:
                    raise OSError(
                        errno.ENOSPC, "simulated journal commit fsync failure"
                    )
            original_fsync(path)

        with (
            patch.object(
                deploy, "_publish_accepted_record", side_effect=publish_then_arm
            ),
            patch.object(deploy, "_fsync_directory", side_effect=fail_cleanup_fsync),
            self.assertRaises(deploy.DeploymentExecutionError) as raised,
        ):
            self._deploy(FakeRunner())
        self.assertEqual(raised.exception.stage, "transaction_cleanup")
        self.assertFalse((self.paths.history_dir / f"{self.release_id}.json").exists())
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)
        self.assertFalse(self.paths.transaction_dir.exists())

    def test_transaction_tombstone_delete_fsync_fault_removes_acceptance(
        self,
    ) -> None:
        original_publish = deploy._publish_accepted_record
        original_fsync = deploy._fsync_directory
        publication_complete = False
        cleanup_fsyncs = 0

        def publish_then_arm(*args: object, **kwargs: object) -> None:
            nonlocal publication_complete
            original_publish(*args, **kwargs)
            publication_complete = True

        def fail_second_cleanup_fsync(path: Path) -> None:
            nonlocal cleanup_fsyncs
            if publication_complete and path == self.paths.transaction_dir.parent:
                cleanup_fsyncs += 1
                if cleanup_fsyncs == 2:
                    raise OSError(
                        errno.ENOSPC, "simulated tombstone delete fsync failure"
                    )
            original_fsync(path)

        with (
            patch.object(
                deploy, "_publish_accepted_record", side_effect=publish_then_arm
            ),
            patch.object(
                deploy, "_fsync_directory", side_effect=fail_second_cleanup_fsync
            ),
            self.assertRaises(deploy.DeploymentExecutionError) as raised,
        ):
            self._deploy(FakeRunner())
        self.assertEqual(raised.exception.stage, "transaction_cleanup")
        self.assertFalse((self.paths.history_dir / f"{self.release_id}.json").exists())
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)
        self.assertFalse(self.paths.transaction_dir.exists())
        self.assertFalse(deploy._transaction_tombstone(self.paths).exists())

    def test_pre_live_failure_removes_only_new_candidate_without_compensation(
        self,
    ) -> None:
        runner = FakeRunner(fail_stage="predeploy_backup")
        with self.assertRaises(deploy.CommandFailure) as raised:
            self._deploy(runner)
        self.assertEqual(raised.exception.stage, "predeploy_backup")
        self.assertFalse((self.paths.releases_dir / self.release_id).exists())
        self.assertTrue(self.current_release.is_dir())
        self.assertEqual(self.paths.public_runtime.read_bytes(), self.current_public)
        self.assertEqual(self.paths.private_runtime.read_bytes(), self.current_private)
        self.assertFalse(any(event.startswith("recovery_") for event in runner.events))

    def test_failed_pull_leaves_durable_exact_application_attempt_record(
        self,
    ) -> None:
        runner = FakeRunner(fail_stage="pull_media_worker")
        with self.assertRaises(deploy.CommandFailure):
            self._deploy(runner)
        record_path = self.paths.attempts_dir / f"{self.release_id}.json"
        self.assertTrue(record_path.is_file())
        if os.name != "nt":
            self.assertEqual(record_path.stat().st_mode & 0o777, 0o600)
        record = deploy._read_attempt_record(
            self.paths,
            self.release_id,
            self.uid,
            stage="attempt_record",
        )
        self.assertEqual(
            record["application_references"],
            {
                component: self.target_references[component]
                for component in deploy.APPLICATION_ARTIFACTS
            },
        )
        self.assertNotIn("caddy", record["application_references"])
        self.assertFalse((self.paths.releases_dir / self.release_id).exists())

    def test_root_requirement_precedes_staged_input_processing(self) -> None:
        runner = FakeRunner()
        controller = deploy.Deployer(
            self.paths,
            runner=runner,
            expected_uid=self.uid,
            require_root=True,
            lock_factory=lambda: nullcontext(),
        )
        with (
            patch.object(deploy, "_effective_uid", return_value=1234),
            self.assertRaises(deploy.DeployError) as raised,
        ):
            controller.deploy(
                bundle=self.bundle,
                manifest=self.manifest,
                checksum=self.checksum,
                expected_current_source_sha=self.current_source_sha,
                expected_source_sha=self.source_sha,
                expected_release_id=self.release_id,
            )
        self.assertEqual(raised.exception.stage, "root")
        self.assertEqual(runner.events, [])

    def test_installer_and_installed_controller_contract_is_executable(self) -> None:
        controller = ROOT / "deploy_release.py"
        installer = ROOT / "install_ci_deploy.sh"
        self.assertEqual(controller.read_text().splitlines()[0], "#!/usr/bin/python3")
        self.assertNotIn(b"\r", controller.read_bytes())
        script = installer.read_text()
        self.assertTrue(script.startswith("#!/bin/sh\nset -eu\n"))
        self.assertIn("ACCOUNT_HOME=/var/lib/aperture-deploy", script)
        self.assertIn("INCOMING_ROOT=$ACCOUNT_HOME/incoming", script)
        self.assertIn("CONTROLLER_DIR=/usr/local/sbin", script)
        self.assertIn("CONTROLLER=$CONTROLLER_DIR/aperture-deploy-release", script)
        self.assertIn("install -o root -g root -m 0755", script)
        self.assertIn('chmod 0444 "$key_temp"', script)
        self.assertIn('if [ "$(id -G "$ACCOUNT")" != "$account_gid" ]', script)
        self.assertIn("password must remain locked", script)
        self.assertIn('require_existing_directory "$ACCOUNT_HOME" 0 0 755', script)
        self.assertIn('require_existing_directory "$ACCOUNT_HOME/.ssh" 0 0 755', script)
        self.assertIn('require_existing_directory "$INCOMING_ROOT"', script)
        self.assertIn("/opt/aperture/deploy-jobs", script)
        self.assertIn("/opt/aperture/deploy-status", script)
        self.assertIn("/opt/aperture/deploy-attempts", script)
        self.assertIn(
            "require_existing_directory /opt/aperture/deploy-attempts 0 0 700",
            script,
        )
        self.assertIn("/usr/bin/systemd-run", script)
        self.assertIn(
            "ConditionPathIsDirectory=|/opt/aperture/deploy-transaction", script
        )
        self.assertIn("deploy-transaction.completed", script)
        self.assertIn("After=docker.service network-online.target", script)
        self.assertIn("ExecStart=$CONTROLLER --recover", script)
        self.assertIn("Restart=on-failure", script)
        self.assertIn("RuntimeMaxSec=3h", script)
        self.assertIn("ReadWritePaths=/opt/aperture -/var/lib/aperture", script)
        self.assertIn("systemctl enable aperture-deploy-recovery.service", script)
        self.assertIn("ExecStart=$CONTROLLER --gc", script)
        self.assertIn(
            "ConditionPathIsRegularFile=/etc/aperture/production-launch-enabled",
            script,
        )
        self.assertIn("ConditionPathExists=/opt/aperture/current", script)
        self.assertIn("OnCalendar=daily", script)
        self.assertIn("RandomizedDelaySec=1h", script)
        self.assertIn("Persistent=yes", script)
        self.assertIn("Unit=aperture-deploy-gc.service", script)
        self.assertIn("systemctl enable --now aperture-deploy-gc.timer", script)
        self.assertIn("NOPASSWD: $CONTROLLER", script)
        self.assertIn(
            "deployment controller must use an exact LF-only Python shebang", script
        )
        self.assertEqual(
            deploy.EXPECTED_REPOSITORY,
            "ghcr.io/hlkstudios-ui/aperture",
        )
        self.assertNotIn("/dev/null /var/lock/aperture-production-deploy.lock", script)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertEqual(readme.count("production-deploy.lock"), 3)
        self.assertEqual(readme.count("/opt/aperture/current/"), 3)
        self.assertNotIn("/var/lock/aperture-maintenance.lock", readme)
        self.assertNotIn("/var/lock/aperture-replication.lock", readme)
        self.assertNotIn("/var/lock/aperture-backup.lock", readme)
        shell = shutil.which("sh")
        if shell is not None:
            completed = subprocess.run(
                [shell, "-n", str(installer)],
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)


if __name__ == "__main__":
    unittest.main()
