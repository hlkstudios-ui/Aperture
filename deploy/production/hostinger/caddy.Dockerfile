# syntax=docker/dockerfile:1.18

FROM golang:1.26.7-alpine3.24@sha256:28d89ee9cc0ff9fec75c82ca201e6bf7fdf9a679d4b7b24dfa04f2bb766bb468 AS builder

ENV CGO_ENABLED=0 \
    GOFLAGS=-buildvcs=false \
    GOTOOLCHAIN=local

WORKDIR /src
ADD --checksum=sha256:a593bd7077c76102ca76d19287a5e247d4e359dd67eddbc933f865afd3c131eb \
    https://github.com/caddyserver/caddy/archive/e2eee6a7fce366321294c9c2a79f3146891dcbdf.tar.gz \
    /tmp/caddy-source.tar.gz
RUN tar --extract --gzip --file=/tmp/caddy-source.tar.gz \
      --strip-components=1 --directory=/src \
    && rm /tmp/caddy-source.tar.gz \
    && go get \
      golang.org/x/crypto@v0.55.0 \
      golang.org/x/net@v0.57.0 \
      google.golang.org/grpc@v1.82.1 \
    && go mod tidy \
    && go mod verify \
    && test "$(sha256sum go.mod)" = "a092f0a81444e26ecdea87d58858b3511737929cbeed4ab4d675153a8d3db51d  go.mod" \
    && test "$(sha256sum go.sum)" = "5c04f692e2acc5bba059e6dfda5305d10acc087196c080ab2a006f364298cb24  go.sum" \
    && go build -trimpath \
      -ldflags="-s -w -buildid= -X github.com/caddyserver/caddy/v2.CustomVersion=v2.11.4" \
      -o /out/caddy ./cmd/caddy \
    && test "$(/out/caddy version)" = "v2.11.4"

RUN mkdir -p /runtime/data /runtime/config \
    && chown -R 65532:65532 /runtime/data /runtime/config

FROM gcr.io/distroless/static-debian13:nonroot@sha256:1c2c046bc09ed40fad370b599a0b1ae7987f55b01e247cf27a7c27cd97e5bbc7

LABEL org.opencontainers.image.title="Aperture Caddy edge" \
      org.opencontainers.image.source="https://github.com/caddyserver/caddy" \
      org.opencontainers.image.revision="e2eee6a7fce366321294c9c2a79f3146891dcbdf" \
      org.opencontainers.image.version="v2.11.4" \
      org.opencontainers.image.licenses="Apache-2.0"

ENV XDG_CONFIG_HOME=/config \
    XDG_DATA_HOME=/data

COPY --from=builder /out/caddy /usr/bin/caddy
COPY --from=builder /src/LICENSE /licenses/caddy/LICENSE
COPY --from=builder --chown=65532:65532 /runtime/data /data
COPY --from=builder --chown=65532:65532 /runtime/config /config

WORKDIR /srv
USER nonroot
EXPOSE 8080 8443 8443/udp

ENTRYPOINT ["/usr/bin/caddy"]
CMD ["run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
