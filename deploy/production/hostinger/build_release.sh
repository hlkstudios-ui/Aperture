#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
BUILD_INPUT=${APERTURE_RELEASE_INPUT:-"$ROOT_DIR/.env"}
CREDENTIALS=${APERTURE_RELEASE_CREDENTIALS:-"$ROOT_DIR/.env"}

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
CAPTCHA_REQUIRED=$(value "$CREDENTIALS" CAPTCHA_REQUIRED)
TURNSTILE_SITE_KEY=

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
case "$CAPTCHA_REQUIRED" in
  true)
    TURNSTILE_SITE_KEY=$(value "$CREDENTIALS" NEXT_PUBLIC_TURNSTILE_SITE_KEY)
    case "$TURNSTILE_SITE_KEY" in
      ""|DUMMY_*) echo "replace NEXT_PUBLIC_TURNSTILE_SITE_KEY when CAPTCHA_REQUIRED=true" >&2; exit 1 ;;
    esac
    ;;
  false) ;;
  *) echo "CAPTCHA_REQUIRED must be true or false" >&2; exit 1 ;;
esac

SOURCE_COMMIT=$(python3 "$BASE_DIR/release_artifact_contract.py" source-preflight \
  --root "$ROOT_DIR")
docker buildx version >/dev/null
GIT_DIR=$(git -C "$ROOT_DIR" rev-parse --absolute-git-dir)
RELEASE_MANIFEST_DIR=${APERTURE_RELEASE_MANIFEST_DIR:-"$GIT_DIR/aperture-release-manifests"}

api_tag="$REGISTRY_REPOSITORY/api:$RELEASE_ID"
media_worker_tag="$REGISTRY_REPOSITORY/media-worker:$RELEASE_ID"
web_tag="$REGISTRY_REPOSITORY/web:$RELEASE_ID"
backup_tag="$REGISTRY_REPOSITORY/backup:$RELEASE_ID"
caddy_tag="$REGISTRY_REPOSITORY/caddy:$RELEASE_ID"
storage_tag="$REGISTRY_REPOSITORY/storage:$RELEASE_ID"
node_exporter_tag="$REGISTRY_REPOSITORY/node-exporter:$RELEASE_ID"
blackbox_tag="$REGISTRY_REPOSITORY/blackbox:$RELEASE_ID"

python3 "$BASE_DIR/release_artifact_contract.py" preflight \
  --repository "$REGISTRY_REPOSITORY" \
  --release-id "$RELEASE_ID" \
  --manifest-dir "$RELEASE_MANIFEST_DIR" \
  --tag "api=$api_tag" \
  --tag "media_worker=$media_worker_tag" \
  --tag "web=$web_tag" \
  --tag "backup=$backup_tag" \
  --tag "caddy=$caddy_tag" \
  --tag "storage=$storage_tag" \
  --tag "node_exporter=$node_exporter_tag" \
  --tag "blackbox=$blackbox_tag"

docker buildx build --platform "$RELEASE_PLATFORM" --provenance=mode=max --sbom=true --file "$ROOT_DIR/apps/api/Dockerfile" --tag "$api_tag" --push "$ROOT_DIR"
docker buildx build --platform "$RELEASE_PLATFORM" --provenance=mode=max --sbom=true --file "$ROOT_DIR/apps/api/Dockerfile.media-worker" --tag "$media_worker_tag" --push "$ROOT_DIR"
docker buildx build --platform "$RELEASE_PLATFORM" --provenance=mode=max --sbom=true --file "$ROOT_DIR/apps/web/Dockerfile" --tag "$web_tag" --push \
  --build-arg API_ORIGIN=http://api:8000 \
  --build-arg NEXT_PUBLIC_OBJECT_STORAGE_ORIGIN="https://$STORAGE_HOSTNAME" \
  --build-arg MEDIA_SOURCE_ORIGINS="https://$CDN_HOSTNAME" \
  --build-arg CAPTCHA_REQUIRED="$CAPTCHA_REQUIRED" \
  --build-arg NEXT_PUBLIC_TURNSTILE_SITE_KEY="$TURNSTILE_SITE_KEY" \
  --build-arg WEB_ORIGIN="https://$WEB_HOSTNAME" \
  --build-arg POLICY_REQUIRE_APPROVED=true "$ROOT_DIR"
