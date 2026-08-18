#!/usr/bin/env bash
set -euo pipefail

readonly CONTAINER_NAME="aperture-hostinger-policy-test"
readonly SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../../.." && pwd)"
readonly NETWORK_NAME="${HOSTINGER_TEST_NETWORK:-aperture-staging_private}"
readonly TEST_PORT="${HOSTINGER_TEST_PORT:-18443}"
readonly TEST_HOST="hostinger-policy.localhost"
readonly ORIGIN_SECRET="runtime-origin-secret"
readonly STUDIO_SECRET="runtime-studio-secret"
readonly BASE_URL="https://${TEST_HOST}:${TEST_PORT}"

cleanup() {
  docker stop "${CONTAINER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

if ! docker network inspect "${NETWORK_NAME}" >/dev/null 2>&1; then
  echo "Hostinger ingress check requires the running staging network: ${NETWORK_NAME}" >&2
  exit 1
fi

docker run --rm -d \
  --name "${CONTAINER_NAME}" \
  --network "${NETWORK_NAME}" \
  --publish "127.0.0.1:${TEST_PORT}:8443" \
  --tmpfs /data:size=16m,mode=0700 \
  --volume "${PROJECT_ROOT}/deploy/production/hostinger/Caddyfile:/etc/caddy/Caddyfile:ro" \
  --env WEB_HOSTNAME="${TEST_HOST}" \
  --env ORIGIN_HOSTNAME="hostinger-origin.localhost" \
  --env STORAGE_HOSTNAME="hostinger-storage.localhost" \
  --env ACME_EMAIL="owner@example.test" \
  --env ORIGIN_EDGE_SECRET="${ORIGIN_SECRET}" \
  --env STUDIO_EDGE_SECRET="${STUDIO_SECRET}" \
  caddy:2.10.2-alpine >/dev/null

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
expect 404 "$(status /api/admin/auth/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}")" "public admin denial"

private_admin_status="$(status /api/admin/auth/login -H "X-Aperture-Origin-Secret: ${ORIGIN_SECRET}" -H "X-Aperture-Studio-Edge: ${STUDIO_SECRET}")"
if [[ "${private_admin_status}" == "404" ]]; then
  echo "private admin request did not pass Caddy admission" >&2
  exit 1
fi

echo "Hostinger ingress runtime policy passed."
