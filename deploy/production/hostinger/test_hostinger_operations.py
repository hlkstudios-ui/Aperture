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
            "media_worker": "registry.example/aperture-media-worker@sha256:" + "d" * 64,
            "web": "registry.example/aperture-web@sha256:" + "b" * 64,
            "backup": "registry.example/aperture-backup@sha256:" + "c" * 64,
            "caddy": "registry.example/aperture-caddy@sha256:" + "e" * 64,
            "storage": "registry.example/aperture-storage@sha256:" + "f" * 64,
            "node_exporter": (
                "registry.example/aperture-node-exporter@sha256:" + "9" * 64
            ),
            "blackbox": "registry.example/aperture-blackbox@sha256:" + "8" * 64,
        }
        self.target = {
            "api": "registry.example/aperture-api@sha256:" + "1" * 64,
            "media_worker": "registry.example/aperture-media-worker@sha256:" + "4" * 64,
            "web": "registry.example/aperture-web@sha256:" + "2" * 64,
            "backup": "registry.example/aperture-backup@sha256:" + "3" * 64,
            "caddy": "registry.example/aperture-caddy@sha256:" + "5" * 64,
            "storage": "registry.example/aperture-storage@sha256:" + "6" * 64,
            "node_exporter": (
                "registry.example/aperture-node-exporter@sha256:" + "7" * 64
            ),
            "blackbox": "registry.example/aperture-blackbox@sha256:" + "8" * 64,
        }
        self.credentials.write_text(
            f"API_IMAGE={self.current['api']}\n"
            f"MEDIA_WORKER_IMAGE={self.current['media_worker']}\n"
            f"WEB_IMAGE={self.current['web']}\n"
            f"BACKUP_IMAGE={self.current['backup']}\n"
            f"CADDY_IMAGE={self.current['caddy']}\n"
            f"STORAGE_IMAGE={self.current['storage']}\n"
            f"NODE_EXPORTER_IMAGE={self.current['node_exporter']}\n"
            f"BLACKBOX_IMAGE={self.current['blackbox']}\nSECRET=preserved\n"
        )
        os.chmod(self.credentials, 0o600)
        self.rollback_input.write_text(
            f"HOSTINGER_ROLLBACK_API_IMAGE={self.target['api']}\n"
            f"HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE={self.target['media_worker']}\n"
            f"HOSTINGER_ROLLBACK_WEB_IMAGE={self.target['web']}\n"
            f"HOSTINGER_ROLLBACK_BACKUP_IMAGE={self.target['backup']}\n"
            f"HOSTINGER_ROLLBACK_CADDY_IMAGE={self.target['caddy']}\n"
            f"HOSTINGER_ROLLBACK_STORAGE_IMAGE={self.target['storage']}\n"
            f"HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE={self.target['node_exporter']}\n"
            f"HOSTINGER_ROLLBACK_BLACKBOX_IMAGE={self.target['blackbox']}\n"
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
            f"HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE={self.target['media_worker']}\n"
            f"HOSTINGER_ROLLBACK_WEB_IMAGE={self.target['web']}\n"
            f"HOSTINGER_ROLLBACK_BACKUP_IMAGE={self.target['backup']}\n"
            f"HOSTINGER_ROLLBACK_CADDY_IMAGE={self.target['caddy']}\n"
            f"HOSTINGER_ROLLBACK_STORAGE_IMAGE={self.target['storage']}\n"
            f"HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE={self.target['node_exporter']}\n"
            f"HOSTINGER_ROLLBACK_BLACKBOX_IMAGE={self.target['blackbox']}\n"
        )
        with self.assertRaisesRegex(RuntimeError, "does not authorize"):
            rollback.run("execute")

    def test_rollback_rejects_a_worker_that_reuses_the_api_digest(self):
        shared_digest = self.target["api"].rsplit("@sha256:", 1)[1]
        self.rollback_input.write_text(
            f"HOSTINGER_ROLLBACK_API_IMAGE={self.target['api']}\n"
            "HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE="
            f"registry.example/aperture-media-worker@sha256:{shared_digest}\n"
            f"HOSTINGER_ROLLBACK_WEB_IMAGE={self.target['web']}\n"
            f"HOSTINGER_ROLLBACK_BACKUP_IMAGE={self.target['backup']}\n"
            f"HOSTINGER_ROLLBACK_CADDY_IMAGE={self.target['caddy']}\n"
            f"HOSTINGER_ROLLBACK_STORAGE_IMAGE={self.target['storage']}\n"
            f"HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE={self.target['node_exporter']}\n"
            f"HOSTINGER_ROLLBACK_BLACKBOX_IMAGE={self.target['blackbox']}\n"
        )
        with self.assertRaisesRegex(ValueError, "image digests must be distinct"):
            rollback.run("inspect")

    def test_atomic_tag_replacement_preserves_secrets_and_mode(self):
        rollback.replace_release(self.credentials, self.current, self.target)
        self.assertIn("SECRET=preserved", self.credentials.read_text())
        self.assertIn(f"API_IMAGE={self.target['api']}", self.credentials.read_text())
        self.assertIn(
            f"MEDIA_WORKER_IMAGE={self.target['media_worker']}",
            self.credentials.read_text(),
        )
        self.assertIn(f"WEB_IMAGE={self.target['web']}", self.credentials.read_text())
        self.assertIn(
            f"BACKUP_IMAGE={self.target['backup']}", self.credentials.read_text()
        )
        self.assertIn(
            f"CADDY_IMAGE={self.target['caddy']}", self.credentials.read_text()
        )
        self.assertIn(
            f"STORAGE_IMAGE={self.target['storage']}", self.credentials.read_text()
        )
        self.assertIn(
            f"NODE_EXPORTER_IMAGE={self.target['node_exporter']}",
            self.credentials.read_text(),
        )
        self.assertIn(
            f"BLACKBOX_IMAGE={self.target['blackbox']}", self.credentials.read_text()
        )
        if os.name != "nt":
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
        self.assertEqual(
            json.loads(output), {"event": "rollback.failed", "status": "fail"}
        )


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
        valid = {
            "S3_BUCKET": "production-media",
            "REPLICA_S3_ENDPOINT": "https://objects.example.com",
            "REPLICA_S3_BUCKET": "production-media-replica",
            "REPLICA_S3_ACCESS_KEY": "replica-key",
            "REPLICA_S3_SECRET_KEY": "replica-secret",
        }
        replication.validate(valid)
        for endpoint in (
            "http://minio:9000",
            "https://objects.example.com/bucket",
            "https://objects.example.com?bucket=value",
            "https://access:secret@objects.example.com",
            "https://objects.example.com:not-a-port",
        ):
            with self.subTest(endpoint=endpoint):
                values = {**valid, "REPLICA_S3_ENDPOINT": endpoint}
                with self.assertRaisesRegex(ValueError, "HTTPS origin"):
                    replication.validate(values)

        values = {**valid, "REPLICA_S3_ENDPOINT": "https://minio"}
        with self.assertRaisesRegex(ValueError, "outside the Hostinger VPS"):
            replication.validate(values)

    def test_replica_job_only_copies_objects_to_preprovisioned_bucket(self):
        compose = (ROOT / "compose.yml").read_text()
        service = compose.split("  replicate-media:", 1)[1].split(
            "  node-exporter:", 1
        )[0]

        self.assertEqual(service.count("--api S3v4"), 2)
        self.assertIn("mc mirror --overwrite", service)
        for forbidden in (
            "mc mb",
            "mc version",
            "mc anonymous",
            "--preserve",
            "--remove",
            "ACL",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, service)


