#!/usr/bin/env bash
set -euo pipefail
staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$staging_dir/.env.staging"
[[ -f "$env_file" ]] || { echo "Run deploy/staging/generate-env.sh first." >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required for staging verification." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "The Docker engine is not running." >&2; exit 1; }
set -a
source "$env_file"
set +a
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$staging_dir/compose.yml")
else
  compose=(docker-compose --env-file "$env_file" -f "$staging_dir/compose.yml")
fi
"${compose[@]}" config --quiet
"${compose[@]}" build
"${compose[@]}" up -d

ca_file=$(mktemp)
trap 'rm -f "$ca_file"' EXIT
for _ in $(seq 1 60); do
  if "${compose[@]}" cp caddy:/data/caddy/pki/authorities/local/root.crt "$ca_file" >/dev/null 2>&1; then
    if curl --silent --fail --cacert "$ca_file" \
      --resolve "$STAGING_API_HOST:$STAGING_HTTPS_PORT:127.0.0.1" \
      "$STAGING_API_ORIGIN/ready" >/dev/null; then break; fi
  fi
  sleep 2
done
curl --fail --show-error --cacert "$ca_file" \
  --resolve "$STAGING_WEB_HOST:$STAGING_HTTPS_PORT:127.0.0.1" "$STAGING_WEB_ORIGIN/" >/dev/null
curl --fail --show-error --cacert "$ca_file" \
  --resolve "$STAGING_API_HOST:$STAGING_HTTPS_PORT:127.0.0.1" "$STAGING_API_ORIGIN/ready"
"${compose[@]}" exec -T redis redis-cli FLUSHDB >/dev/null

export APP_ENV=test
export DATABASE_URL="postgresql+psycopg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$STAGING_POSTGRES_PORT/$POSTGRES_DB"
export REDIS_URL=redis://127.0.0.1:6379/15
export S3_ENDPOINT="http://127.0.0.1:$STAGING_MINIO_PORT"
export S3_PUBLIC_ENDPOINT="$STAGING_STORAGE_ORIGIN"
export S3_ACCESS_KEY="$MINIO_ROOT_USER"
export S3_SECRET_KEY="$MINIO_ROOT_PASSWORD"
export SESSION_SECRET
export E2E_BASE_URL="$STAGING_WEB_ORIGIN"
export E2E_API_ORIGIN="$STAGING_API_ORIGIN"
export E2E_MAILPIT_ORIGIN="http://127.0.0.1:${STAGING_MAILPIT_PORT:-58025}"
cd "$root_dir/apps/api"
../../.venv/bin/python scripts/seed_catalog.py
cd "$root_dir"
npx playwright test --project=desktop-chromium --project=mobile-chromium \
  --grep-invert "development password-reset"
echo "Staging HTTPS, migrations, isolated seed, smoke, and E2E verification passed."
