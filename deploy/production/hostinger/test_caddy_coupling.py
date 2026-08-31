import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import validate_caddy_coupling as coupling


IMAGE = "registry.example/aperture-caddy@sha256:" + "a" * 64


def write_env(path: Path, image: str) -> None:
    path.write_text(f"CADDY_IMAGE={image}\n", encoding="utf-8")


class CaddyCouplingTests(unittest.TestCase):
    def test_artifact_check_requires_one_exact_immutable_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            public = Path(directory) / "public.env"
            private = Path(directory) / "private.env"
            write_env(public, IMAGE)
            write_env(private, IMAGE)
            self.assertEqual(coupling.artifact_image(public, private), IMAGE)

            write_env(private, "registry.example/aperture-caddy@sha256:" + "b" * 64)
            with self.assertRaisesRegex(coupling.CouplingError, "values differ"):
                coupling.artifact_image(public, private)

            write_env(private, "registry.example/aperture-caddy:latest")
            with self.assertRaisesRegex(coupling.CouplingError, "immutable"):
                coupling.artifact_image(public, private)

            dummy = "dummy.registry.example/aperture-caddy@sha256:" + "0" * 64
            write_env(public, dummy)
            write_env(private, dummy)
            with self.assertRaisesRegex(coupling.CouplingError, "non-dummy"):
                coupling.artifact_image(public, private)

    def test_container_check_requires_exact_image_nonroot_and_running(self):
        record = [
            {
                "Config": {
                    "Image": IMAGE,
                    "User": "nonroot",
                    "Labels": {"com.docker.compose.service": "caddy"},
                },
                "State": {"Running": True, "Health": {"Status": "healthy"}},
            }
        ]
        with mock.patch.object(coupling, "run_command", return_value=json.dumps(record)):
            coupling.validate_container(
                "container-id",
                service="caddy",
                expected_image=IMAGE,
                require_healthy=True,
            )

        record[0]["Config"]["Image"] = "registry.example/old@sha256:" + "b" * 64
        with mock.patch.object(coupling, "run_command", return_value=json.dumps(record)):
            with self.assertRaisesRegex(coupling.CouplingError, "image mismatch"):
                coupling.validate_container(
                    "container-id",
                    service="caddy",
                    expected_image=IMAGE,
                    require_healthy=True,
                )

    def test_running_contract_checks_both_compose_services(self):
        with (
            mock.patch.object(
                coupling,
                "compose_container_id",
                side_effect=("public-id", "private-id"),
            ) as container_id,
            mock.patch.object(coupling, "validate_container") as validate,
        ):
            coupling.validate_running(
                public_env=Path("public.env"),
                private_env=Path("private.env"),
                public_compose=Path("public.yml"),
                private_compose=Path("private.yml"),
                expected_image=IMAGE,
            )
        self.assertEqual(container_id.call_count, 2)
        self.assertEqual(validate.call_count, 2)
        self.assertEqual(validate.call_args_list[0].kwargs["service"], "caddy")
        self.assertEqual(
            validate.call_args_list[1].kwargs["service"], "studio-gateway"
        )
        self.assertTrue(validate.call_args_list[0].kwargs["require_healthy"])
        self.assertFalse(validate.call_args_list[1].kwargs["require_healthy"])

    def test_cli_failure_is_secret_free(self):
        secret_like_image = "registry.example/private-caddy@sha256:" + "f" * 64
        with (
            mock.patch.object(
                coupling,
                "artifact_image",
                side_effect=coupling.CouplingError(secret_like_image),
            ),
            contextlib.redirect_stderr(io.StringIO()) as stderr,
        ):
            self.assertEqual(coupling.main([]), 1)
        self.assertNotIn(secret_like_image, stderr.getvalue())
        self.assertEqual(
            json.loads(stderr.getvalue()),
            {"event": "caddy.coupling", "status": "fail"},
        )


if __name__ == "__main__":
    unittest.main()
