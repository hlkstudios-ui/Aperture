import contextlib
import io
import itertools
import os
from pathlib import Path
import re
import stat
import tempfile
import unittest
from unittest import mock

import prepare_vps_env as prepare
from validate_config import EXAMPLE_INPUT, load
from validate_host_hardening import REQUIRED as HOST_HARDENING_REQUIRED


def deployable_values() -> dict[str, str]:
    values = {
        key: value.replace("DUMMY", "production").replace("dummy", "production")
        for key, value in load(EXAMPLE_INPUT).items()
    }
    values["HOSTINGER_API_TOKEN"] = "hostinger-local-control-token"
    values["HOSTINGER_VPS_IP"] = "8.8.8.8"
    values["HOSTINGER_VPS_IPV6"] = "2606:4700:4700::1111"
    values["API_IMAGE"] = "registry.example/aperture-api@sha256:" + "1" * 64
    values["MEDIA_WORKER_IMAGE"] = (
        "registry.example/aperture-media-worker@sha256:" + "4" * 64
    )
    values["WEB_IMAGE"] = "registry.example/aperture-web@sha256:" + "2" * 64
    values["BACKUP_IMAGE"] = "registry.example/aperture-backup@sha256:" + "3" * 64
    values["CADDY_IMAGE"] = "registry.example/aperture-caddy@sha256:" + "5" * 64
    values["STORAGE_IMAGE"] = (
        "registry.example/aperture-storage@sha256:" + "6" * 64
    )
    values["NODE_EXPORTER_IMAGE"] = (
        "registry.example/aperture-node-exporter@sha256:" + "7" * 64
    )
    values["BLACKBOX_IMAGE"] = (
        "registry.example/aperture-blackbox@sha256:" + "8" * 64
    )
    values["STRIPE_SECRET_KEY"] = "sk_live_production_validation"
    values["POLICY_REQUIRE_APPROVED"] = "true"
    values.update(
        {
            "EXPECTED_HOSTNAME": "origin.apertures.example",
            "SSH_ALLOWED_CIDR": "203.0.113.5/32",
            "HOST_MIN_MEMORY_GB": "32",
            "HOST_MIN_DISK_GB": "400",
            "HOST_MIN_FREE_DISK_GB": "100",
            "HOST_HARDENING_CONFIRMATION": "HARDEN_HOSTINGER_VPS_WITH_RESTRICTED_SSH",
        }
    )
    return values


def custom_domain_values() -> dict[str, str]:
    values = deployable_values()
    values.update(
        {
            "CUSTOM_DOMAINS_ENABLED": "true",
            "CUSTOM_DOMAIN_INFRASTRUCTURE_READY": "true",
            "CUSTOM_DOMAIN_PROVIDER": "cloudflare",
            "CUSTOM_DOMAIN_CNAME_TARGET": "customers.apertures.online",
            "CUSTOM_DOMAIN_FALLBACK_ORIGIN": "origin.apertures.online",
            "CUSTOM_DOMAIN_MAX_PER_SITE": "9",
            "ORIGIN_HOSTNAME": "origin.apertures.online",
            "CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN": (
                "cloudflare-custom-hostnames-runtime-token"
            ),
            "CLOUDFLARE_TURNSTILE_API_TOKEN": (
                "cloudflare-turnstile-runtime-token"
            ),
            "NEXT_PUBLIC_TURNSTILE_SITE_KEY": "0x4AAAA-aperture-widget-key",
            "CLOUDFLARE_ZONE_ID": "a" * 32,
            "CLOUDFLARE_ACCOUNT_ID": "b" * 32,
            "CLOUDFLARE_SITE_DOMAINS_KV_NAMESPACE_ID": "c" * 32,
            "TURNSTILE_HOSTNAME_LIMIT": "10",
        }
    )
    return values


def write_env(path: Path, values: dict[str, str]) -> None:
    path.write_text("".join(f"{key}={value}\n" for key, value in values.items()))


def placeholder_internal_values() -> dict[str, str]:
    return {label: f"DUMMY_{label}" for label in prepare.INTERNAL_SECRET_BYTES}


