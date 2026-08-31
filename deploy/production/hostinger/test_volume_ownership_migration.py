import ast
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import migrate_volume_ownership as migration
import prepare_vps_env as prepare


ROOT = Path(__file__).resolve().parent
PRIVATE_RENDERER = ROOT.parent / "private-studio" / "render_runtime.py"


def compose_model() -> dict:
    return {
        "name": migration.EXPECTED_PROJECT,
        "volumes": {
            logical: {"name": exact}
            for logical, exact in migration.TARGET_VOLUMES.items()
        },
        "services": {
            "caddy": {
                "image": "registry.example/caddy@sha256:" + "c" * 64,
            },
            "minio": {
                "image": "registry.example/storage@sha256:" + "d" * 64,
            },
        },
    }


def snapshot_record(now: datetime) -> dict:
    return {
        "schema_version": 1,
        "provider": "hostinger",
        "snapshot_id": "snapshot-20260830-001",
        "status": "ready",
        "verified_at": now.isoformat().replace("+00:00", "Z"),
        "verified_by": "release-operator",
        "hostname": "aperture-origin",
        "compose_project": migration.EXPECTED_PROJECT,
        "volumes": sorted(migration.TARGET_VOLUMES.values()),
    }


class VolumeOwnershipContractTests(unittest.TestCase):
    @unittest.skipUnless(
        os.environ.get("APERTURE_DOCKER_INTEGRATION") == "1",
        "set APERTURE_DOCKER_INTEGRATION=1 for the pinned-helper runtime smoke",
    )
    def test_pinned_helper_can_migrate_a_disposable_volume_and_write_as_nonroot(self):
        volume_name = f"aperture-ownership-contract-{os.getpid()}"
        migration.run_command(["docker", "volume", "create", volume_name])
        try:
            migration.helper_run(
                volume_name,
                "chown -R 65532:65532 /volume && sync",
                read_only_volume=False,
                mutation_capabilities=True,
            )
            self.assertTrue(migration.ownership_is_correct(volume_name))
            migration.helper_run(
                volume_name,
                (
                    "probe=/volume/.aperture-uid-65532-write-probe; umask 077; "
                    ': > "$probe"; '
                    'test "$(stat -c %u:%g "$probe")" = "65532:65532"; '
                    'rm -f -- "$probe"'
                ),
                read_only_volume=False,
                user="65532:65532",
            )
            self.assertTrue(migration.ownership_is_correct(volume_name))
        finally:
            migration.run_command(["docker", "volume", "rm", volume_name])

    def test_helper_is_an_exact_digest_and_runtime_commands_never_pull(self):
        self.assertEqual(
            migration.HELPER_IMAGE,
            "docker.io/library/busybox@sha256:"
            "8d7b1636e974e0adfd8d945955fca609304f0a56c18799dfd032d6e661382d84",
        )
        self.assertRegex(
            migration.HELPER_IMAGE,
            r"^docker\.io/library/busybox@sha256:[0-9a-f]{64}$",
        )
        source = Path(migration.__file__).read_text(encoding="utf-8")
        self.assertIn('"--pull=never"', source)
        self.assertIn('user="65532:65532"', source)
        self.assertIn('"--cap-drop=ALL"', source)
        self.assertIn('"--network=none"', source)

    def test_compose_contract_uses_only_the_three_exact_named_volumes(self):
        model = compose_model()
        migration.validate_compose_targets(model)
        self.assertEqual(
            migration.TARGET_VOLUMES,
            {
                "caddy-config": "aperture-production_caddy-config",
                "caddy-data": "aperture-production_caddy-data",
                "minio-data": "aperture-production_minio-data",
            },
        )

        model["volumes"]["minio-data"]["name"] = "another-project_minio-data"
        with self.assertRaisesRegex(migration.MigrationError, "must resolve to"):
            migration.validate_compose_targets(model)

    def test_partial_volume_set_fails_closed(self):
        only_one = next(iter(migration.TARGET_VOLUMES.values()))
        with mock.patch.object(
            migration, "run_command", return_value=f"{only_one}\n"
        ):
            with self.assertRaisesRegex(migration.MigrationError, "partial managed"):
                migration.existing_target_volumes()

    def test_volume_labels_must_bind_exact_project_and_logical_name(self):
        records = []
        for logical, exact in migration.TARGET_VOLUMES.items():
            records.append(
                json.dumps(
                    [
                        {
                            "Name": exact,
                            "Labels": {
                                "com.docker.compose.project": migration.EXPECTED_PROJECT,
                                "com.docker.compose.volume": logical,
                            },
                        }
                    ]
                )
            )
        command_results = [value for record in records for value in (record, "")]
        with mock.patch.object(migration, "run_command", side_effect=command_results):
            migration.inspect_and_validate_volumes()

        records[1] = records[1].replace("caddy-data", "unrelated", 1)
        command_results = [value for record in records for value in (record, "")]
        with mock.patch.object(migration, "run_command", side_effect=command_results):
            with self.assertRaisesRegex(migration.MigrationError, "identity mismatch"):
                migration.inspect_and_validate_volumes()

    def test_labeled_volume_still_mounted_by_any_container_fails_closed(self):
        logical, exact = next(iter(migration.TARGET_VOLUMES.items()))
        inspection = json.dumps(
            [
                {
                    "Name": exact,
                    "Labels": {
                        "com.docker.compose.project": migration.EXPECTED_PROJECT,
                        "com.docker.compose.volume": logical,
                    },
                }
            ]
        )
        with mock.patch.object(
            migration, "run_command", side_effect=(inspection, "container-id\n")
        ):
            with self.assertRaisesRegex(migration.MigrationError, "still mounted"):
                migration.inspect_and_validate_volumes()

    def test_snapshot_evidence_is_current_ready_and_bound_to_exact_volumes(self):
        now = datetime(2026, 8, 30, 12, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            evidence = Path(directory) / "snapshot.json"
            evidence.write_text(json.dumps(snapshot_record(now)), encoding="utf-8")
            os.chmod(evidence, 0o600)
            # CI intentionally runs as an unprivileged user. Model the
            # root-owned production evidence inode without weakening the
            # validator's UID 0 requirement.
            with mock.patch.object(
                Path,
                "stat",
                return_value=SimpleNamespace(
                    st_uid=0,
                    st_mode=stat.S_IFREG | 0o600,
                ),
            ):
                migration.validate_snapshot_evidence(
                    evidence, expected_hostname="aperture-origin", now=now
                )

            stale = snapshot_record(now - timedelta(hours=25))
            evidence.write_text(json.dumps(stale), encoding="utf-8")
            os.chmod(evidence, 0o600)
            with (
                mock.patch.object(
                    Path,
                    "stat",
                    return_value=SimpleNamespace(
                        st_uid=0,
                        st_mode=stat.S_IFREG | 0o600,
                    ),
                ),
                self.assertRaisesRegex(migration.MigrationError, "older than 24"),
            ):
                migration.validate_snapshot_evidence(
                    evidence, expected_hostname="aperture-origin", now=now
                )

    def test_fresh_wiped_host_is_a_no_op_before_helper_or_snapshot_checks(self):
        with (
            mock.patch.object(migration, "load_compose_model", return_value=compose_model()),
            mock.patch.object(migration, "existing_target_volumes", return_value=set()),
            mock.patch.object(migration, "ensure_project_stopped"),
            mock.patch.object(migration, "ensure_helper_present") as helper,
            mock.patch.object(migration, "validate_snapshot_evidence") as snapshot,
        ):
            self.assertEqual(migration.main(["migrate"]), 0)
        helper.assert_not_called()
        snapshot.assert_not_called()

    def test_existing_migration_requires_exact_confirmation(self):
        with (
            mock.patch.object(migration, "load_compose_model", return_value=compose_model()),
            mock.patch.object(
                migration,
                "existing_target_volumes",
                return_value=set(migration.TARGET_VOLUMES.values()),
            ),
            mock.patch.object(migration, "ensure_project_stopped"),
            mock.patch.object(migration, "inspect_and_validate_volumes"),
            mock.patch.object(migration, "ensure_helper_present"),
            mock.patch.object(migration, "audit_ownership", return_value=["minio-data"]),
            mock.patch.object(migration, "migrate_ownership") as mutate,
        ):
            self.assertEqual(migration.main(["migrate", "--confirm", "wrong"]), 1)
        mutate.assert_not_called()

    def test_started_service_check_allows_the_expected_live_volume_mounts(self):
        with (
            mock.patch.object(migration, "load_compose_model", return_value=compose_model()),
            mock.patch.object(
                migration,
                "existing_target_volumes",
                return_value=set(migration.TARGET_VOLUMES.values()),
            ),
            mock.patch.object(migration, "inspect_and_validate_volumes") as inspect,
            mock.patch.object(migration, "verify_started_services"),
        ):
            self.assertEqual(migration.main(["verify-start"]), 0)
        inspect.assert_called_once_with(require_unmounted=False)

    def test_public_and_private_render_contracts_select_the_same_caddy_digest(self):
        owner_values = {label: f"value-{label}" for label in prepare.VPS_RUNTIME_LABELS}
        owner_values["CAPTCHA_REQUIRED"] = "false"
        owner_values["BRAND_AI_PROVIDER"] = "disabled"
        caddy_digest = "registry.example/caddy@sha256:" + "a" * 64
        owner_values["CADDY_IMAGE"] = caddy_digest

        syntax = ast.parse(PRIVATE_RENDERER.read_text(encoding="utf-8"))
        private_labels = None
        for node in syntax.body:
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "RUNTIME_LABELS"
                for target in node.targets
            ):
                private_labels = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(private_labels)
        for label in private_labels:
            owner_values.setdefault(label, f"value-{label}")
        private_runtime = {label: owner_values[label] for label in private_labels}
        public_runtime = prepare.runtime_values(owner_values)
        self.assertEqual(public_runtime["CADDY_IMAGE"], caddy_digest)
        self.assertEqual(private_runtime["CADDY_IMAGE"], caddy_digest)


if __name__ == "__main__":
    unittest.main()
