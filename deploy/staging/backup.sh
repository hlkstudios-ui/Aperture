#!/usr/bin/env bash
set -euo pipefail

staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$root_dir/.env"
env_reader="$root_dir/deploy/production/hostinger/read_env.py"
destination=${1:-}
[[ -f "$env_file" ]] || { echo "Missing root .env; run deploy/staging/generate-env.sh first." >&2; exit 1; }
[[ -f "$env_reader" ]] || { echo "Missing the literal dotenv reader." >&2; exit 1; }
[[ -n "$destination" && "$destination" = /* ]] || { echo "Pass an absolute backup destination." >&2; exit 1; }
case "$destination" in /|"$HOME"|"$root_dir") echo "Refusing a broad backup destination." >&2; exit 1;; esac

value() { python3 "$env_reader" --input "$env_file" --label "$1"; }
POSTGRES_USER=$(value POSTGRES_USER)
POSTGRES_DB=$(value POSTGRES_DB)
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
  .env.example deploy/staging/generate-env.sh \
  deploy/staging/verify.sh deploy/staging/README.md
shasum -a 256 "$dump" "$config" >"$destination/SHA256SUMS-$stamp"
echo "Created database and non-secret configuration backups in $destination"
