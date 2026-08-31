import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class TailnetPolicyBoundaryTests(unittest.TestCase):
    def test_studio_https_and_ci_deploy_ssh_are_independently_scoped(self):
        policy = json.loads((ROOT / "tailnet-policy.example.hujson").read_text())

        self.assertEqual(
            policy["tagOwners"],
            {
                "tag:aperture-studio": ["autogroup:owner"],
                "tag:aperture-ci": ["autogroup:owner"],
            },
        )
        self.assertEqual(
            policy["grants"],
            [
                {
                    "src": ["autogroup:owner"],
                    "dst": ["autogroup:self"],
                    "ip": ["*"],
                },
                {
                    "src": ["autogroup:owner"],
                    "dst": ["tag:aperture-studio"],
                    "ip": ["tcp:443"],
                },
                {
                    "src": ["tag:aperture-ci"],
                    "dst": ["tag:aperture-studio"],
                    "ip": ["tcp:22"],
                },
            ],
        )
        self.assertNotIn("ssh", policy)
        self.assertNotIn("nodeAttrs", policy)
        self.assertEqual(
            policy["tests"],
            [
                {
                    "src": "DUMMY_owner@example.com",
                    "accept": ["tag:aperture-studio:443"],
                    "deny": ["tag:aperture-studio:22"],
                },
                {
                    "src": "tag:aperture-ci",
                    "accept": ["tag:aperture-studio:22"],
                    "deny": ["tag:aperture-studio:443"],
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
