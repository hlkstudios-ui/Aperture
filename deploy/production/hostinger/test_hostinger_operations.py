import importlib.util
import os
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


rollback = module("hostinger_rollback", "hostinger_rollback.py")
restore = module("hostinger_validate_restore", "validate_restore.py")
replication = module("hostinger_validate_replication", "validate_replication.py")
topology = module("hostinger_validate_topology", "validate_topology.py")
pinning = module("hostinger_pin_release", "pin_release.py")
env_reader = module("hostinger_read_env", "read_env.py")


class HostingerRollbackTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.credentials = directory / "credentials.env"
        self.rollback_input = directory / "rollback.env"
        self.current = {
            "api": "registry.example/aperture-api@sha256:" + "a" * 64,
            "web": "registry.example/aperture-web@sha256:" + "b" * 64,
            "backup": "registry.example/aperture-backup@sha256:" + "c" * 64,
        }
        self.target = {
            "api": "registry.example/aperture-api@sha256:" + "d" * 64,
            "web": "registry.example/aperture-web@sha256:" + "e" * 64,
            "backup": "registry.example/aperture-backup@sha256:" + "f" * 64,
        }
        self.credentials.write_text(
            f"API_IMAGE={self.current['api']}\nWEB_IMAGE={self.current['web']}\n"
            f"BACKUP_IMAGE={self.current['backup']}\nSECRET=preserved\n"
        )
        os.chmod(self.credentials, 0o600)
        self.rollback_input.write_text(
            f"HOSTINGER_ROLLBACK_API_IMAGE={self.target['api']}\n"
            f"HOSTINGER_ROLLBACK_WEB_IMAGE={self.target['web']}\n"
            f"HOSTINGER_ROLLBACK_BACKUP_IMAGE={self.target['backup']}\n"
            f"ROLLBACK_CONFIRMATION={rollback.CONFIRMATION}\n"
        )
        self.constants = patch.multiple(
            rollback, CREDENTIALS=self.credentials, ROLLBACK_INPUT=self.rollback_input
        )
        self.constants.start()

    def tearDown(self):
        self.constants.stop()
        self.temporary.cleanup()

    def test_dummy_never_inspects_images(self):
        with patch.object(rollback, "inspect_images", side_effect=AssertionError):
            self.assertEqual(rollback.run("dummy")["status"], "pass")

    def test_inspect_requires_all_target_images(self):
        with patch.object(rollback, "inspect_images") as inspect:
            result = rollback.run("inspect")
        inspect.assert_called_once_with(self.target)
        self.assertEqual(result["current_digests"]["api"], "sha256:" + "a" * 64)

    def test_execute_requires_exact_confirmation(self):
        self.rollback_input.write_text(
            f"HOSTINGER_ROLLBACK_API_IMAGE={self.target['api']}\n"
            f"HOSTINGER_ROLLBACK_WEB_IMAGE={self.target['web']}\n"
            f"HOSTINGER_ROLLBACK_BACKUP_IMAGE={self.target['backup']}\n"
        )
        with self.assertRaisesRegex(RuntimeError, "does not authorize"):
            rollback.run("execute")

    def test_atomic_tag_replacement_preserves_secrets_and_mode(self):
        rollback.replace_release(self.credentials, self.current, self.target)
        self.assertIn("SECRET=preserved", self.credentials.read_text())
        self.assertIn(f"API_IMAGE={self.target['api']}", self.credentials.read_text())
        self.assertIn(f"WEB_IMAGE={self.target['web']}", self.credentials.read_text())
        self.assertIn(f"BACKUP_IMAGE={self.target['backup']}", self.credentials.read_text())
        self.assertEqual(self.credentials.stat().st_mode & 0o777, 0o600)

    def test_failure_output_does_not_expose_exception_details(self):
        secret = "never-print-this-secret"
        with (
            patch.object(rollback, "run", side_effect=RuntimeError(secret)),
            patch.object(sys, "argv", ["hostinger_rollback.py", "--mode", "inspect"]),
            patch("sys.stderr") as stderr,
        ):
            self.assertEqual(rollback.main(), 1)
        output = "".join(call.args[0] for call in stderr.write.call_args_list)
        self.assertNotIn(secret, output)
        self.assertEqual(json.loads(output), {"event": "rollback.failed", "status": "fail"})


