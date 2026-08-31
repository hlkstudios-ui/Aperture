import importlib.util
import json
import os
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
fail2ban_ignore = module("hostinger_fail2ban_ignore", "validate_fail2ban_ignore.py")
monitoring = module("hostinger_render_monitoring", "render_monitoring.py")
operations = module("hostinger_record_operation", "record_operation.py")
monitoring_validator = module("hostinger_validate_monitoring", "validate_monitoring.py")


def valid_config() -> dict[str, str]:
    return {
        "EXPECTED_HOSTNAME": "aperture-production",
        "SSH_ALLOWED_CIDR": "203.0.113.10/32",
        "HOSTINGER_VPS_PROFILE": "full",
        "HOST_MIN_MEMORY_GB": "32",
        "HOST_MIN_DISK_GB": "400",
        "HOST_MIN_FREE_DISK_GB": "100",
        "HOST_HARDENING_CONFIRMATION": inputs.CONFIRMATION,
    }


def compact_config() -> dict[str, str]:
    values = valid_config()
    values.update({
        "HOSTINGER_VPS_PROFILE": "compact",
        "HOST_MIN_MEMORY_GB": "16",
        "HOST_MIN_DISK_GB": "200",
        "HOST_MIN_FREE_DISK_GB": "50",
    })
    return values


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

    def test_full_capacity_floor_rejects_smaller_hosts(self):
        values = valid_config()
        values["HOST_MIN_MEMORY_GB"] = "31"
        with self.assertRaisesRegex(ValueError, "capacity floors"):
            inputs.validate(values, apply=False)

        values = valid_config()
        values["HOST_MIN_DISK_GB"] = "399"
        with self.assertRaisesRegex(ValueError, "capacity floors"):
            inputs.validate(values, apply=False)

    def test_compact_capacity_floor_is_valid_and_enforced(self):
        values = compact_config()
        inputs.validate(values, apply=False)

        values["HOST_MIN_MEMORY_GB"] = "15"
        with self.assertRaisesRegex(ValueError, "capacity floors"):
            inputs.validate(values, apply=False)

        values.update({"HOST_MIN_MEMORY_GB": "16", "HOST_MIN_DISK_GB": "199"})
        with self.assertRaisesRegex(ValueError, "capacity floors"):
            inputs.validate(values, apply=False)

    def test_unknown_host_profile_is_rejected(self):
        values = valid_config()
        values["HOSTINGER_VPS_PROFILE"] = "custom"
        with self.assertRaisesRegex(ValueError, "compact or full"):
            inputs.validate(values, apply=False)

    def test_complete_fixture_passes_every_audit(self):
        evidence = json.loads((ROOT / "host-audit-pass.fixture.json").read_text())
        checks = audit.evaluate(evidence, valid_config())
        self.assertTrue(all(checks.values()), checks)

    def test_guest_visible_capacity_allows_provider_provisioning_overhead(self):
        compact = compact_config()
        inputs.validate(compact, apply=False)
        self.assertEqual(
            audit.observed_capacity_floors(compact),
            {"memory_gb": 15, "disk_gb": 190},
        )
        evidence = json.loads((ROOT / "host-audit-compact-pass.fixture.json").read_text())
        checks = audit.evaluate(evidence, compact)
        self.assertTrue(all(checks.values()), checks)

        evidence["memory_gb"] = 14
        self.assertFalse(audit.evaluate(evidence, compact)["memory_capacity"])
        evidence["memory_gb"] = 15
        evidence["disk_gb"] = 189
        self.assertFalse(audit.evaluate(evidence, compact)["disk_capacity"])

    def test_full_guest_visible_capacity_uses_equivalent_overhead(self):
        self.assertEqual(
            audit.observed_capacity_floors(valid_config()),
            {"memory_gb": 31, "disk_gb": 380},
        )

    def test_ufw_audit_accepts_real_columns_but_rejects_world_open_ssh(self):
        evidence = json.loads((ROOT / "host-audit-pass.fixture.json").read_text())
        restricted_ufw = (
            "Status: active\n"
            "Default: deny (incoming), allow (outgoing), disabled (routed)\n"
            "To                         Action      From\n"
            "22/tcp                     ALLOW IN    203.0.113.10\n"
            "80/tcp                     ALLOW IN    Anywhere\n"
            "443/tcp                    ALLOW IN    Anywhere\n"
            "443/udp                    ALLOW IN    Anywhere"
        )
        evidence["ufw"] = restricted_ufw
        self.assertTrue(audit.evaluate(evidence, valid_config())["firewall_ssh_restricted"])

        evidence["ufw"] += "\n22/tcp (v6)                ALLOW IN    Anywhere (v6)"
        self.assertFalse(audit.evaluate(evidence, valid_config())["firewall_ssh_restricted"])

        evidence["ufw"] = restricted_ufw.replace("203.0.113.10", "203.0.113.11")
        self.assertFalse(audit.evaluate(evidence, valid_config())["firewall_ssh_restricted"])

    def test_bootstrap_ssh_drop_in_precedes_cloud_init_and_removes_obsolete_file(self):
        script = (ROOT / "bootstrap_host.sh").read_text()
        replacement = "/etc/ssh/sshd_config.d/00-aperture-hardening.conf"
        obsolete = "/etc/ssh/sshd_config.d/60-aperture-hardening.conf"
        self.assertIn(replacement, script)
        self.assertIn(f"rm -f -- {obsolete}", script)
        self.assertLess(script.index(replacement), script.index(f"rm -f -- {obsolete}"))
        self.assertIn("effective_sshd=$(/usr/sbin/sshd -T)", script)

    def test_bootstrap_fail2ban_ignores_only_the_approved_ssh_sources(self):
        script = (ROOT / "bootstrap_host.sh").read_text()
        jail = "/etc/fail2ban/jail.d/zz-aperture-sshd.local"
        install_index = script.index(jail)
        validate_index = script.index("fail2ban-client -t")
        restart_index = script.index("systemctl restart fail2ban")

        self.assertIn("[sshd]", script)
        self.assertIn("ignoreip = 127.0.0.1/8 ::1 $SSH_ALLOWED_CIDR", script)
        self.assertNotIn("[DEFAULT]\nignoreip", script)
        self.assertIn("rm -f -- /etc/fail2ban/jail.d/99-aperture-sshd.local", script)
        self.assertLess(install_index, script.index("apt-get install"))
        self.assertLess(install_index, validate_index)
        self.assertLess(validate_index, restart_index)
        self.assertNotIn("enable --now unattended-upgrades fail2ban", script)
        self.assertIn('fail2ban-client set sshd unbanip "$REMOTE_IP"', script)
        self.assertIn("FAIL2BAN_IGNOREIP=$(fail2ban-client get sshd ignoreip)", script)
        self.assertIn("validate_fail2ban_ignore.py", script)

    def test_effective_fail2ban_ignoreip_requires_loopback_and_exact_cidr(self):
        output = (
            "These IP addresses/networks are ignored:\n"
            "|- 127.0.0.1/8\n"
            "|- ::1\n"
            "`- 203.0.113.10"
        )
        fail2ban_ignore.validate(output, "203.0.113.10/32")

        with self.assertRaisesRegex(ValueError, "incomplete"):
            fail2ban_ignore.validate(output.replace("203.0.113.10", "203.0.113.11"), "203.0.113.10/32")
        with self.assertRaisesRegex(ValueError, "incomplete"):
            fail2ban_ignore.validate(output.replace("::1", ""), "203.0.113.10/32")

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
            if os.name != "nt":
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
            if os.name != "nt":
                self.assertEqual(output.stat().st_mode & 0o777, 0o600)
            target_groups = json.loads(targets.read_text())
            self.assertEqual(
                {group["labels"]["surface"] for group in target_groups},
                {"web", "api", "storage", "cdn", "origin-denial"},
            )
            if os.name != "nt":
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
            if os.name != "nt":
                self.assertEqual(output.stat().st_mode & 0o777, 0o644)
            with self.assertRaisesRegex(ValueError, "allowlisted"):
                operations.record(Path(directory), 'backup"} 1\nevil_metric', timestamp=1)

    def test_rendered_monitoring_contract_covers_every_public_surface(self):
        with tempfile.TemporaryDirectory() as directory:
            prometheus = Path(directory) / "prometheus.yml"
            targets = Path(directory) / "blackbox-targets.yml"
            monitoring.render(
                ROOT / "credentials.example.env",
                prometheus,
                deploy=False,
                targets_output=targets,
            )
            monitoring_validator.validate(
                prometheus,
                ROOT / "blackbox.yml",
                targets,
                ROOT.parents[2] / "ops" / "prometheus-alerts.yml",
            )


if __name__ == "__main__":
    unittest.main()
