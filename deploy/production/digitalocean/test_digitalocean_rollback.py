import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import digitalocean_rollback as rollback


class DigitalOceanRollbackConfigurationTests(unittest.TestCase):
    def test_dummy_mode_does_not_require_an_input_file(self):
        missing = Path("definitely-not-present.env")
        self.assertEqual(rollback.configuration("dummy", missing)["token"], "DUMMY_NOT_USED")

    def test_example_fixture_loads_without_exporting_it_through_a_shell(self):
        fixture = Path(__file__).resolve().parent / "rollback.example.env"
        with mock.patch.dict(os.environ, {}, clear=True):
            values = rollback.configuration("inspect", fixture)
        self.assertEqual(set(values), {"app_id", "deployment_id", "token"})

    def test_process_environment_overrides_file_values(self):
        fixture = Path(__file__).resolve().parent / "rollback.example.env"
        override = "33333333-3333-4333-8333-333333333333"
        with mock.patch.dict(os.environ, {"DIGITALOCEAN_APP_ID": override}, clear=True):
            values = rollback.configuration("inspect", fixture)
        self.assertEqual(values["app_id"], override)

    def test_shared_file_ignores_unrelated_labels_and_rejects_duplicates(self):
        fixture = Path(__file__).resolve().parent / "rollback.example.env"
        with tempfile.TemporaryDirectory() as directory:
            shared = Path(directory) / ".env"
            shared.write_text(fixture.read_text() + "\nUNRELATED_LABEL=ignored\n")
            with mock.patch.dict(os.environ, {}, clear=True):
                rollback.configuration("inspect", shared)
            shared.write_text(shared.read_text() + "\nDIGITALOCEAN_APP_ID=duplicate\n")
            with self.assertRaisesRegex(ValueError, "duplicate rollback label"):
                rollback.load_values(shared)


if __name__ == "__main__":
    unittest.main()