docker buildx build --platform "$RELEASE_PLATFORM" --provenance=mode=max --sbom=true --file "$BASE_DIR/backup.Dockerfile" --tag "$backup_tag" --push "$ROOT_DIR"

publish_infrastructure() {
  component=$1
  target=$2
  dockerfile=$3
  source=$4
  if [ -n "$source" ]; then
    python3 "$BASE_DIR/release_artifact_contract.py" validate-reuse \
      --component "$component" \
      --repository "$REGISTRY_REPOSITORY" \
      --reference "$source" >/dev/null
    docker buildx imagetools create --tag "$target" "$source"
  else
    docker buildx build --platform "$RELEASE_PLATFORM" --provenance=mode=max --sbom=true \
      --file "$dockerfile" --tag "$target" --push "$ROOT_DIR"
  fi
}

publish_infrastructure caddy "$caddy_tag" "$BASE_DIR/caddy.Dockerfile" "${APERTURE_REUSE_CADDY_IMAGE:-}"
publish_infrastructure storage "$storage_tag" "$BASE_DIR/storage.Dockerfile" "${APERTURE_REUSE_STORAGE_IMAGE:-}"
publish_infrastructure node_exporter "$node_exporter_tag" "$BASE_DIR/node-exporter.Dockerfile" "${APERTURE_REUSE_NODE_EXPORTER_IMAGE:-}"
publish_infrastructure blackbox "$blackbox_tag" "$BASE_DIR/blackbox-exporter.Dockerfile" "${APERTURE_REUSE_BLACKBOX_IMAGE:-}"

digest() {
  docker buildx imagetools inspect "$1" --format '{{json .Manifest.Digest}}' | tr -d '"'
}

api_ref="$api_tag@$(digest "$api_tag")"
media_worker_ref="$media_worker_tag@$(digest "$media_worker_tag")"
web_ref="$web_tag@$(digest "$web_tag")"
backup_ref="$backup_tag@$(digest "$backup_tag")"
caddy_ref="$caddy_tag@$(digest "$caddy_tag")"
storage_ref="$storage_tag@$(digest "$storage_tag")"
node_exporter_ref="$node_exporter_tag@$(digest "$node_exporter_tag")"
blackbox_ref="$blackbox_tag@$(digest "$blackbox_tag")"

verify_reused_digest() {
  component=$1
  source=$2
  target=$3
  if [ -n "$source" ]; then
    expected=$(python3 "$BASE_DIR/release_artifact_contract.py" validate-reuse \
      --component "$component" \
      --repository "$REGISTRY_REPOSITORY" \
      --reference "$source")
    actual=${target##*@}
    if [ "$actual" != "$expected" ]; then
      echo "reused infrastructure digest changed while publishing $component" >&2
      exit 1
    fi
  fi
}

verify_reused_digest caddy "${APERTURE_REUSE_CADDY_IMAGE:-}" "$caddy_ref"
verify_reused_digest storage "${APERTURE_REUSE_STORAGE_IMAGE:-}" "$storage_ref"
verify_reused_digest node_exporter "${APERTURE_REUSE_NODE_EXPORTER_IMAGE:-}" "$node_exporter_ref"
verify_reused_digest blackbox "${APERTURE_REUSE_BLACKBOX_IMAGE:-}" "$blackbox_ref"

python3 "$BASE_DIR/release_artifact_contract.py" commit \
  --repository "$REGISTRY_REPOSITORY" \
  --release-id "$RELEASE_ID" \
  --platform "$RELEASE_PLATFORM" \
  --source-commit "$SOURCE_COMMIT" \
  --manifest-dir "$RELEASE_MANIFEST_DIR" \
  --reference "api=$api_ref" \
  --reference "media_worker=$media_worker_ref" \
  --reference "web=$web_ref" \
  --reference "backup=$backup_ref" \
  --reference "caddy=$caddy_ref" \
  --reference "storage=$storage_ref" \
  --reference "node_exporter=$node_exporter_ref" \
  --reference "blackbox=$blackbox_ref"

python3 "$BASE_DIR/pin_release.py" \
  --credentials "$CREDENTIALS" \
  --api "$api_ref" \
  --media-worker "$media_worker_ref" \
  --web "$web_ref" \
  --backup "$backup_ref" \
  --caddy "$caddy_ref" \
  --storage "$storage_ref" \
  --node-exporter "$node_exporter_ref" \
  --blackbox "$blackbox_ref"

echo "Release pushed, pinned, attested, and committed to a secret-free manifest."