class PrepareVpsEnvironmentTests(unittest.TestCase):
    def test_clear_hostinger_token_is_atomic_and_preserves_every_other_line(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = (
                "# HOSTINGER_API_TOKEN=comment-only\r\n"
                "FIRST=unchanged\r\n"
                "HOSTINGER_API_TOKEN=provider-secret\r\n"
                "LAST=also-unchanged\r\n"
            )
            path.write_text(original, encoding="utf-8", newline="")
            os.chmod(path, 0o640)
            original_mode = stat.S_IMODE(path.stat().st_mode)

            with mock.patch.object(prepare.os, "replace", wraps=os.replace) as replace:
                self.assertTrue(prepare.clear_hostinger_api_token(path))

            self.assertEqual(replace.call_count, 1)
            self.assertEqual(
                path.read_bytes(),
                original.replace(
                    "HOSTINGER_API_TOKEN=provider-secret",
                    "HOSTINGER_API_TOKEN=",
                ).encode("utf-8"),
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), original_mode)

    def test_clear_hostinger_token_clears_all_active_assignments_and_is_idempotent(
        self,
    ):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                "HOSTINGER_API_TOKEN=first\n  export HOSTINGER_API_TOKEN =second\n",
                encoding="utf-8",
                newline="",
            )

            self.assertTrue(prepare.clear_hostinger_api_token(path))
            first_render = path.read_bytes()
            self.assertEqual(
                first_render,
                b"HOSTINGER_API_TOKEN=\n  export HOSTINGER_API_TOKEN =\n",
            )
            with mock.patch.object(
                prepare, "atomic_write", side_effect=AssertionError("must not rewrite")
            ):
                self.assertFalse(prepare.clear_hostinger_api_token(path))
            self.assertEqual(path.read_bytes(), first_render)

    def test_clear_hostinger_token_cli_never_prints_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            secret = "provider-secret-must-not-appear"
            path.write_text(f"HOSTINGER_API_TOKEN={secret}\n", encoding="utf-8")
            output = io.StringIO()

            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                prepare.main(["clear-hostinger-token", "--input", str(path)])

            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn("HOSTINGER_API_TOKEN=", output.getvalue())
            self.assertEqual(path.read_text(encoding="utf-8"), "HOSTINGER_API_TOKEN=\n")

    def test_clear_hostinger_token_rejects_a_missing_assignment_without_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            original = b"UNRELATED=value\n"
            path.write_bytes(original)

            with self.assertRaisesRegex(ValueError, "assignment is missing"):
                prepare.clear_hostinger_api_token(path)

            self.assertEqual(path.read_bytes(), original)

    def test_clear_cloudflare_source_tokens_is_atomic_and_secret_free(self):
        for action, label, function in (
            (
                "clear-cloudflare-dns-token",
                "CLOUDFLARE_API_TOKEN",
                prepare.clear_cloudflare_dns_token,
            ),
            (
                "clear-cloudflare-preflight-token",
                "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
                prepare.clear_cloudflare_preflight_token,
            ),
        ):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / ".env"
                secret = f"{label.lower()}-secret-must-not-appear"
                path.write_text(f"{label}={secret}\nKEEP=value\n", encoding="utf-8")
                os.chmod(path, 0o640)
                original_mode = stat.S_IMODE(path.stat().st_mode)

                with mock.patch.object(
                    prepare.os, "replace", wraps=os.replace
                ) as replace:
                    self.assertTrue(function(path))

                self.assertEqual(replace.call_count, 1)
                self.assertEqual(
                    path.read_text(encoding="utf-8"), f"{label}=\nKEEP=value\n"
                )
                self.assertEqual(stat.S_IMODE(path.stat().st_mode), original_mode)

                output = io.StringIO()
                path.write_text(f"{label}={secret}\n", encoding="utf-8")
                with contextlib.redirect_stdout(output), contextlib.redirect_stderr(
                    output
                ):
                    prepare.main([action, "--input", str(path)])
                self.assertNotIn(secret, output.getvalue())
                self.assertEqual(path.read_text(encoding="utf-8"), f"{label}=\n")

    def test_clear_tailscale_auth_key_is_atomic_and_cli_never_prints_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            secret = "tskey-auth-secret-must-not-appear"
            original = (
                f"HOSTINGER_API_TOKEN=preserve-me\r\nTAILSCALE_AUTH_KEY={secret}\r\n"
            )
            path.write_text(original, encoding="utf-8", newline="")
            output = io.StringIO()

            with mock.patch.object(prepare.os, "replace", wraps=os.replace) as replace:
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    prepare.main(["clear-tailscale-auth-key", "--input", str(path)])

            self.assertEqual(replace.call_count, 1)
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn("TAILSCALE_AUTH_KEY=", output.getvalue())
            self.assertEqual(
                path.read_bytes(),
                b"HOSTINGER_API_TOKEN=preserve-me\r\nTAILSCALE_AUTH_KEY=\r\n",
            )

    def test_clear_tailscale_api_key_is_atomic_and_cli_never_prints_value(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            secret = "tskey-api-secret-must-not-appear"
            original = (
                f"TAILSCALE_AUTH_KEY=preserve-me\r\nTAILSCALE_API_KEY={secret}\r\n"
            )
            path.write_text(original, encoding="utf-8", newline="")
            output = io.StringIO()

            with mock.patch.object(prepare.os, "replace", wraps=os.replace) as replace:
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    prepare.main(["clear-tailscale-api-key", "--input", str(path)])

            self.assertEqual(replace.call_count, 1)
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn("TAILSCALE_API_KEY=", output.getvalue())
            self.assertEqual(
                path.read_bytes(),
                b"TAILSCALE_AUTH_KEY=preserve-me\r\nTAILSCALE_API_KEY=\r\n",
            )

    def test_generate_is_atomic_idempotent_and_preserves_configured_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            values = placeholder_internal_values()
            configured = "a" * 64
            values["POSTGRES_PASSWORD"] = configured
            values["STRIPE_SECRET_KEY"] = "DUMMY_PROVIDER_ISSUED_VALUE"
            write_env(path, values)
            os.chmod(path, 0o640)
            original_mode = stat.S_IMODE(path.stat().st_mode)

            sequence = itertools.count(1)

            def token_hex(size: int) -> str:
                return format(next(sequence), f"0{size * 2}x")

            with mock.patch.object(prepare.secrets, "token_hex", side_effect=token_hex):
                generated, preserved = prepare.generate_internal(path)

            self.assertEqual(
                (generated, preserved),
                (len(prepare.INTERNAL_SECRET_BYTES) - 1, 1),
            )
            generated_values = load(path)
            self.assertEqual(generated_values["POSTGRES_PASSWORD"], configured)
            self.assertEqual(
                generated_values["STRIPE_SECRET_KEY"], "DUMMY_PROVIDER_ISSUED_VALUE"
            )
            self.assertEqual(len(generated_values["MINIO_ROOT_USER"]), 32)
            for label in prepare.INTERNAL_SECRET_BYTES.keys() - {"MINIO_ROOT_USER"}:
                self.assertEqual(len(generated_values[label]), 64)
            self.assertEqual(
                len(
                    {generated_values[label] for label in prepare.INTERNAL_SECRET_BYTES}
                ),
                len(prepare.INTERNAL_SECRET_BYTES),
            )
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), original_mode)

            first_render = path.read_bytes()
            with mock.patch.object(
                prepare.secrets,
                "token_hex",
                side_effect=AssertionError("must not rotate"),
            ):
                self.assertEqual(
                    prepare.generate_internal(path),
                    (0, len(prepare.INTERNAL_SECRET_BYTES)),
                )
            self.assertEqual(path.read_bytes(), first_render)

    def test_generate_recognizes_only_documented_non_dummy_placeholders(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            values = {
                label: "configured-value" for label in prepare.INTERNAL_SECRET_BYTES
            }
            for label, placeholders in prepare.KNOWN_PLACEHOLDERS.items():
                if placeholders:
                    values[label] = next(iter(placeholders))
            write_env(path, values)

            generated, _preserved = prepare.generate_internal(path)
            expected = sum(
                bool(placeholders)
                for placeholders in prepare.KNOWN_PLACEHOLDERS.values()
            )
            self.assertEqual(generated, expected)
            rendered = load(path)
            for label, placeholders in prepare.KNOWN_PLACEHOLDERS.items():
                if not placeholders:
                    self.assertEqual(rendered[label], "configured-value")

    def test_generate_cli_never_prints_generated_values(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            write_env(path, placeholder_internal_values())
            secret = "f" * 64
            output = io.StringIO()
            with mock.patch.object(prepare.secrets, "token_hex", return_value=secret):
                with (
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(output),
                ):
                    prepare.main(["generate", "--input", str(path)])
            self.assertNotIn(secret, output.getvalue())
            self.assertNotIn("POSTGRES_PASSWORD=", output.getvalue())

    def test_render_writes_exact_runtime_allowlist_and_drops_control_plane(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            values = deployable_values()
            values.update(
                {
                    "HOSTINGER_SSH_USER": "operator",
                    "HOSTINGER_SSH_PRIVATE_KEY_PATH": "/local/private/key",
                    "DNS_ZONE": values["DNS_ZONE"],
                    "REGISTRY_REPOSITORY": "registry.example/aperture",
                    "RELEASE_ID": "release-1",
                    "RELEASE_PLATFORM": "linux/amd64",
                    "HOSTINGER_ROLLBACK_API_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_WEB_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_BACKUP_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_CADDY_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_STORAGE_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE": "DUMMY_ROLLBACK",
                    "HOSTINGER_ROLLBACK_BLACKBOX_IMAGE": "DUMMY_ROLLBACK",
                    "TAILSCALE_AUTH_KEY": "DUMMY_ENROLLMENT_KEY",
                    "TAILSCALE_OWNER_EMAIL": "owner@example.com",
                    "CLOUDFLARE_API_TOKEN": "DUMMY_CLOUDFLARE_CONTROL_TOKEN",
                    "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN": (
                        "DUMMY_CLOUDFLARE_PREFLIGHT_TOKEN"
                    ),
                    "CLOUDFLARE_ACCOUNT_ID": "DUMMY_CLOUDFLARE_ACCOUNT",
                }
            )
            write_env(source, values)

            with mock.patch.object(prepare.os, "chmod", wraps=os.chmod) as chmod:
                prepare.render_vps(source, output)

            rendered = load(output)
            self.assertEqual(set(rendered), set(prepare.VPS_RUNTIME_LABELS))
            self.assertEqual(chmod.call_args.args[1], 0o600)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
            for excluded in (
                "HOSTINGER_API_TOKEN",
                "HOSTINGER_SSH_USER",
                "HOSTINGER_SSH_PRIVATE_KEY_PATH",
                "HOSTINGER_VPS_REGION",
                "HOSTINGER_VPS_MEMORY_GB",
                "HOSTINGER_VPS_VCPU",
                "DNS_ZONE",
                "REGISTRY_REPOSITORY",
                "RELEASE_ID",
                "RELEASE_PLATFORM",
                "HOSTINGER_ROLLBACK_API_IMAGE",
                "HOSTINGER_ROLLBACK_MEDIA_WORKER_IMAGE",
                "HOSTINGER_ROLLBACK_WEB_IMAGE",
                "HOSTINGER_ROLLBACK_BACKUP_IMAGE",
                "HOSTINGER_ROLLBACK_CADDY_IMAGE",
                "HOSTINGER_ROLLBACK_STORAGE_IMAGE",
                "HOSTINGER_ROLLBACK_NODE_EXPORTER_IMAGE",
                "HOSTINGER_ROLLBACK_BLACKBOX_IMAGE",
                "TAILSCALE_AUTH_KEY",
                "TAILSCALE_OWNER_EMAIL",
                "STRIPE_SECRET_KEY",
                "STRIPE_WEBHOOK_SECRET",
                "CLOUDFLARE_API_TOKEN",
                "CLOUDFLARE_CUSTOM_DOMAIN_PREFLIGHT_API_TOKEN",
            ):
                self.assertNotIn(excluded, rendered)
            self.assertEqual(
                rendered["CLOUDFLARE_CUSTOM_HOSTNAMES_API_TOKEN"], ""
            )
            self.assertEqual(rendered["HOSTINGER_VPS_IP"], "8.8.8.8")
            self.assertEqual(
                rendered["HOSTINGER_VPS_IPV6"], "2606:4700:4700::1111"
            )
            self.assertEqual(rendered["CLOUDFLARE_TURNSTILE_API_TOKEN"], "")
            self.assertEqual(rendered["TURNSTILE_HOSTNAME_LIMIT"], "10")
            self.assertEqual(rendered["CLOUDFLARE_ACCOUNT_ID"], "")
            self.assertEqual(rendered["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"], "false")

    def test_post_provision_render_accepts_an_empty_hostinger_token(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            values = deployable_values()
            values["HOSTINGER_API_TOKEN"] = ""
            write_env(source, values)

            prepare.render_vps(source, output)

            self.assertNotIn("HOSTINGER_API_TOKEN", load(output))

    def test_render_omits_inactive_optional_credentials(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            values = deployable_values()
            values["CAPTCHA_REQUIRED"] = "false"
            values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = "DUMMY_UNUSED_SITE_KEY"
            values["TURNSTILE_SECRET_KEY"] = "DUMMY_UNUSED_SECRET_KEY"
            values["BRAND_AI_PROVIDER"] = "disabled"
            values["OPENAI_API_KEY"] = "DUMMY_UNUSED_OPENAI_KEY"
            write_env(source, values)

            prepare.render_vps(source, output)

            rendered = load(output)
            self.assertEqual(rendered["NEXT_PUBLIC_TURNSTILE_SITE_KEY"], "")
            self.assertEqual(rendered["TURNSTILE_SECRET_KEY"], "")
            self.assertEqual(rendered["OPENAI_API_KEY"], "")
            self.assertEqual(rendered["CLOUDFLARE_TURNSTILE_API_TOKEN"], "")
            self.assertEqual(rendered["TURNSTILE_HOSTNAME_LIMIT"], "10")

    def test_render_keeps_turnstile_lifecycle_only_for_active_custom_domains(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            values = custom_domain_values()
            write_env(source, values)

            prepare.render_vps(source, output)

            rendered = load(output)
            self.assertEqual(
                rendered["CLOUDFLARE_TURNSTILE_API_TOKEN"],
                values["CLOUDFLARE_TURNSTILE_API_TOKEN"],
            )
            self.assertEqual(rendered["TURNSTILE_HOSTNAME_LIMIT"], "10")
            self.assertEqual(rendered["CUSTOM_DOMAIN_INFRASTRUCTURE_READY"], "true")

    def test_invalid_render_does_not_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            values = deployable_values()
            values["POLICY_REQUIRE_APPROVED"] = "false"
            write_env(source, values)
            output.write_text("sentinel\n")

            with self.assertRaisesRegex(ValueError, "POLICY_REQUIRE_APPROVED"):
                prepare.render_vps(source, output)
            self.assertEqual(output.read_text(), "sentinel\n")

    def test_runtime_validation_accepts_rendered_file_without_control_token(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "vps.env"
            write_env(source, deployable_values())
            prepare.render_vps(source, output)

            prepare.validate_runtime_file(output)
            stdout = io.StringIO()
            with contextlib.redirect_stdout(stdout):
                prepare.main(["validate-runtime", "--input", str(output)])
            self.assertEqual(
                stdout.getvalue(), "Sanitized VPS environment is structurally valid.\n"
            )
            rendered = load(output)
            self.assertNotIn("HOSTINGER_API_TOKEN", rendered)

    def test_runtime_validation_rejects_missing_or_unexpected_labels(self):
        values = prepare.runtime_values(deployable_values())
        missing = dict(values)
        missing.pop("SESSION_SECRET")
        with self.assertRaisesRegex(
            ValueError, "missing VPS runtime labels: SESSION_SECRET"
        ):
            prepare.validate_runtime_values(missing)

        unexpected = dict(values)
        unexpected["HOSTINGER_API_TOKEN"] = "must-stay-local"
        with self.assertRaisesRegex(
            ValueError, "unexpected VPS runtime labels: HOSTINGER_API_TOKEN"
        ):
            prepare.validate_runtime_values(unexpected)

    def test_compose_references_exactly_match_reviewed_runtime_labels(self):
        compose = (Path(__file__).resolve().parent / "compose.yml").read_text()
        restore = compose.split("  restore:", 1)[1].split(
            "  replicate-media:", 1
        )[0]
        persistent_compose = compose.replace(restore, "")
        references = set(
            re.findall(
                r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}",
                persistent_compose,
            )
        )
        self.assertEqual(references, set(prepare.COMPOSE_RUNTIME_LABELS))
        restore_references = set(
            re.findall(r"(?<!\$)\$\{([A-Z][A-Z0-9_]*)(?::-[^}]*)?\}", restore)
        )
        self.assertEqual(
            restore_references - set(prepare.COMPOSE_RUNTIME_LABELS),
            {
                "RESTORE_DATABASE_URL",
                "RESTORE_MANIFEST_KEY",
                "RESTORE_CONFIRMATION",
            },
        )

    def test_owner_env_example_excludes_one_shot_restore_authorization(self):
        restore_labels = {
            "RESTORE_DATABASE_URL",
            "RESTORE_MANIFEST_KEY",
            "RESTORE_CONFIRMATION",
        }
        owner_example = load(Path(__file__).resolve().parents[3] / ".env.example")
        self.assertTrue(restore_labels.isdisjoint(owner_example))
        self.assertTrue(restore_labels.isdisjoint(prepare.VPS_RUNTIME_LABELS))

    def test_source_and_host_contracts_are_covered_without_copying_source_only_labels(
        self,
    ):
        source_labels = set(load(EXAMPLE_INPUT))
        self.assertEqual(
            source_labels,
            set(prepare.COMPOSE_RUNTIME_LABELS)
            | set(prepare.SOURCE_ONLY_VALIDATION_LABELS)
            | {"HOSTINGER_VPS_PROFILE"},
        )
        self.assertEqual(
            set(HOST_HARDENING_REQUIRED), set(prepare.HOST_AUDIT_RUNTIME_LABELS)
        )
        self.assertTrue(
            prepare.SOURCE_ONLY_VALIDATION_LABELS.isdisjoint(prepare.VPS_RUNTIME_LABELS)
        )


if __name__ == "__main__":
    unittest.main()
