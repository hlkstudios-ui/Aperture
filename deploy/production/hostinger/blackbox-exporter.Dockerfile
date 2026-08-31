# syntax=docker/dockerfile:1.18

FROM golang:1.26.7-alpine3.24@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS builder

ARG TARGETOS=linux
ARG TARGETARCH
ENV CGO_ENABLED=0 \
    GOFLAGS="-mod=readonly -buildvcs=false" \
    GOTOOLCHAIN=local

WORKDIR /src/blackbox-exporter
ADD --checksum=sha256:12b6eb9b307ebc5e55eafe6eb503816756fa0c344854897fb5aeb687544999f9 \
    https://github.com/prometheus/blackbox_exporter/archive/5a059bee8d8ffa4e75947c5055fb0abeefc582e6.tar.gz \
    /tmp/blackbox-exporter-source.tar.gz
RUN tar --extract --gzip --file=/tmp/blackbox-exporter-source.tar.gz \
        --strip-components=1 --directory=/src/blackbox-exporter \
    && rm /tmp/blackbox-exporter-source.tar.gz \
    && grep -Fxq "0.28.0" VERSION \
    && GOFLAGS= go get \
        golang.org/x/crypto@v0.55.0 \
        golang.org/x/net@v0.57.0 \
        google.golang.org/grpc@v1.82.1 \
    && go mod download \
    && go mod verify \
    && test "$(sha256sum go.mod)" = "f7244986e469a6b4c29994d26d9b7631d17aa6ec118b39db53eef0214c40a292  go.mod" \
    && test "$(sha256sum go.sum)" = "b03e0e390718fff4c1d42cf60fd778c3489fa8d81c9481da14d699c049a888c0  go.sum" \
    && mkdir -p /out \
    && GOOS="${TARGETOS}" GOARCH="${TARGETARCH}" go build \
        -trimpath \
        -ldflags="-s -w -buildid= \
          -X github.com/prometheus/common/version.Version=0.28.0 \
          -X github.com/prometheus/common/version.Revision=5a059bee8d8ffa4e75947c5055fb0abeefc582e6 \
          -X github.com/prometheus/common/version.Branch=HEAD \
          -X github.com/prometheus/common/version.BuildUser=aperture@build \
          -X github.com/prometheus/common/version.BuildDate=20251204-192314" \
        -o /out/blackbox_exporter . \
    && /out/blackbox_exporter --version 2>&1 | grep -Fq "version 0.28.0" \
    && /out/blackbox_exporter --version 2>&1 | grep -Fq "revision: 5a059bee8d8ffa4e75947c5055fb0abeefc582e6"

FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7 AS runtime

LABEL org.opencontainers.image.authors="The Prometheus Authors" \
      org.opencontainers.image.title="Aperture blackbox_exporter" \
      org.opencontainers.image.description="Prometheus blackbox_exporter rebuilt from its exact release source with patched Go dependencies" \
      org.opencontainers.image.source="https://github.com/prometheus/blackbox_exporter" \
      org.opencontainers.image.revision="5a059bee8d8ffa4e75947c5055fb0abeefc582e6" \
      org.opencontainers.image.version="0.28.0" \
      org.opencontainers.image.licenses="Apache-2.0"

COPY --from=builder --chown=65532:65532 --chmod=0555 /out/blackbox_exporter /bin/blackbox_exporter
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/blackbox-exporter/blackbox.yml /etc/blackbox_exporter/config.yml
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/blackbox-exporter/LICENSE /licenses/blackbox-exporter/LICENSE
COPY --from=builder --chown=65532:65532 --chmod=0444 /src/blackbox-exporter/NOTICE /licenses/blackbox-exporter/NOTICE

USER nonroot
EXPOSE 9115
ENTRYPOINT ["/bin/blackbox_exporter"]
CMD ["--config.file=/etc/blackbox_exporter/config.yml"]
