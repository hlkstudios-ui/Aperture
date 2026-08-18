import unittest

from validate_config import DEFAULT_INPUT, load, validate


class HostingerConfigTests(unittest.TestCase):
    def test_dummy_file_is_structurally_valid(self):
        validate(load(DEFAULT_INPUT), deploy=False)

    def test_dummy_file_cannot_deploy(self):
        with self.assertRaisesRegex(ValueError, "replace dummy labels"):
            validate(load(DEFAULT_INPUT), deploy=True)

    def test_public_hosts_must_be_distinct(self):
        values = load(DEFAULT_INPUT)
        values["STORAGE_HOSTNAME"] = values["WEB_HOSTNAME"]
        with self.assertRaisesRegex(ValueError, "distinct"):
            validate(values, deploy=False)

    def test_memory_profile_reserves_host_headroom(self):
        values = load(DEFAULT_INPUT)
        values["HOSTINGER_VPS_MEMORY_GB"] = "16"
        with self.assertRaisesRegex(ValueError, "20% VPS headroom"):
            validate(values, deploy=False)

    def test_mutable_image_tag_is_rejected(self):
        values = load(DEFAULT_INPUT)
        values["API_IMAGE"] = "registry.example/aperture-api:latest"
        with self.assertRaisesRegex(ValueError, "immutable registry digest"):
            validate(values, deploy=False)


if __name__ == "__main__":
    unittest.main()
