#!/usr/bin/env bash
set -euo pipefail

readonly CONTAINER_NAME="aperture-hostinger-policy-test"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly NETWORK_NAME="${HOSTINGER_TEST_NETWORK:-aperture-staging_private}"
readonly TEST_PORT="${HOSTINGER_TEST_PORT:-18443}"
readonly TEST_HOST="hostinger-policy.localhost"
readonly STORAGE_TEST_HOST="hostinger-storage.localhost"
readonly ORIGIN_SECRET="runtime-origin-secret"
readonly STUDIO_SECRET="runtime-studio-secret"
readonly CDN_SECRET="runtime-cdn-origin-secret"
readonly BASE_URL="https://${TEST_HOST}:${TEST_PORT}"
readonly STORAGE_BASE_URL="https://${STORAGE_TEST_HOST}:${TEST_PORT}"
readonly CADDY_TEST_IMAGE="${HOSTINGER_CADDY_TEST_IMAGE:-aperture-hostinger-caddy-policy:local}"

cleanup() {
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "Hostinger ingress check requires the running staging network: ${NETWORK_NAME}" >&2
  exit 1
fi

docker build \
  --file "${PROJECT_ROOT}/deploy/production/hostinger/caddy.Dockerfile" \
  --tag "${CADDY_TEST_IMAGE}" \
  "${PROJECT_ROOT}" >/dev/null

docker run --rm -d \
  --name "${CONTAINER_NAME}" \
  --network "${NETWORK_NAME}" \
  --publish "127.0.0.1:${TEST_PORT}:8443" \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges \
  --tmpfs /tmp:size=16m,mode=0700,uid=65532,gid=65532 \
  --tmpfs /data:size=16m,mode=0700,uid=65532,gid=65532 \
  --tmpfs /config:size=16m,mode=0700,uid=65532,gid=65532 \
  --volume "${PROJECT_ROOT}/deploy/production/hostinger/Caddyfile:/etc/caddy/Caddyfile:ro" \
  --env WEB_HOSTNAME="${TEST_HOST}" \
  --env ORIGIN_HOSTNAME="hostinger-origin.localhost" \
  --env STORAGE_HOSTNAME="${STORAGE_TEST_HOST}" \
  --env ACME_EMAIL="owner@example.test" \
  --env ORIGIN_EDGE_SECRET="${ORIGIN_SECRET}" \
  --env STUDIO_EDGE_SECRET="${STUDIO_SECRET}" \
  --env CDN_ORIGIN_SECRET="${CDN_SECRET}" \
  "${CADDY_TEST_IMAGE}" >/dev/null

ready=false
for _attempt in {1..50}; do
  if curl --insecure --silent \
    --resolve "${TEST_HOST}:${TEST_PORT}:127.0.0.1" \
    --output /dev/null "${BASE_URL}/"; then
    ready=true
    break
  fi
  sleep 0.1
done
if [[ "${ready}" != "true" ]]; then
  echo "Hostinger policy Caddy did not become ready" >&2
  exit 1
fi

status() {
  local path="$1"
  shift
  curl --insecure --silent --show-error \
    --resolve "${TEST_HOST}:${TEST_PORT}:127.0.0.1" \
    --output /dev/null --write-out '%{http_code}' \
    "$@" "${BASE_URL}${path}"
}

storage_status() {
  local path="$1"
  shift
  curl --insecure --silent --show-error \
    --resolve "${STORAGE_TEST_HOST}:${TEST_PORT}:127.0.0.1" \
    --output /dev/null --write-out '%{http_code}' \
    "$@" "${STORAGE_BASE_URL}${path}"
}

expect() {
  local expected="$1"
  local actual="$2"
  local label="$3"
  if [[ "${actual}" != "${expected}" ]]; then
    echo "${label}: expected ${expected}, received ${actual}" >&2
    exit 1
  fi
}

expect 404 "$(status /)" "direct origin denial"
expect 200 "$(status / -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "trusted homepage"
expect 404 "$(status /studio/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "public Studio denial"
expect 200 "$(status /studio/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}" -H "X-Aperture-Studio-Edge: ${STUDIO_SECRET}")" "private Studio admission"
expect 200 "$(status /api/ready -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "trusted API readiness"
expect 404 "$(status /api/account -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "direct API catch-all denial"
expect 404 "$(status /api/admin/auth/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "public admin denial"
expect 404 "$(status /api/admin/auth/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}" -H "X-Aperture-Studio-Edge: ${STUDIO_SECRET}")" "legacy private admin denial"
expect 404 "$(status /api/edge-media/not-a-uuid/1/not-a-uuid/GLOBAL/bad/file.m3u8 -H "X-Aperture-Origin-Secret: wrong")" "media origin secret denial"

media_origin_status="$(status /api/edge-media/not-a-uuid/1/not-a-uuid/GLOBAL/bad/file.m3u8 -H "X-Aperture-Origin-Secret: ${CDN_SECRET}")"
if [[ "${media_origin_status}" == "404" ]]; then
  echo "protected media request did not pass Caddy admission" >&2
  exit 1
fi

private_admin_status="$(status /api/gateway/admin/auth/me -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}" -H "X-Aperture-Studio-Edge: ${STUDIO_SECRET}")"
if [[ "${private_admin_status}" == "404" ]]; then
  echo "private gateway admin request did not pass Caddy admission" >&2
  exit 1
fi

expect 200 "$(storage_status /minio/health/ready)" "ordinary storage readiness"
expect 403 "$(storage_status /bucket/object -X PUT -H 'X-Amz-Content-Sha256: STREAMING-UNSIGNED-PAYLOAD-TRAILER')" "unsigned trailer denial"
expect 403 "$(storage_status /bucket/object -X PUT -H 'X-Amz-Meta-Snowball-Auto-Extract: true')" "Snowball extract denial"
expect 403 "$(storage_status '/bucket/object?select&select-type=2' -X POST)" "S3 Select denial"
expect 403 "$(storage_status /bucket/object -X PUT -H 'X-Minio-Replication-Server-Side-Encryption-Sealed-Key: forged')" "replication sealed-key denial"
expect 403 "$(storage_status /bucket/object -X PUT -H 'X-Minio-Replication-Server-Side-Encryption-Seal-Algorithm: forged')" "replication seal-algorithm denial"
expect 403 "$(storage_status /bucket/object -X PUT -H 'X-Minio-Replication-Server-Side-Encryption-Iv: forged')" "replication IV denial"
expect 404 "$(storage_status /minio/storage/drive/v63/rmpl -X POST)" "storage REST denial"

echo "Hostinger ingress runtime policy passed."