class HostingerTopologyTests(unittest.TestCase):
    def test_rendered_topology_has_mandatory_hardening(self):
        rendered = os.environ.get("HOSTINGER_RENDERED_COMPOSE")
        if not rendered:
            self.skipTest("HOSTINGER_RENDERED_COMPOSE was not supplied")
        topology.validate(json.loads(Path(rendered).read_text()))

    def test_tmpfs_targets_are_absolute_and_web_cache_is_bounded(self):
        services = {
            name: {"tmpfs": ["/tmp:size=64m,mode=1777"]} for name in topology.HARDENED
        }
        services["web"]["tmpfs"].append(
            "/app/apps/web/.next/cache:size=128m,mode=0700,uid=65532,gid=65532"
        )
        topology.validate_tmpfs(services)

    def test_tmpfs_rejects_yaml_split_artifacts(self):
        services = {
            name: {"tmpfs": ["/tmp:size=64m,mode=1777"]} for name in topology.HARDENED
        }
        services["web"]["tmpfs"].extend(
            [
                "/app/apps/web/.next/cache:size=128m,mode=0700,uid=65532,gid=65532",
                "mode=1777",
            ]
        )
        with self.assertRaisesRegex(ValueError, "absolute path"):
            topology.validate_tmpfs(services)

    def test_web_cache_tmpfs_must_have_a_size_ceiling(self):
        services = {
            name: {"tmpfs": ["/tmp:size=64m,mode=1777"]} for name in topology.HARDENED
        }
        services["web"]["tmpfs"].append(
            "/app/apps/web/.next/cache:mode=0700,uid=65532,gid=65532"
        )
        with self.assertRaisesRegex(ValueError, "size ceiling"):
            topology.validate_tmpfs(services)

    def test_upstream_runtime_images_match_the_audited_releases(self):
        services = {
            name: {"image": image}
            for name, image in topology.UPSTREAM_RUNTIME_IMAGES.items()
        }
        topology.validate_upstream_runtime_images(services)
        services["prometheus"]["image"] = "prom/prometheus:latest"
        with self.assertRaisesRegex(ValueError, "audited upstream image"):
            topology.validate_upstream_runtime_images(services)

    def test_release_image_mappings_cover_eight_distinct_artifacts(self):
        services = {}
        for index, (component, service_names) in enumerate(
            topology.ARTIFACT_IMAGE_SERVICES.items(), start=1
        ):
            image = f"registry.example/aperture/{component}@sha256:{index:064x}"
            services.update({name: {"image": image} for name in service_names})

        topology.validate_release_images(services)
        self.assertEqual(
            services["scene-worker"]["image"], services["api"]["image"]
        )

        services["scene-worker"]["image"] = (
            "registry.example/aperture/scene@sha256:" + "7" * 64
        )
        with self.assertRaisesRegex(ValueError, "api services must share"):
            topology.validate_release_images(services)
        services["scene-worker"]["image"] = services["api"]["image"]

        services["minio"]["image"] = services["caddy"]["image"]
        with self.assertRaisesRegex(ValueError, "image digests must be distinct"):
            topology.validate_release_images(services)


