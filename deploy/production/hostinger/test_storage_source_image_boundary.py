import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOCKERFILE = ROOT / "storage.Dockerfile"
HEALTHCHECK = ROOT / "storage_healthcheck.go"

RELEASE = "RELEASE.2025-10-15T17-29-55Z"
REVISION = "9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a"
SOURCE_SHA256 = "45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841"
GO_MOD_SHA256 = "bf79454a319f9350d8c2af4c34b20a91d7b7d7d0c0ffb76dc60e54006bfed823"
GO_SUM_SHA256 = "53902a66e120baee850b88a72f5ef945d8f6483320abf2c4c87add6522ed1277"
REMEDIATED_MODULES = {
    "github.com/apache/thrift": "v0.23.0",
    "github.com/buger/jsonparser": "v1.1.2",
    "github.com/go-jose/go-jose/v4": "v4.1.4",
    "github.com/prometheus/prometheus": "v0.311.3",
    "go.etcd.io/etcd/client/pkg/v3": "v3.5.33",
    "go.opentelemetry.io/otel/sdk": "v1.43.0",
    "golang.org/x/crypto": "v0.55.0",
    "golang.org/x/net": "v0.57.0",
    "google.golang.org/grpc": "v1.82.1",
}


def test_storage_build_pins_the_official_security_source_and_toolchain() -> None:
    dockerfile = DOCKERFILE.read_text()

    assert re.search(
        r"^FROM golang:1\.26\.7-alpine3\.24@sha256:[0-9a-f]{64} AS builder$",
        dockerfile,
        re.MULTILINE,
    )
    assert f"ADD --checksum=sha256:{SOURCE_SHA256}" in dockerfile
    assert f"minio/archive/{REVISION}.tar.gz" in dockerfile
    assert "GOTOOLCHAIN=local" in dockerfile
    assert 'GOFLAGS="-mod=readonly -buildvcs=false"' in dockerfile
    for module, version in REMEDIATED_MODULES.items():
        assert f"{module}@{version}" in dockerfile
    assert "GOFLAGS= go get" in dockerfile
    assert f'"{GO_MOD_SHA256}  go.mod"' in dockerfile
    assert f'"{GO_SUM_SHA256}  go.sum"' in dockerfile
    assert "go mod verify" in dockerfile
    assert "-trimpath" in dockerfile
    assert f"cmd.ReleaseTag={RELEASE}" in dockerfile
    assert f"cmd.CommitID={REVISION}" in dockerfile
    assert f'org.opencontainers.image.revision="{REVISION}"' in dockerfile
    assert f'org.opencontainers.image.version="{RELEASE}"' in dockerfile


def test_storage_runtime_is_digest_pinned_distroless_and_nonroot() -> None:
    dockerfile = DOCKERFILE.read_text()
    runtime = dockerfile.split(
        "FROM gcr.io/distroless/static-debian13:nonroot@sha256:", maxsplit=1
    )[1]

    assert re.match(r"[0-9a-f]{64} AS runtime", runtime)
    assert "USER nonroot" in runtime
    assert 'ENTRYPOINT ["/usr/local/bin/minio"]' in runtime
    assert 'VOLUME ["/data"]' in runtime
    assert "--chown=65532:65532" in runtime
    assert "--chmod=0555" in runtime
    assert "COPY --from=builder" in runtime
    assert "apk " not in runtime
    assert "apt-get" not in runtime
    assert "RUN " not in runtime
    assert "/out/curl /usr/bin/curl" in runtime
    assert "/bin/sh" not in runtime
    assert "COPY . ." not in dockerfile


def test_compatibility_health_probe_is_fixed_to_loopback_readiness() -> None:
    source = HEALTHCHECK.read_text()

    assert 'const readyURL = "http://localhost:9000/minio/health/ready"' in source
    assert 'os.Args[1] != "-f"' in source
    assert "os.Args[2] != readyURL" in source
    assert "Proxy:               nil" in source
    assert "return http.ErrUseLastResponse" in source
    assert "response.StatusCode != http.StatusOK" in source
