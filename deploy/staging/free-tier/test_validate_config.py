import unittest

from validate_config import load, validate, DEFAULT_INPUT


class FreeTierConfigTests(unittest.TestCase):
    def test_dummy_template_is_structurally_valid(self):
        validate(load(DEFAULT_INPUT), deploy=False)

    def test_dummy_template_cannot_be_deployed(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(DEFAULT_INPUT), deploy=True)

    def test_dependencies_are_fail_closed(self):
        values = load(DEFAULT_INPUT)
        values["FEATURE_SCENE_LENS_ENABLED"] = "false"
        with self.assertRaisesRegex(ValueError, "requires SceneLens"):
            validate(values, deploy=False)


if __name__ == "__main__":
    unittest.main()
