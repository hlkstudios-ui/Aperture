import os
import re
import stat
import tempfile
import unittest
from pathlib import Path

from render_runtime import RUNTIME_LABELS, render
from validate_config import load, validate


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parents[2]
FIXTURE_INPUT = ROOT / "credentials.example.env"


def deployable_values() -> dict[str, str]:
    values = load(FIXTURE_INPUT)
    values = {key: value.replace("DUMMY_", "production_") for key, value in values.items()}
    values["TAILSCALE_AUTH_KEY"] = ""
    values["CADDY_IMAGE"] = "registry.example/aperture-caddy@sha256:" + "c" * 64
    values["STUDIO_EDGE_SECRET"] = "s" * 48
    values["ORIGIN_EDGE_SECRET"] = "o" * 48
    return values


class PrivateStudioConfigTests(unittest.TestCase):
    def test_dummy_inputs_are_structurally_valid(self):
        validate(load(FIXTURE_INPUT), deploy=False)

    def test_dummy_inputs_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(FIXTURE_INPUT), deploy=True)

    def test_origin_host_must_match(self):
        values = load(FIXTURE_INPUT)
        values["PUBLIC_APP_HOST"] = "different.example.com"
        with self.assertRaisesRegex(ValueError, "must match"):
            validate(values, deploy=False)

    def test_edge_secrets_must_be_independent_for_deploy(self):
        values = deployable_values()
        values["TAILSCALE_AUTH_KEY"] = "tskey-" + "x" * 48
        values["STUDIO_EDGE_SECRET"] = "x" * 48
        values["ORIGIN_EDGE_SECRET"] = values["STUDIO_EDGE_SECRET"]
        with self.assertRaisesRegex(ValueError, "must be independent"):
            validate(values, deploy=True)

    def test_consumed_tailscale_auth_key_can_be_cleared_before_deploy(self):
        values = deployable_values()
        values["TAILSCALE_AUTH_KEY"] = ""
        values["STUDIO_EDGE_SECRET"] = "s" * 48
        values["ORIGIN_EDGE_SECRET"] = "o" * 48

        validate(values, deploy=True)


class DeploymentBoundaryTests(unittest.TestCase):
    def test_gateway_strips_public_custom_domain_identity(self):
        caddyfile = (ROOT / "Caddyfile").read_text()
        self.assertIn("header_up X-Forwarded-Host {$PUBLIC_APP_HOST}", caddyfile)
        for header in (
            "X-Aperture-Public-Host",
            "X-Aperture-Public-Origin",
            "X-Aperture-Edge-Secret",
        ):
            self.assertIn(f"header_up -{header}", caddyfile)

    def test_gateway_caddy_keeps_only_its_required_file_capability(self):
        compose = (ROOT / "compose.yml").read_text()
        self.assertIn("cap_drop:\n      - ALL", compose)
        self.assertNotIn("cap_add:", compose)
        self.assertIn("image: ${CADDY_IMAGE}", compose)
        self.assertIn("uid=65532,gid=65532", compose)

    def test_gateway_image_must_be_an_immutable_digest(self):
        values = deployable_values()
        values["CADDY_IMAGE"] = "registry.example/aperture-caddy:latest"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=True)

    def test_gateway_container_receives_only_its_four_runtime_values(self):
        compose = (ROOT / "compose.yml").read_text()
        self.assertNotIn("env_file:", compose)

        match = re.search(
            r"(?m)^    environment:\n(?P<body>(?:^      [A-Z][A-Z0-9_]*: .*\n)+)",
            compose,
        )
        self.assertIsNotNone(match, "studio-gateway must have an environment allowlist")
        entries = dict(
            line.strip().split(":", 1)
            for line in match.group("body").splitlines()
        )
        self.assertEqual(
            entries,
            {
                "PUBLIC_APP_ORIGIN": ' "${PUBLIC_APP_ORIGIN}"',
                "PUBLIC_APP_HOST": ' "${PUBLIC_APP_HOST}"',
                "ORIGIN_EDGE_SECRET": ' "${ORIGIN_EDGE_SECRET}"',
                "STUDIO_EDGE_SECRET": ' "${STUDIO_EDGE_SECRET}"',
            },
        )

    def test_docker_build_context_excludes_generated_runtime_artifacts(self):
        patterns = {
            line.strip()
            for line in (PROJECT_ROOT / ".dockerignore").read_text().splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        }
        self.assertTrue(
            {"**/*.log", "**/venv", "**/venv/**", "**/*.tsbuildinfo"} <= patterns
        )

    def test_runtime_renderer_writes_only_gateway_values(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "owner.env"
            output = Path(directory) / "studio.env"
            source.write_text(
                "".join(f"{key}={value}\n" for key, value in deployable_values().items()),
                encoding="utf-8",
            )

            render(source, output)

            rendered = dict(
                line.split("=", 1) for line in output.read_text(encoding="utf-8").splitlines()
            )
            self.assertEqual(tuple(rendered), RUNTIME_LABELS)
            self.assertNotIn("TAILSCALE_AUTH_KEY", rendered)
            self.assertNotIn("TAILSCALE_OWNER_EMAIL", rendered)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)


if __name__ == "__main__":
    unittest.main()
