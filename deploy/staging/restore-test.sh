#!/usr/bin/env bash
set -euo pipefail

staging_dir=$(cd "$(dirname "$0")" && pwd)
root_dir=$(cd "$staging_dir/../.." && pwd)
env_file="$root_dir/.env"
env_reader="$root_dir/deploy/production/hostinger/read_env.py"
[[ -f "$env_file" ]] || { echo "Missing root .env; run deploy/staging/generate-env.sh first." >&2; exit 1; }
[[ -f "$env_reader" ]] || { echo "Missing the literal dotenv reader." >&2; exit 1; }
value() { python3 "$env_reader" --input "$env_file" --label "$1"; }
POSTGRES_USER=$(value POSTGRES_USER)
POSTGRES_DB=$(value POSTGRES_DB)
if docker compose version >/dev/null 2>&1; then
  compose=(docker compose --env-file "$env_file" -f "$staging_dir/compose.yml")
else
  compose=(docker-compose --env-file "$env_file" -f "$staging_dir/compose.yml")
fi

restore_dir=$(mktemp -d /tmp/aperture-restore-test.XXXXXX)
database="aperture_restore_test_$(openssl rand -hex 6)"
cleanup() {
  [[ "$database" =~ ^aperture_restore_test_[0-9a-f]{12}$ ]] && \
    "${compose[@]}" exec -T postgres dropdb --if-exists --force --username "$POSTGRES_USER" "$database" >/dev/null
  [[ "$restore_dir" == /tmp/aperture-restore-test.* ]] && rm -rf -- "$restore_dir"
}
trap cleanup EXIT

"$staging_dir/backup.sh" "$restore_dir"
dump=$(find "$restore_dir" -type f -name 'postgres-*.dump' -print -quit)
"${compose[@]}" exec -T postgres createdb --username "$POSTGRES_USER" "$database"
"${compose[@]}" exec -T postgres pg_restore \
  --username "$POSTGRES_USER" --dbname "$database" --no-owner --no-privileges <"$dump"

source_head=$("${compose[@]}" exec -T postgres psql -At --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c 'SELECT version_num FROM alembic_version')
restored_head=$("${compose[@]}" exec -T postgres psql -At --username "$POSTGRES_USER" --dbname "$database" -c 'SELECT version_num FROM alembic_version')
[[ "$source_head" == "$restored_head" ]] || { echo "Restored migration head differs." >&2; exit 1; }
source_tables=$("${compose[@]}" exec -T postgres psql -At --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
restored_tables=$("${compose[@]}" exec -T postgres psql -At --username "$POSTGRES_USER" --dbname "$database" -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'")
[[ "$source_tables" == "$restored_tables" ]] || { echo "Restored table count differs." >&2; exit 1; }
echo "Isolated restore test passed at migration $restored_head with $restored_tables public tables."
