import unittest
from pathlib import Path

from validate_config import EXAMPLE_INPUT, load, validate

ROOT = Path(__file__).resolve().parent


class FreeTierConfigTests(unittest.TestCase):
    def test_runtime_pins_and_staging_safety_gates_are_explicit(self):
        dockerfile = (ROOT / "api.Dockerfile").read_text()
        manifest = (ROOT / "render.yaml").read_text()

        self.assertTrue(dockerfile.startswith("FROM python:3.12.14-alpine3.24\n"))
        self.assertIn("apk add --no-cache ffmpeg ca-certificates", dockerfile)
        self.assertIn("USER aperture", dockerfile)
        self.assertEqual(manifest.count("NODE_VERSION, value: 24.20.0"), 1)
        self.assertEqual(manifest.count('autoDeployTrigger: "off"'), 2)
        self.assertIn("BILLING_PROVIDER, value: disabled", manifest)
        self.assertIn('POLICY_REQUIRE_APPROVED, value: "false"', manifest)
        self.assertIn('UPLOAD_MAX_BYTES, value: "52428800"', manifest)

    def test_dummy_template_is_structurally_valid(self):
        validate(load(EXAMPLE_INPUT), deploy=False)

    def test_dummy_template_cannot_be_deployed(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(EXAMPLE_INPUT), deploy=True)

    def test_dependencies_are_fail_closed(self):
        values = load(EXAMPLE_INPUT)
        values["FEATURE_SCENE_LENS_ENABLED"] = "false"
        with self.assertRaisesRegex(ValueError, "requires SceneLens"):
            validate(values, deploy=False)

    def test_copy_assistant_requires_a_server_key_when_enabled(self):
        values = load(EXAMPLE_INPUT)
        values["BRAND_AI_PROVIDER"] = "openai"
        with self.assertRaisesRegex(ValueError, "requires OPENAI_API_KEY"):
            validate(values, deploy=False)

    def test_copy_assistant_rejects_fine_tuned_models(self):
        values = load(EXAMPLE_INPUT)
        values["BRAND_AI_MODEL"] = "ft:gpt-5-mini:example:brand"
        with self.assertRaisesRegex(ValueError, "fine-tuned"):
            validate(values, deploy=False)


if __name__ == "__main__":
    unittest.main()
