import unittest

import yaml

from render_config import EXAMPLE_INPUT, load_values, render_app, validate_auth_values


class DigitalOceanAuthConfigurationTests(unittest.TestCase):
    def test_dummy_auth_pipeline_renders_with_secret_separation(self):
        values = load_values(EXAMPLE_INPUT)
        values["OAUTH_GOOGLE_CLIENT_ID"] = "google-client"
        values["OAUTH_GOOGLE_CLIENT_SECRET"] = "google-secret"
        values["BRAND_AI_PROVIDER"] = "openai"
        values["OPENAI_API_KEY"] = "test-project-key"
        document = yaml.safe_load(render_app(values))
        api = next(service for service in document["services"] if service["name"] == "api")
        web = next(service for service in document["services"] if service["name"] == "web")
        api_keys = {item["key"] for item in api["envs"]}
        web_keys = {item["key"] for item in web["envs"]}
        worker_keys = {
            item["key"]
            for worker in document["workers"]
            for item in worker["envs"]
        }

        self.assertIn("TURNSTILE_SECRET_KEY", api_keys)
        self.assertIn("OAUTH_GOOGLE_CLIENT_SECRET", api_keys)
        self.assertIn("OPENAI_API_KEY", api_keys)
        self.assertNotIn("NEXT_PUBLIC_TURNSTILE_SITE_KEY", api_keys)
        self.assertIn("NEXT_PUBLIC_TURNSTILE_SITE_KEY", web_keys)
        self.assertNotIn("TURNSTILE_SECRET_KEY", web_keys)
        self.assertNotIn("OAUTH_GOOGLE_CLIENT_SECRET", web_keys)
        self.assertNotIn("OPENAI_API_KEY", web_keys)
        self.assertNotIn("OAUTH_APPLE_CLIENT_SECRET", api_keys)
        self.assertNotIn("TURNSTILE_SECRET_KEY", worker_keys)
        self.assertNotIn("OAUTH_GOOGLE_CLIENT_SECRET", worker_keys)
        self.assertNotIn("OPENAI_API_KEY", worker_keys)

    def test_captcha_requires_public_and_private_turnstile_keys(self):
        values = load_values(EXAMPLE_INPUT)
        values["NEXT_PUBLIC_TURNSTILE_SITE_KEY"] = ""
        with self.assertRaisesRegex(ValueError, "requires both"):
            validate_auth_values(values)

        values["CAPTCHA_REQUIRED"] = "false"
        values["TURNSTILE_SECRET_KEY"] = ""
        validate_auth_values(values)

    def test_oauth_provider_credentials_are_optional_but_atomic(self):
        values = load_values(EXAMPLE_INPUT)
        values["OAUTH_APPLE_CLIENT_ID"] = "apple-client"
        with self.assertRaisesRegex(ValueError, "must be configured together"):
            validate_auth_values(values)
        values["OAUTH_APPLE_CLIENT_SECRET"] = "apple-secret"
        validate_auth_values(values)

    def test_copy_assistant_requires_an_api_key_when_enabled(self):
        values = load_values(EXAMPLE_INPUT)
        values["BRAND_AI_PROVIDER"] = "openai"
        with self.assertRaisesRegex(ValueError, "requires OPENAI_API_KEY"):
            validate_auth_values(values)


if __name__ == "__main__":
    unittest.main()
