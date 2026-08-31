# syntax=docker/dockerfile:1.18

FROM golang:1.26.7-alpine3.24@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS builder

ARG TARGETOS=linux
ARG TARGETARCH
ENV CGO_ENABLED=0 \
    GOFLAGS="-mod=readonly -buildvcs=false" \
    GOTOOLCHAIN=local

WORKDIR /src/node-exporter
ADD --checksum=sha256:cfec7478aa9bfd011f29df084584b7c7b68dfef85a24d28e9d6d5f88224f83c3 \
    https://github.com/prometheus/node_exporter/archive/6044da783597cc3b57aef7580ddcdcff58a4ee99.tar.gz \
    /tmp/node-exporter-source.tar.gz
RUN tar --extract --gzip --file=/tmp/node-exporter-source.tar.gz \
        --strip-components=1 --directory=/src/node-exporter \
    && rm /tmp/node-exporter-source.tar.gz \
    && grep -Fxq "1.12.1" VERSION \
    && GOFLAGS= go get \
        golang.org/x/crypto@v0.55.0 \
        golang.org/x/net@v0.57.0 \
    && go mod download \
    && go mod verify \
    && test "$(sha256sum go.mod)" = "97771f3e918c850a6eee90091d30fa34da928731c9db061e758df2ad5cebdfb5  go.mod" \
    && test "$(sha256sum go.sum)" = "3dabbe3836fce2c930051905d8387c1244a72aefc3207b1f8afc9f14826d9d61  go.sum" \
    && mkdir -p /out \
    && GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" go build \
        -trimpath \
        -ldflags="-s -w -buildid= \
          -X github.com/prometheus/common/version.Version=1.12.1 \
          -X github.com/prometheus/common/version.Revision=6044da783597cc3b57aef7580ddcdcff58a4ee99 \
          -X github.com/prometheus/common/version.Branch=HEAD \
          -X github.com/prometheus/common/version.BuildUser=aperture@build \
          -X github.com/prometheus/common/version.BuildDate=20260714-120406" \
        -o /out/node_exporter . \
    && /out/node_exporter --version 2>&1 | grep -Fq "version 1.12.1" \
    && /out/node_exporter --version 2>&1 | grep -Fq "revision: 6044da783597cc3b57aef7580ddcdcff58a4ee99"

FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7 AS runtime

LABEL org.opencontainers.image.authors="The Prometheus Authors" \
      org.opencontainers.image.title="Aperture node_exporter" \
      org.opencontainers.image.description="Prometheus node_exporter rebuilt from its exact release source with a patched Go toolchain" \
      org.opencontainers.image.source="https://github.com/prometheus/node_exporter" \
      org.opencontainers.image.revision="6044da783597cc3b57aef7580ddcdcff58a4ee99" \
      org.opencontainers.image.version="1.12.1" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=builder --chown=65532:65532 --chmod=0555 /out/node_exporter /bin/node_exporter
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/node-exporter/LICENSE /licenses/node-exporter/LICENSE
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/node-exporter/NOTICE /licenses/node-exporter/NOTICE

USER nonroot
EXPOSE 9100
ENTRYPOINT ["/bin/node_exporter"]
