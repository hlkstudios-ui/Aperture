import unittest

from validate_config import DEFAULT_INPUT, load, validate


class PrivateStudioConfigTests(unittest.TestCase):
    def test_dummy_inputs_are_structurally_valid(self):
        validate(load(DEFAULT_INPUT), deploy=False)

    def test_dummy_inputs_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(DEFAULT_INPUT), deploy=True)

    def test_origin_host_must_match(self):
        values = load(DEFAULT_INPUT)
        values["PUBLIC_APP_HOST"] = "different.example.com"
        with self.assertRaisesRegex(ValueError, "must match"):
            validate(values, deploy=False)

    def test_edge_secrets_must_be_independent_for_deploy(self):
        values = load(DEFAULT_INPUT)
        values = {key: value.replace("DUMMY_", "real_") for key, value in values.items()}
        values["TAILSCALE_AUTH_KEY"] = "tskey-" + "x" * 48
        values["STUDIO_EDGE_SECRET"] = "x" * 48
        values["ORIGIN_EDGE_SECRET"] = values["STUDIO_EDGE_SECRET"]
        with self.assertRaisesRegex(ValueError, "must be independent"):
            validate(values, deploy=True)


if __name__ == "__main__":
    unittest.main()
