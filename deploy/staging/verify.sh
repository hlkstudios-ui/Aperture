#!/usr/bin/env bash
set -euo pipefail
staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$root_dir/.env"
env_reader="$root_dir/deploy/production/hostinger/read_env.py"
[[ -f "$env_file" ]] || { echo "Run deploy/staging/generate-env.sh first." >&2; exit 1; }
[[ -f "$env_reader" ]] || { echo "Missing the literal dotenv reader." >&2; exit 1; }
command -v docker >/dev/null || { echo "Docker is required for staging verification." >&2; exit 1; }
docker info >/dev/null 2>&1 || { echo "The Docker engine is not running." >&2; exit 1; }
value() { python3 "$env_reader" --input "$env_file" --label "$1"; }
STAGING_API_HOST=$(value STAGING_API_HOST)
STAGING_HTTPS_PORT=$(value STAGING_HTTPS_PORT)
STAGING_API_ORIGIN=$(value STAGING_API_ORIGIN)
STAGING_WEB_HOST=$(value STAGING_WEB_HOST)
STAGING_WEB_ORIGIN=$(value STAGING_WEB_ORIGIN)
POSTGRES_USER=$(value POSTGRES_USER)
POSTGRES_PASSWORD=$(value POSTGRES_PASSWORD)
STAGING_POSTGRES_PORT=$(value STAGING_POSTGRES_PORT)
POSTGRES_DB=$(value POSTGRES_DB)
STAGING_MINIO_PORT=$(value STAGING_MINIO_PORT)
STAGING_STORAGE_ORIGIN=$(value STAGING_STORAGE_ORIGIN)
MINIO_ROOT_USER=$(value MINIO_ROOT_USER)
MINIO_ROOT_PASSWORD=$(value MINIO_ROOT_PASSWORD)
SESSION_SECRET=$(value SESSION_SECRET)
STAGING_MAILPIT_PORT=$(value STAGING_MAILPIT_PORT)
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
