import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class BackupImageBoundaryTests(unittest.TestCase):
    def test_backup_image_is_minimal_pinned_and_nonroot(self):
        dockerfile = (ROOT / "backup.Dockerfile").read_text()

        self.assertRegex(
            dockerfile,
            re.compile(
                r"\AFROM python:3\.12\.14-alpine3\.23@sha256:[0-9a-f]{64}$",
                re.MULTILINE,
            ),
        )
        self.assertNotIn("FROM postgres:", dockerfile)
        self.assertNotIn("postgresql17=", dockerfile)
        self.assertIn("postgresql17-client=17.11-r0", dockerfile)
        self.assertIn("libcrypto3=3.5.8-r0", dockerfile)
        self.assertIn("libssl3=3.5.8-r0", dockerfile)
        self.assertIn("sqlite-libs=3.53.4-r0", dockerfile)
        self.assertIn("boto3==1.42.54", dockerfile)
        self.assertIn("PYTHONDONTWRITEBYTECODE=1", dockerfile)
        self.assertIn("COPY --chmod=0444", dockerfile)
        self.assertIn("USER 10001:10001", dockerfile)
        self.assertIn("ENTRYPOINT []", dockerfile)

    def test_backup_and_restore_keep_the_read_only_runtime_contract(self):
        compose = (ROOT / "compose.yml").read_text()
        backup = compose.split("  backup:", 1)[1].split("  restore:", 1)[0]
        restore = compose.split("  restore:", 1)[1].split("  replicate-media:", 1)[0]

        for service in (backup, restore):
            self.assertIn("read_only: true", service)
            self.assertIn("cap_drop: [ALL]", service)
            self.assertIn("security_opt: [no-new-privileges:true]", service)
            self.assertIn('tmpfs: ["/tmp:size=8g,mode=1777"]', service)


if __name__ == "__main__":
    unittest.main()
