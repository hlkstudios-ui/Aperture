#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
BUILD_INPUT="$ROOT_DIR/.env"
CREDENTIALS="$ROOT_DIR/.env"

value() {
  python3 "$BASE_DIR/read_env.py" --input "$1" --label "$2"
}
REGISTRY_REPOSITORY=$(value "$BUILD_INPUT" REGISTRY_REPOSITORY)
RELEASE_ID=$(value "$BUILD_INPUT" RELEASE_ID)
RELEASE_PLATFORM=$(value "$BUILD_INPUT" RELEASE_PLATFORM)
WEB_HOSTNAME=$(value "$CREDENTIALS" WEB_HOSTNAME)
STORAGE_HOSTNAME=$(value "$CREDENTIALS" STORAGE_HOSTNAME)
CDN_HOSTNAME=$(value "$CREDENTIALS" CDN_HOSTNAME)
POLICY_REQUIRE_APPROVED=$(value "$CREDENTIALS" POLICY_REQUIRE_APPROVED)

case "$REGISTRY_REPOSITORY" in
  DUMMY_*|dummy.*|*[!a-z0-9./_-]*) echo "replace REGISTRY_REPOSITORY with a lowercase registry path" >&2; exit 1 ;;
esac
case "$RELEASE_ID" in
  DUMMY_*|dummy_*|*latest*|*[!a-z0-9._-]*) echo "RELEASE_ID must be immutable and non-dummy" >&2; exit 1 ;;
esac
if [ "$RELEASE_PLATFORM" != "linux/amd64" ]; then
  echo "Hostinger production release platform must be linux/amd64" >&2
  exit 1
fi
for value in "$WEB_HOSTNAME" "$STORAGE_HOSTNAME" "$CDN_HOSTNAME"; do
  case "$value" in DUMMY_*|dummy.*) echo "replace public hostnames before release build" >&2; exit 1 ;; esac
done
if [ "$POLICY_REQUIRE_APPROVED" != "true" ]; then
  echo "POLICY_REQUIRE_APPROVED must be true before a production web build" >&2
  exit 1
fi
docker buildx version >/dev/null

api_tag="$REGISTRY_REPOSITORY/api:$RELEASE_ID"
web_tag="$REGISTRY_REPOSITORY/web:$RELEASE_ID"
backup_tag="$REGISTRY_REPOSITORY/backup:$RELEASE_ID"

docker buildx build --platform "$RELEASE_PLATFORM" --file "$ROOT_DIR/apps/api/Dockerfile" --tag "$api_tag" --push "$ROOT_DIR"
docker buildx build --platform "$RELEASE_PLATFORM" --file "$ROOT_DIR/apps/web/Dockerfile" --tag "$web_tag" --push \
  --build-arg API_ORIGIN=http://api:8000 \
  --build-arg NEXT_PUBLIC_API_ORIGIN="https://$WEB_HOSTNAME/api" \
  --build-arg NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN="https://$STORAGE_HOSTNAME" \
  --build-arg NEXT_PUBLIC_MEDIA_ORIGIN="https://$CDN_HOSTNAME" \
  --build-arg WEB_ORIGIN="https://$WEB_HOSTNAME" \
  --build-arg POLICY_REQUIRE_APPROVED=true "$ROOT_DIR"
docker buildx build --platform "$RELEASE_PLATFORM" --file "$BASE_DIR/backup.Dockerfile" --tag "$backup_tag" --push "$ROOT_DIR"

digest() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest.Digest}}' | tr -d '"'
}

python3 "$BASE_DIR/pin_release.py" \
  --credentials "$CREDENTIALS" \
  --api "$api_tag@$(digest "$api_tag")" \
  --web "$web_tag@$(digest "$web_tag")" \
  --backup "$backup_tag@$(digest "$backup_tag")"

echo "Release pushed and credentials pinned to immutable digests."
