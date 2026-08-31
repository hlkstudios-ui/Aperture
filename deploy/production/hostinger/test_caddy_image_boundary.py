import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class CaddyImageBoundaryTests(unittest.TestCase):
    def test_caddy_is_built_from_the_fixed_release_with_a_patched_toolchain(self):
        dockerfile = (ROOT / "caddy.Dockerfile").read_text()

        self.assertRegex(
            dockerfile,
            re.compile(
                r"\A# syntax=docker/dockerfile:1\.18\n\n"
                r"FROM golang:1\.26\.7-alpine3\.24@sha256:[0-9a-f]{64} AS builder$",
                re.MULTILINE,
            ),
        )
        self.assertIn("GOTOOLCHAIN=local", dockerfile)
        self.assertIn("CGO_ENABLED=0", dockerfile)
        self.assertIn("GOFLAGS=-buildvcs=false", dockerfile)
        self.assertIn(
            "ADD --checksum=sha256:"
            "a593bd7077c76102ca76d19287a5e247d4e359dd67eddbc933f865afd3c131eb",
            dockerfile,
        )
        self.assertIn(
            "caddy/archive/e2eee6a7fce366321294c9c2a79f3146891dcbdf.tar.gz",
            dockerfile,
        )
        self.assertIn("golang.org/x/crypto@v0.55.0", dockerfile)
        self.assertIn("golang.org/x/net@v0.57.0", dockerfile)
        self.assertIn("google.golang.org/grpc@v1.82.1", dockerfile)
        self.assertIn("CustomVersion=v2.11.4", dockerfile)
        self.assertIn('test "$(/out/caddy version)" = "v2.11.4"', dockerfile)
        self.assertIn("go mod verify", dockerfile)
        self.assertIn("a092f0a81444e26ecdea87d58858b3511737929cbeed4ab4d675153a8d3db51d", dockerfile)
        self.assertIn("5c04f692e2acc5bba059e6dfda5305d10acc087196c080ab2a006f364298cb24", dockerfile)
        self.assertIn("-trimpath", dockerfile)

    def test_caddy_runtime_is_pinned_distroless_and_nonroot(self):
        dockerfile = (ROOT / "caddy.Dockerfile").read_text()
        runtime = dockerfile.split(
            "FROM gcr.io/distroless/static-debian13:nonroot@sha256:", maxsplit=1
        )[1]

        self.assertRegex(runtime, r"\A[0-9a-f]{64}\n")
        self.assertIn("USER nonroot", runtime)
        self.assertIn('ENTRYPOINT ["/usr/bin/caddy"]', runtime)
        self.assertIn('org.opencontainers.image.version="v2.11.4"', runtime)
        self.assertIn(
            'org.opencontainers.image.revision="e2eee6a7fce366321294c9c2a79f3146891dcbdf"',
            runtime,
        )
        self.assertIn("--chown=65532:65532", runtime)
        self.assertNotIn("apk ", runtime)
        self.assertNotIn("curl", runtime)
        self.assertNotIn("/bin/sh", runtime)

    def test_compose_keeps_caddy_read_only_and_unprivileged(self):
        compose = (ROOT / "compose.yml").read_text()
        service = compose.split("  caddy:", 1)[1].split("  maintenance:", 1)[0]

        self.assertIn("read_only: true", service)
        self.assertIn("cap_drop: [ALL]", service)
        self.assertNotIn("cap_add:", service)
        self.assertIn("security_opt: [no-new-privileges:true]", service)
        self.assertIn('tmpfs: ["/tmp:size=64m,mode=1777"]', service)


if __name__ == "__main__":
    unittest.main()