class HostingerRestoreTests(unittest.TestCase):
    def test_dummy_restore_is_rejected_before_container_start(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            restore.validate(restore.load(ROOT / "restore.example.env"))

    def test_valid_restore_is_isolated_and_https(self):
        values = {
            "RESTORE_DATABASE_URL": "postgresql://user:secret@db/aperture_restore_rehearsal?sslmode=require",
            "RESTORE_MANIFEST_KEY": "postgres/2026/08/18/example.manifest.json",
            "RESTORE_CONFIRMATION": "RESTORE_TO_ISOLATED_EMPTY_DATABASE",
            "BACKUP_S3_ENDPOINT": "https://s3.example.com",
            "BACKUP_S3_REGION": "region-1",
            "BACKUP_S3_BUCKET": "backups",
            "BACKUP_S3_ACCESS_KEY": "read-only",
            "BACKUP_S3_SECRET_KEY": "secret",
        }
        restore.validate(values)
        values["RESTORE_DATABASE_URL"] = "postgresql://user:secret@db/aperture"
        with self.assertRaisesRegex(ValueError, "aperture_restore_"):
            restore.validate(values)


class HostingerReplicationTests(unittest.TestCase):
    def test_dummy_replication_is_rejected_before_copy(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            replication.validate(replication.load(ROOT / "credentials.example.env"))

    def test_replica_must_be_remote_https_and_separate_bucket(self):
        values = {
            "S3_BUCKET": "production-media",
            "REPLICA_S3_ENDPOINT": "https://objects.example.com",
            "REPLICA_S3_BUCKET": "production-media-replica",
            "REPLICA_S3_ACCESS_KEY": "replica-key",
            "REPLICA_S3_SECRET_KEY": "replica-secret",
        }
        replication.validate(values)
        values["REPLICA_S3_ENDPOINT"] = "http://minio:9000"
        with self.assertRaisesRegex(ValueError, "HTTPS origin"):
            replication.validate(values)


class HostingerTopologyTests(unittest.TestCase):
    def test_rendered_topology_has_mandatory_hardening(self):
        rendered = os.environ.get("HOSTINGER_RENDERED_COMPOSE")
        if not rendered:
            self.skipTest("HOSTINGER_RENDERED_COMPOSE was not supplied")
        topology.validate(json.loads(Path(rendered).read_text()))


class HostingerReleaseTests(unittest.TestCase):
    def test_release_pinning_replaces_only_three_images_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            path.write_text(
                "API_IMAGE=dummy.registry/api@sha256:" + "0" * 64 + "\n"
                "WEB_IMAGE=dummy.registry/web@sha256:" + "0" * 64 + "\n"
                "BACKUP_IMAGE=dummy.registry/backup@sha256:" + "0" * 64 + "\n"
                "SECRET=preserved\n"
            )
            os.chmod(path, 0o600)
            images = {
                "api": "registry.example/aperture/api@sha256:" + "a" * 64,
                "web": "registry.example/aperture/web@sha256:" + "b" * 64,
                "backup": "registry.example/aperture/backup@sha256:" + "c" * 64,
            }
            pinning.pin(path, images)
            self.assertIn("SECRET=preserved", path.read_text())
            self.assertIn(f"API_IMAGE={images['api']}", path.read_text())
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_dotenv_reader_returns_shell_syntax_literally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.env"
            path.write_text("SAFE=$(touch /tmp/must-not-execute)\n")
            self.assertEqual(env_reader.read(path, "SAFE"), "$(touch /tmp/must-not-execute)")


if __name__ == "__main__":
    unittest.main()
