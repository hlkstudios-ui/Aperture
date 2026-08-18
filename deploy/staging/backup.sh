#!/usr/bin/env bash
set -euo pipefail

staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$staging_dir/.env.staging"
destination=${1:-}
[[ -f "$env_file" ]] || { echo "Missing isolated staging environment." >&2; exit 1; }
[[ -n "$destination" && "$destination" = /* ]] || { echo "Pass an absolute backup destination." >&2; exit 1; }
case "$destination" in /|"$HOME"|"$root_dir") echo "Refusing a broad backup destination." >&2; exit 1;; esac

set -a
source "$env_file"
set +a
mkdir -p "$destination"
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$staging_dir/compose.yml")
else
  compose=(docker-compose --env-file "$env_file" -f "$staging_dir/compose.yml")
fi
stamp=$(date -u +%Y%m%dT%H%M%SZ)
dump="$destination/postgres-$stamp.dump"
config="$destination/config-$stamp.tar.gz"

"${compose[@]}" exec -T postgres pg_dump \
  --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  --format=custom --no-owner --no-privileges >"$dump"
tar -czf "$config" -C "$root_dir" \
  deploy/staging/compose.yml deploy/staging/Caddyfile \
  deploy/staging/.env.staging.example deploy/staging/generate-env.sh \
  deploy/staging/verify.sh deploy/staging/README.md
shasum -a 256 "$dump" "$config" >"$destination/SHA256SUMS-$stamp"
echo "Created database and non-secret configuration backups in $destination"
