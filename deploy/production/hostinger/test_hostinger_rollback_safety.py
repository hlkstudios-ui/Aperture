import importlib.util
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent


def module(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / filename)
    assert spec and spec.loader
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


rollback = module("hostinger_rollback_safety", "hostinger_rollback.py")


class HostingerRollbackSafetyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        directory = Path(self.temporary.name)
        self.credentials = directory / "credentials.env"
        self.rollback_input = directory / "rollback.env"
        self.private_runtime = directory / "private-studio.env"
        self.private_compose = directory / "private-studio-compose.yml"
        self.coupling_validator = directory / "validate-caddy-coupling.py"
        components = tuple(rollback.IMAGE_KEYS)
        current_digits = ("a", "b", "c", "d", "e", "f", "9", "8")
        target_digits = ("1", "2", "3", "4", "5", "6", "7", "8")
        self.current = {
            component: f"registry.example/{component}@sha256:{digit * 64}"
            for component, digit in zip(components, current_digits, strict=True)
        }
        self.target = {
            component: f"registry.example/{component}@sha256:{digit * 64}"
            for component, digit in zip(components, target_digits, strict=True)
        }
        self._write_credentials()
        self._write_rollback(include_storage_confirmations=True)
        self._write_private_runtime()
        self.private_compose.write_text("services: {}\n")
        self.coupling_validator.write_text("# test fixture\n")
        self.constants = patch.multiple(
            rollback,
            CREDENTIALS=self.credentials,
            ROLLBACK_INPUT=self.rollback_input,
            PRIVATE_STUDIO_RUNTIME=self.private_runtime,
            PRIVATE_STUDIO_COMPOSE=self.private_compose,
            CADDY_COUPLING_VALIDATOR=self.coupling_validator,
        )
        self.constants.start()

    def tearDown(self):
        self.constants.stop()
        self.temporary.cleanup()

    def _write_credentials(self) -> None:
        lines = [
            f"{label}={self.current[component]}"
            for component, label in rollback.IMAGE_KEYS.items()
        ]
        lines.append("SECRET=must-not-appear-in-output")
        self.credentials.write_text("\n".join(lines) + "\n")
        os.chmod(self.credentials, 0o600)

    def _write_rollback(
        self,
        *,
        include_storage_confirmations: bool,
        overrides: dict[str, str] | None = None,
    ) -> None:
        lines = [
            f"{rollback.TARGET_KEYS[component]}={self.target[component]}"
            for component in rollback.IMAGE_KEYS
        ]
        lines.append(f"ROLLBACK_CONFIRMATION={rollback.CONFIRMATION}")
        confirmations = dict(rollback.STORAGE_CHANGE_CONFIRMATIONS)
        if overrides:
            confirmations.update(overrides)
        if include_storage_confirmations:
            lines.extend(f"{label}={value}" for label, value in confirmations.items())
        self.rollback_input.write_text("\n".join(lines) + "\n")

    def _write_private_runtime(self, caddy_image: str | None = None) -> None:
        image = caddy_image or self.current["caddy"]
        self.private_runtime.write_text(
            f"CADDY_IMAGE={image}\n"
            "PUBLIC_APP_ORIGIN=https://example.com\n"
            "PUBLIC_APP_HOST=example.com\n"
            "ORIGIN_EDGE_SECRET=private-origin-secret-must-remain-private\n"
            "STUDIO_EDGE_SECRET=private-studio-secret-must-remain-private\n"
        )
        os.chmod(self.private_runtime, 0o600)

    def test_ci_managed_layout_refuses_inspection_and_execution_before_state_access(self):
        managed_current = Path(self.temporary.name) / "ci-managed-current"
        managed_current.write_text("sentinel\n")

        for mode in ("inspect", "execute"):
            with (
                self.subTest(mode=mode),
                patch.object(
                    rollback,
                    "CI_MANAGED_LAYOUT_SENTINELS",
                    (managed_current,),
                ),
                patch.object(rollback, "configuration") as configuration,
                patch.object(rollback, "inspect_images") as inspect_images,
                self.assertRaisesRegex(RuntimeError, "disabled on CI-managed hosts"),
            ):
                rollback.run(mode)
            configuration.assert_not_called()
            inspect_images.assert_not_called()

    def test_ci_layout_detection_error_fails_closed_before_state_access(self):
        inaccessible = Path(self.temporary.name) / "inaccessible-current"
        with (
            patch.object(
                rollback,
                "CI_MANAGED_LAYOUT_SENTINELS",
                (inaccessible,),
            ),
            patch.object(Path, "lstat", side_effect=PermissionError("denied")),
            patch.object(rollback, "configuration") as configuration,
            self.assertRaisesRegex(RuntimeError, "cannot safely determine"),
        ):
            rollback.run("inspect")
        configuration.assert_not_called()

    def test_dummy_validation_remains_non_operational_on_ci_managed_host(self):
        managed_current = Path(self.temporary.name) / "ci-managed-current"
        managed_current.write_text("sentinel\n")
        with patch.object(
            rollback,
            "CI_MANAGED_LAYOUT_SENTINELS",
            (managed_current,),
        ):
            self.assertEqual(
                rollback.run("dummy"),
                {"event": "rollback.dummy_validated", "status": "pass"},
            )

    def _execute_with_outcomes(
        self, outcomes: list[BaseException | subprocess.CompletedProcess]
    ) -> tuple[list[tuple[str, str]], rollback.RollbackExecutionError]:
        events: list[tuple[str, str]] = []
        original_replace = rollback.replace_release
        original_replace_private = rollback.replace_private_caddy
        outcome_iterator = iter(outcomes)

        def replace(path, expected, replacement):
            release = "target" if replacement == self.target else "current"
            events.append(("replace_public", release))
            original_replace(path, expected, replacement)

        def replace_private(path, expected, replacement):
            release = "target" if replacement == self.target["caddy"] else "current"
            events.append(("replace_private", release))
            original_replace_private(path, expected, replacement)

        def execute(command, **kwargs):
            if command[-1] == "preflight":
                kind = "preflight"
            elif str(self.coupling_validator) in command:
                kind = "caddy_coupling"
            elif str(self.private_compose) in command:
                kind = "private_compose"
            else:
                kind = "public_compose"
            events.append(("command", kind))
            self.assertEqual(
                kwargs,
                {
                    "check": True,
                    "capture_output": True,
                    "text": True,
                    "timeout": 600,
                },
            )
            outcome = next(outcome_iterator)
            if isinstance(outcome, BaseException):
                raise outcome
            return outcome

        with (
            patch.object(rollback, "inspect_images"),
            patch.object(rollback, "command_prefix", return_value=["docker", "compose"]),
            patch.object(rollback, "replace_release", side_effect=replace),
            patch.object(
                rollback, "replace_private_caddy", side_effect=replace_private
            ),
            patch.object(rollback.subprocess, "run", side_effect=execute),
            self.assertRaises(rollback.RollbackExecutionError) as raised,
        ):
            rollback.run("execute")
        return events, raised.exception

    def test_storage_change_rejects_missing_or_inexact_evidence_confirmations(self):
        self._write_rollback(include_storage_confirmations=False)
        with (
            patch.object(rollback, "inspect_images") as inspect,
            self.assertRaisesRegex(RuntimeError, "compatibility, snapshot, and clone"),
        ):
            rollback.run("execute")
        inspect.assert_not_called()

        for label in rollback.STORAGE_CHANGE_CONFIRMATIONS:
            with self.subTest(label=label):
                self._write_rollback(
                    include_storage_confirmations=True,
                    overrides={label: "ALMOST_BUT_NOT_THE_EXACT_CONFIRMATION"},
                )
                with self.assertRaisesRegex(
                    RuntimeError, "compatibility, snapshot, and clone"
                ):
                    rollback.configuration("execute")

    def test_unchanged_storage_image_does_not_require_stateful_evidence(self):
        self.target["storage"] = self.current["storage"]
        self._write_rollback(include_storage_confirmations=False)
        current, target = rollback.configuration("execute")
        self.assertEqual(current["storage"], target["storage"])

    def test_target_compose_failure_restores_env_and_verifies_compensation(self):
        original = self.credentials.read_text()
        private_original = self.private_runtime.read_text()
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CalledProcessError(1, ["target-compose"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
                subprocess.CompletedProcess(["recovery-preflight"], 0),
                subprocess.CompletedProcess(["recovery-caddy-coupling"], 0),
            ]
        )
        self.assertEqual(
            events,
            [
                ("command", "caddy_coupling"),
                ("replace_private", "target"),
                ("replace_public", "target"),
                ("command", "public_compose"),
                ("replace_public", "current"),
                ("replace_private", "current"),
                ("command", "public_compose"),
                ("command", "private_compose"),
                ("command", "preflight"),
                ("command", "caddy_coupling"),
            ],
        )
        self.assertEqual(error.failed_stage, "target_rollout")
        self.assertEqual(error.recovery_status, "completed")
        self.assertIsNone(error.recovery_failure_stage)
        self.assertEqual(self.credentials.read_text(), original)
        self.assertEqual(self.private_runtime.read_text(), private_original)

    def test_target_preflight_failure_restores_before_compensation(self):
        original = self.credentials.read_text()
        private_original = self.private_runtime.read_text()
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CompletedProcess(["target-public-compose"], 0),
                subprocess.CompletedProcess(["target-private-compose"], 0),
                subprocess.CalledProcessError(1, ["target-preflight"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
                subprocess.CompletedProcess(["recovery-preflight"], 0),
                subprocess.CompletedProcess(["recovery-caddy-coupling"], 0),
            ]
        )
        self.assertEqual(
            events,
            [
                ("command", "caddy_coupling"),
                ("replace_private", "target"),
                ("replace_public", "target"),
                ("command", "public_compose"),
                ("command", "private_compose"),
                ("command", "preflight"),
                ("replace_public", "current"),
                ("replace_private", "current"),
                ("command", "public_compose"),
                ("command", "private_compose"),
                ("command", "preflight"),
                ("command", "caddy_coupling"),
            ],
        )
        self.assertEqual(error.failed_stage, "target_preflight")
        self.assertEqual(error.recovery_status, "completed")
        self.assertEqual(self.credentials.read_text(), original)
        self.assertEqual(self.private_runtime.read_text(), private_original)

    def test_public_compensation_failure_still_redeploys_private_gateway(self):
        original = self.credentials.read_text()
        private_original = self.private_runtime.read_text()
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CalledProcessError(1, ["target-compose"]),
                subprocess.CalledProcessError(1, ["recovery-public-compose"]),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
            ]
        )
        self.assertEqual(
            events,
            [
                ("command", "caddy_coupling"),
                ("replace_private", "target"),
                ("replace_public", "target"),
                ("command", "public_compose"),
                ("replace_public", "current"),
                ("replace_private", "current"),
                ("command", "public_compose"),
                ("command", "private_compose"),
            ],
        )
        self.assertEqual(error.recovery_status, "failed")
        self.assertEqual(error.recovery_failure_stage, "compensation_rollout")
        self.assertEqual(self.credentials.read_text(), original)
        self.assertEqual(self.private_runtime.read_text(), private_original)

    def test_private_compensation_failure_has_distinct_stage(self):
        original = self.credentials.read_text()
        private_original = self.private_runtime.read_text()
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CalledProcessError(1, ["target-compose"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CalledProcessError(1, ["recovery-private-compose"]),
            ]
        )
        self.assertEqual(error.recovery_status, "failed")
        self.assertEqual(
            error.recovery_failure_stage, "private_compensation_rollout"
        )
        self.assertEqual(events[-2:], [("command", "public_compose"), ("command", "private_compose")])
        self.assertEqual(self.credentials.read_text(), original)
        self.assertEqual(self.private_runtime.read_text(), private_original)

    def test_target_private_gateway_failure_compensates_both_gateways(self):
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CompletedProcess(["target-public-compose"], 0),
                subprocess.CalledProcessError(1, ["target-private-compose"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
                subprocess.CompletedProcess(["recovery-preflight"], 0),
                subprocess.CompletedProcess(["recovery-caddy-coupling"], 0),
            ]
        )
        self.assertEqual(error.failed_stage, "target_private_rollout")
        self.assertEqual(error.recovery_status, "completed")
        self.assertEqual(
            [event for event in events if event[0] == "command"],
            [
                ("command", "caddy_coupling"),
                ("command", "public_compose"),
                ("command", "private_compose"),
                ("command", "public_compose"),
                ("command", "private_compose"),
                ("command", "preflight"),
                ("command", "caddy_coupling"),
            ],
        )

    def test_target_caddy_coupling_failure_compensates_both_gateways(self):
        events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CompletedProcess(["target-public-compose"], 0),
                subprocess.CompletedProcess(["target-private-compose"], 0),
                subprocess.CompletedProcess(["target-preflight"], 0),
                subprocess.CalledProcessError(1, ["target-caddy-coupling"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
                subprocess.CompletedProcess(["recovery-preflight"], 0),
                subprocess.CompletedProcess(["recovery-caddy-coupling"], 0),
            ]
        )
        self.assertEqual(error.failed_stage, "target_caddy_coupling")
        self.assertEqual(error.recovery_status, "completed")
        self.assertEqual(
            [event for event in events if event == ("command", "caddy_coupling")],
            [
                ("command", "caddy_coupling"),
                ("command", "caddy_coupling"),
                ("command", "caddy_coupling"),
            ],
        )

    def test_compensation_caddy_coupling_failure_has_distinct_stage(self):
        _events, error = self._execute_with_outcomes(
            [
                subprocess.CompletedProcess(["current-caddy-coupling"], 0),
                subprocess.CalledProcessError(1, ["target-public-compose"]),
                subprocess.CompletedProcess(["recovery-public-compose"], 0),
                subprocess.CompletedProcess(["recovery-private-compose"], 0),
                subprocess.CompletedProcess(["recovery-preflight"], 0),
                subprocess.CalledProcessError(1, ["recovery-caddy-coupling"]),
            ]
        )
        self.assertEqual(error.recovery_status, "failed")
        self.assertEqual(
            error.recovery_failure_stage, "compensation_caddy_coupling"
        )

    def test_caddy_change_success_updates_and_deploys_both_gateways(self):
        commands: list[str] = []
        private_commands: list[list[str]] = []

        def execute(command, **kwargs):
            del kwargs
            if command[-1] == "preflight":
                commands.append("preflight")
            elif str(self.coupling_validator) in command:
                commands.append("caddy_coupling")
            elif str(self.private_compose) in command:
                commands.append("private_compose")
                private_commands.append(command)
            else:
                commands.append("public_compose")
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.object(rollback, "inspect_images"),
            patch.object(rollback, "command_prefix", return_value=["docker", "compose"]),
            patch.object(rollback.subprocess, "run", side_effect=execute),
        ):
            result = rollback.run("execute")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(
            commands,
            [
                "caddy_coupling",
                "public_compose",
                "private_compose",
                "preflight",
                "caddy_coupling",
            ],
        )
        self.assertEqual(len(private_commands), 1)
        self.assertEqual(private_commands[0][-3:], ["--wait", "--wait-timeout", "120"])
        self.assertIn(f"CADDY_IMAGE={self.target['caddy']}", self.credentials.read_text())
        private_content = self.private_runtime.read_text()
        self.assertIn(f"CADDY_IMAGE={self.target['caddy']}", private_content)
        self.assertIn("private-studio-secret-must-remain-private", private_content)

    def test_missing_or_mismatched_private_runtime_fails_before_public_env_change(self):
        original = self.credentials.read_text()
        for state in ("missing", "mismatched", "duplicate"):
            with self.subTest(state=state):
                if state == "missing":
                    self.private_runtime.unlink(missing_ok=True)
                elif state == "mismatched":
                    self._write_private_runtime("registry.example/caddy@sha256:" + "0" * 64)
                else:
                    self._write_private_runtime()
                    with self.private_runtime.open("a") as runtime:
                        runtime.write(f"CADDY_IMAGE={self.target['caddy']}\n")
                with (
                    patch.object(rollback, "inspect_images"),
                    patch.object(rollback, "replace_release") as replace_public,
                    self.assertRaisesRegex(RuntimeError, "private Studio runtime"),
                ):
                    rollback.run("execute")
                replace_public.assert_not_called()
                self.assertEqual(self.credentials.read_text(), original)

    def test_unchanged_caddy_digest_does_not_touch_private_gateway(self):
        self.target["caddy"] = self.current["caddy"]
        self._write_rollback(include_storage_confirmations=True)
        commands: list[str] = []

        def execute(command, **kwargs):
            del kwargs
            commands.append("preflight" if command[-1] == "preflight" else "public")
            return subprocess.CompletedProcess(command, 0)

        with (
            patch.object(rollback, "inspect_images"),
            patch.object(rollback, "command_prefix", return_value=["docker", "compose"]),
            patch.object(
                rollback,
                "replace_private_caddy",
                side_effect=AssertionError("private runtime must remain untouched"),
            ),
            patch.object(rollback.subprocess, "run", side_effect=execute),
        ):
            result = rollback.run("execute")

        self.assertEqual(result["status"], "pass")
        self.assertEqual(commands, ["public", "preflight"])
        self.assertIn(f"CADDY_IMAGE={self.current['caddy']}", self.private_runtime.read_text())

    def test_recovery_failure_output_is_structured_and_secret_free(self):
        secret = "never-print-this-command-or-secret"
        error = rollback.RollbackExecutionError(
            "target_private_rollout", "failed", "private_compensation_rollout"
        )
        error.__cause__ = RuntimeError(secret)
        output = io.StringIO()
        with (
            patch.object(rollback, "run", side_effect=error),
            patch.object(sys, "argv", ["hostinger_rollback.py", "--mode", "execute"]),
            redirect_stderr(output),
        ):
            self.assertEqual(rollback.main(), 1)
        self.assertNotIn(secret, output.getvalue())
        self.assertEqual(
            json.loads(output.getvalue()),
            {
                "event": "rollback.recovery_failed",
                "failed_stage": "target_private_rollout",
                "recovery_failure_stage": "private_compensation_rollout",
                "recovery_status": "failed",
                "status": "fail",
            },
        )


if __name__ == "__main__":
    unittest.main()
