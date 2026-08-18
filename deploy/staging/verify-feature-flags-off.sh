#!/usr/bin/env bash
set -euo pipefail

staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$staging_dir/.env.staging"
[[ -f "$env_file" ]] || { echo "Run deploy/staging/generate-env.sh first." >&2; exit 1; }

set -a
source "$env_file"
set +a
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$staging_dir/compose.yml")
else
  compose=(docker-compose --env-file "$env_file" -f "$staging_dir/compose.yml")
fi

restore_enabled_stack() {
  local test_status=$?
  unset FEATURE_SCENE_LENS_ENABLED FEATURE_ASK_MOVIE_ENABLED FEATURE_COMMUNITY_ENABLED
  unset FEATURE_WATCH_PARTIES_ENABLED FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED
  set +e
  "${compose[@]}" build web >/dev/null
  "${compose[@]}" up -d api media-worker scene-worker web >/dev/null
  local restore_status=$?
  set -e
  if (( restore_status != 0 )); then
    echo "WARNING: failed to restore the enabled staging stack." >&2
    exit "$restore_status"
  fi
  exit "$test_status"
}
trap restore_enabled_stack EXIT

export FEATURE_SCENE_LENS_ENABLED=false
export FEATURE_ASK_MOVIE_ENABLED=false
export FEATURE_COMMUNITY_ENABLED=false
export FEATURE_WATCH_PARTIES_ENABLED=false
export FEATURE_EXPERIMENTAL_RECOMMENDATIONS_ENABLED=false

"${compose[@]}" build web api
"${compose[@]}" up -d api media-worker scene-worker web

export E2E_FLAGS_OFF=1
export E2E_BASE_URL="$STAGING_WEB_ORIGIN"
export E2E_API_ORIGIN="$STAGING_API_ORIGIN"
cd "$root_dir"
npx playwright test tests/e2e/feature-flags-off.spec.ts \
  --project=desktop-chromium --project=mobile-chromium
echo "All-risky-features-off desktop/mobile browser acceptance passed."