class HostingerReleaseTests(unittest.TestCase):
    def test_release_pinning_replaces_only_eight_images_and_preserves_mode(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            path.write_text(
                "API_IMAGE=dummy.registry/api@sha256:" + "0" * 64 + "\n"
                "MEDIA_WORKER_IMAGE=dummy.registry/media-worker@sha256:"
                + "0"
                * 64
                + "\n"
                "WEB_IMAGE=dummy.registry/web@sha256:" + "0" * 64 + "\n"
                "BACKUP_IMAGE=dummy.registry/backup@sha256:" + "0" * 64 + "\n"
                "CADDY_IMAGE=dummy.registry/caddy@sha256:" + "0" * 64 + "\n"
                "STORAGE_IMAGE=dummy.registry/storage@sha256:" + "0" * 64 + "\n"
                "NODE_EXPORTER_IMAGE=dummy.registry/node-exporter@sha256:"
                + "0" * 64
                + "\n"
                "BLACKBOX_IMAGE=dummy.registry/blackbox@sha256:" + "0" * 64 + "\n"
                "SECRET=preserved\n"
            )
            os.chmod(path, 0o600)
            images = {
                "api": "registry.example/aperture/api@sha256:" + "a" * 64,
                "media_worker": "registry.example/aperture/media-worker@sha256:"
                + "d" * 64,
                "web": "registry.example/aperture/web@sha256:" + "b" * 64,
                "backup": "registry.example/aperture/backup@sha256:" + "c" * 64,
                "caddy": "registry.example/aperture/caddy@sha256:" + "e" * 64,
                "storage": "registry.example/aperture/storage@sha256:" + "f" * 64,
                "node_exporter": (
                    "registry.example/aperture/node-exporter@sha256:" + "1" * 64
                ),
                "blackbox": "registry.example/aperture/blackbox@sha256:" + "2" * 64,
            }
            pinning.pin(path, images)
            self.assertIn("SECRET=preserved", path.read_text())
            self.assertIn(f"API_IMAGE={images['api']}", path.read_text())
            self.assertIn(
                f"MEDIA_WORKER_IMAGE={images['media_worker']}", path.read_text()
            )
            self.assertIn(f"CADDY_IMAGE={images['caddy']}", path.read_text())
            self.assertIn(f"STORAGE_IMAGE={images['storage']}", path.read_text())
            self.assertIn(
                f"NODE_EXPORTER_IMAGE={images['node_exporter']}", path.read_text()
            )
            self.assertIn(f"BLACKBOX_IMAGE={images['blackbox']}", path.read_text())
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)

    def test_release_pinning_rejects_shared_content_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "credentials.env"
            path.write_text(
                "API_IMAGE=dummy.registry/api@sha256:" + "0" * 64 + "\n"
                "MEDIA_WORKER_IMAGE=dummy.registry/media-worker@sha256:"
                + "0"
                * 64
                + "\n"
                "WEB_IMAGE=dummy.registry/web@sha256:" + "0" * 64 + "\n"
                "BACKUP_IMAGE=dummy.registry/backup@sha256:" + "0" * 64 + "\n"
                "CADDY_IMAGE=dummy.registry/caddy@sha256:" + "0" * 64 + "\n"
                "STORAGE_IMAGE=dummy.registry/storage@sha256:" + "0" * 64 + "\n"
                "NODE_EXPORTER_IMAGE=dummy.registry/node-exporter@sha256:"
                + "0" * 64
                + "\n"
                "BLACKBOX_IMAGE=dummy.registry/blackbox@sha256:" + "0" * 64 + "\n"
            )
            shared = "f" * 64
            images = {
                "api": "registry.example/aperture/api@sha256:" + shared,
                "media_worker": "registry.example/aperture/media-worker@sha256:"
                + shared,
                "web": "registry.example/aperture/web@sha256:" + "b" * 64,
                "backup": "registry.example/aperture/backup@sha256:" + "c" * 64,
                "caddy": "registry.example/aperture/caddy@sha256:" + "e" * 64,
                "storage": "registry.example/aperture/storage@sha256:" + "f" * 64,
                "node_exporter": (
                    "registry.example/aperture/node-exporter@sha256:" + "1" * 64
                ),
                "blackbox": "registry.example/aperture/blackbox@sha256:" + "2" * 64,
            }
            with self.assertRaisesRegex(ValueError, "digests must be distinct"):
                pinning.pin(path, images)

    def test_dotenv_reader_returns_shell_syntax_literally(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "input.env"
            path.write_text("SAFE=$(touch /tmp/must-not-execute)\n")
            self.assertEqual(
                env_reader.read(path, "SAFE"), "$(touch /tmp/must-not-execute)"
            )


if __name__ == "__main__":
    unittest.main()
