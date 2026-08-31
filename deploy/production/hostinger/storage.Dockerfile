# syntax=docker/dockerfile:1.18

# MinIO Community Edition became source-only with this security release. Pin both
# the supported Go toolchain image and the exact upstream source archive so a
# moved tag or changed download fails the build instead of changing the binary.
FROM golang:1.26.7-alpine3.24@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS builder

ARG TARGETOS=linux
ARG TARGETARCH
ENV CGO_ENABLED=0 \
    GOFLAGS="-mod=readonly -buildvcs=false" \
    GOTOOLCHAIN=local \
    SOURCE_DATE_EPOCH=1760549395

WORKDIR /src/minio
ADD --checksum=sha256:45521908307306e925c98d629e1c17d78c8b72b6ee242b1bfb1409f7d8ee5841 \
    https://github.com/minio/minio/archive/9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a.tar.gz \
    /tmp/minio-source.tar.gz
# The final community release predates these upstream security fixes. Keep
# MinIO's application source exact while pinning its vulnerable Go modules to
# the first versions Docker Scout identifies as remediated.
RUN tar --extract --gzip --file=/tmp/minio-source.tar.gz \
        --strip-components=1 --directory=/src/minio \
    && rm /tmp/minio-source.tar.gz \
    && grep -Fxq "toolchain go1.24.8" go.mod \
    && GOFLAGS= go get \
        github.com/apache/thrift@v0.23.0 \
        github.com/buger/jsonparser@v1.1.2 \
        github.com/go-jose/go-jose/v4@v4.1.4 \
        github.com/prometheus/prometheus@v0.311.3 \
        go.etcd.io/etcd/client/pkg/v3@v3.5.33 \
        go.opentelemetry.io/otel/sdk@v1.43.0 \
        golang.org/x/crypto@v0.55.0 \
        golang.org/x/net@v0.57.0 \
        google.golang.org/grpc@v1.82.1 \
    && mkdir -p /out \
    && GOFLAGS="-mod=mod -buildvcs=false" GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" go build \
        -trimpath \
        -ldflags="-s -w -buildid= \
          -X github.com/minio/minio/cmd.Version=2025-10-15T17:29:55Z \
          -X github.com/minio/minio/cmd.ReleaseTag=RELEASE.2025-10-15T17-29-55Z \
          -X github.com/minio/minio/cmd.CommitID=9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a \
          -X github.com/minio/minio/cmd.ShortCommitID=9e49d5e7a648 \
          -X github.com/minio/minio/cmd.CopyrightYear=2025" \
        -o /out/minio . \
    && go mod verify
RUN test "$(sha256sum go.mod)" = "bf79454a319f9350d8c2af4c34b20a91d7b7d7d0c0ffb76dc60e54006bfed823  go.mod" \
    && test "$(sha256sum go.sum)" = "53902a66e120baee850b88a72f5ef945d8f6483320abf2c4c87add6522ed1277  go.sum"

# Preserve the existing Compose health command without carrying a shell, curl,
# or a package manager into the runtime image. This static probe accepts only
# the fixed loopback readiness URL used by this deployment.
COPY deploy/production/hostinger/storage_healthcheck.go /tmp/storage_healthcheck.go
RUN GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" go build \
        -trimpath -ldflags="-s -w -buildid=" \
        -o /out/curl /tmp/storage_healthcheck.go \
    && mkdir -p /out/data

FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7 AS runtime

LABEL org.opencontainers.image.title="Aperture MinIO storage" \
      org.opencontainers.image.description="Exact MinIO Community Edition security-release source with pinned remediated Go dependencies" \
      org.opencontainers.image.source="https://github.com/minio/minio" \
      org.opencontainers.image.revision="9e49d5e7a648f00e26f2246f4dc28e6b07f8c84a" \
      org.opencontainers.image.version="RELEASE.2025-10-15T17-29-55Z" \
      org.opencontainers.image.licenses="AGPL-3.0-or-later"

ENV HOME=/tmp
COPY --from=builder --chown=65532:65532 --chmod=0555 /out/minio /usr/local/bin/minio
COPY --from=builder --chown=65532:65532 --chmod=0555 /out/curl /usr/bin/curl
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/minio/LICENSE /licenses/minio/LICENSE
COPY --from=builder --chown=65532:65532 --chmod=0700 /out/data /data

USER nonroot
VOLUME ["/data"]
EXPOSE 9000 9001
ENTRYPOINT ["/usr/local/bin/minio"]
CMD ["server", "/data", "--console-address", ":9001"]
