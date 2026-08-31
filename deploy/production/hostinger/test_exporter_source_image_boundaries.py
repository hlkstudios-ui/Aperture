import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
BUILDER = (
    "golang:1.26.7-alpine3.24@sha256:"
    "28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468"
)
RUNTIME = (
    "gcr.io/distroless/static-debian13:nonroot@sha256:"
    "1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7"
)

EXPORTERS = {
    "node-exporter.Dockerfile": {
        "version": "1.12.1",
        "revision": "6044da783597cc3b57aef7580ddcdcff58a4ee99",
        "source_sha256": (
            "cfec7478aa9bfd011f29df084584b7c7b68dfef85a24d28e9d6d5f88224f83c3"
        ),
        "binary": "node_exporter",
        "port": "9100",
        "go_mod_sha256": (
            "97771f3e918c850a6eee90091d30fa34da928731c9db061e758df2ad5cebdfb5"
        ),
        "go_sum_sha256": (
            "3dabbe3836fce2c930051905d8387c1244a72aefc3207b1f8afc9f14826d9d61"
        ),
        "modules": {
            "golang.org/x/crypto": "v0.55.0",
            "golang.org/x/net": "v0.57.0",
        },
    },
    "blackbox-exporter.Dockerfile": {
        "version": "0.28.0",
        "revision": "5a059bee8d8ffa4e75947c5055fb0abeefc582e6",
        "source_sha256": (
            "12b6eb9b307ebc5e55eafe6eb503816756fa0c344854897fb5aeb687544999f9"
        ),
        "binary": "blackbox_exporter",
        "port": "9115",
        "go_mod_sha256": (
            "f7244986e469a6b4c29994d26d9b7631d17aa6ec118b39db53eef0214c40a292"
        ),
        "go_sum_sha256": (
            "b03e0e390718fff4c1d42cf60fd778c3489fa8d81c9481da14d699c049a888c0"
        ),
        "modules": {
            "golang.org/x/crypto": "v0.55.0",
            "golang.org/x/net": "v0.57.0",
            "google.golang.org/grpc": "v1.82.1",
        },
    },
}


def _dockerfile(name: str) -> str:
    return (ROOT / name).read_text()


def test_exporters_pin_exact_official_sources_and_patched_toolchain() -> None:
    for name, expected in EXPORTERS.items():
        dockerfile = _dockerfile(name)

        assert f"FROM {BUILDER} AS builder" in dockerfile
        assert "CGO_ENABLED=0" in dockerfile
        assert "GOTOOLCHAIN=local" in dockerfile
        assert 'GOFLAGS="-mod=readonly -buildvcs=false"' in dockerfile
        assert f"ADD --checksum=sha256:{expected['source_sha256']}" in dockerfile
        assert f"archive/{expected['revision']}.tar.gz" in dockerfile
        assert f'grep -Fxq "{expected["version"]}" VERSION' in dockerfile
        for module, version in expected["modules"].items():
            assert f"{module}@{version}" in dockerfile
        assert "go mod verify" in dockerfile
        assert f'"{expected["go_mod_sha256"]}  go.mod"' in dockerfile
        assert f'"{expected["go_sum_sha256"]}  go.sum"' in dockerfile
        assert "-trimpath" in dockerfile
        assert "-buildid=" in dockerfile
        assert f"version.Version={expected['version']}" in dockerfile
        assert f"version.Revision={expected['revision']}" in dockerfile
        assert f'org.opencontainers.image.revision="{expected["revision"]}"' in dockerfile
        assert f'org.opencontainers.image.version="{expected["version"]}"' in dockerfile


def test_exporter_runtimes_are_minimal_pinned_and_nonroot() -> None:
    for name, expected in EXPORTERS.items():
        dockerfile = _dockerfile(name)
        runtime = dockerfile.split(f"FROM {RUNTIME} AS runtime", maxsplit=1)[1]
        binary = expected["binary"]

        assert "USER nonroot" in runtime
        assert f'EXPOSE {expected["port"]}' in runtime
        assert f'ENTRYPOINT ["/bin/{binary}"]' in runtime
        assert "--chown=65532:65532" in runtime
        assert "--chmod=0555" in runtime
        assert "/licenses/" in runtime
        assert "LICENSE" in runtime
        assert "NOTICE" in runtime
        assert "RUN " not in runtime
        assert "apk " not in runtime
        assert "apt-get" not in runtime
        assert "/bin/sh" not in runtime
        assert "curl" not in runtime
        assert "COPY . ." not in dockerfile


def test_only_blackbox_carries_its_release_default_configuration() -> None:
    node = _dockerfile("node-exporter.Dockerfile")
    blackbox = _dockerfile("blackbox-exporter.Dockerfile")

    assert "CMD " not in node.split(" AS runtime", maxsplit=1)[1]
    assert re.search(
        r"COPY --from=builder .* /src/blackbox-exporter/blackbox\.yml "
        r"/etc/blackbox_exporter/config\.yml",
        blackbox,
    )
    assert 'CMD ["--config.file=/etc/blackbox_exporter/config.yml"]' in blackbox
