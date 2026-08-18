import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


inputs = module("host_hardening_inputs", "validate_host_hardening.py")
audit = module("host_hardening_audit", "host_audit.py")
monitoring = module("hostinger_render_monitoring", "render_monitoring.py")
operations = module("hostinger_record_operation", "record_operation.py")
monitoring_validator = module("hostinger_validate_monitoring", "validate_monitoring.py")


def valid_config() -> dict[str, str]:
    return {
        "EXPECTED_HOSTNAME": "aperture-production",
        "SSH_ALLOWED_CIDR": "203.0.113.10/32",
        "HOST_MIN_MEMORY_GB": "24",
        "HOST_MIN_DISK_GB": "500",
        "HOST_MIN_FREE_DISK_GB": "100",
        "HOST_HARDENING_CONFIRMATION": inputs.CONFIRMATION,
    }


class HostHardeningTests(unittest.TestCase):
    def test_dummy_inputs_never_reach_audit_or_apply(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            inputs.validate(inputs.load(ROOT / "host-hardening.example.env"), apply=False)

    def test_ssh_allowlist_cannot_be_broad(self):
        values = valid_config()
        values["SSH_ALLOWED_CIDR"] = "0.0.0.0/0"
        with self.assertRaisesRegex(ValueError, "too broad"):
            inputs.validate(values, apply=True)

    def test_apply_requires_exact_confirmation(self):
        values = valid_config()
        values["HOST_HARDENING_CONFIRMATION"] = "no"
        with self.assertRaisesRegex(ValueError, "confirmation"):
            inputs.validate(values, apply=True)

    def test_complete_fixture_passes_every_audit(self):
        evidence = json.loads((ROOT / "host-audit-pass.fixture.json").read_text())
        checks = audit.evaluate(evidence, valid_config())
        self.assertTrue(all(checks.values()), checks)

    def test_missing_encryption_evidence_fails_closed(self):
        evidence = json.loads((ROOT / "host-audit-pass.fixture.json").read_text())
        evidence["encrypted_volume"] = False
        checks = audit.evaluate(evidence, valid_config())
        self.assertFalse(checks["encrypted_volume_evidence"])

    def test_prometheus_textfile_contains_only_stable_check_labels(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "host.prom"
            audit.write_prometheus(output, {"disk_capacity": True, "time_sync": False}, "fail")
            content = output.read_text()
            self.assertIn('check="disk_capacity"} 1', content)
            self.assertIn('check="time_sync"} 0', content)
            self.assertIn("aperture_host_audit_pass 0", content)
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)

    def test_private_prometheus_config_is_atomic_and_deploy_rejects_dummy(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "prometheus.yml"
            targets = Path(directory) / "targets.yml"
            monitoring.render(
                ROOT / "credentials.example.env", output, deploy=False, targets_output=targets
            )
            content = output.read_text()
            self.assertNotIn("__METRICS_BEARER_TOKEN__", content)
            self.assertIn("DUMMY_64_CHARACTER_METRICS_TOKEN", content)
            self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            target_groups = json.loads(targets.read_text())
            self.assertEqual(
                {group["labels"]["surface"] for group in target_groups},
                {"web", "api", "storage", "cdn", "origin-denial"},
            )
            self.assertEqual(targets.stat().st_mode & 0o777, 0o600)
            with self.assertRaisesRegex(ValueError, "replace METRICS_BEARER_TOKEN"):
                monitoring.render(
                    ROOT / "credentials.example.env", output, deploy=True, targets_output=targets
                )

    def test_success_evidence_is_atomic_bounded_and_allowlisted(self):
        with tempfile.TemporaryDirectory() as directory:
            output = operations.record(Path(directory), "backup", timestamp=1_776_500_000)
            self.assertEqual(
                output.read_text(),
                "# TYPE aperture_operation_last_success_unixtime gauge\n"
                'aperture_operation_last_success_unixtime{operation="backup"} 1776500000\n',
            )
            self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                operations.record(Path(directory), 'backup"} 1\nevil_metric', timestamp=1)

    def test_rendered_monitoring_contract_covers_every_public_surface(self):
        monitoring_validator.validate(
            ROOT / "prometheus.local.yml",
            ROOT / "blackbox.yml",
            ROOT / "blackbox-targets.local.yml",
            ROOT.parents[2] / "ops" / "prometheus-alerts.yml",
        )


if __name__ == "__main__":
    unittest.main()
