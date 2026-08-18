#!/bin/sh
set -eu

BASE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
ROOT_DIR=$(CDPATH= cd -- "$BASE_DIR/../../.." && pwd)
ENV_FILE="$ROOT_DIR/.env"
COMPOSE_FILE="$BASE_DIR/compose.yml"
ACTION=${1:-}
METRICS_DIR=${APERTURE_METRICS_DIR:-/var/lib/aperture/metrics}

if docker compose version >/dev/null 2>&1; then
  set -- docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile operations
elif command -v docker-compose >/dev/null 2>&1; then
  set -- docker-compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" --profile operations
else
  echo "Docker Compose is unavailable" >&2
  exit 1
fi

case "$ACTION" in
  backup) "$@" run --rm backup; python3 "$BASE_DIR/record_operation.py" --directory "$METRICS_DIR" --operation backup ;;
  maintenance) "$@" run --rm maintenance; python3 "$BASE_DIR/record_operation.py" --directory "$METRICS_DIR" --operation maintenance ;;
  preflight) "$@" run --rm preflight; python3 "$BASE_DIR/record_operation.py" --directory "$METRICS_DIR" --operation preflight ;;
  restore)
    python3 "$BASE_DIR/validate_restore.py" --input "$ENV_FILE"
    "$@" run --rm restore
    python3 "$BASE_DIR/record_operation.py" --directory "$METRICS_DIR" --operation restore
    ;;
  replicate-media)
    python3 "$BASE_DIR/validate_replication.py" --input "$ENV_FILE"
    "$@" run --rm replicate-media
    python3 "$BASE_DIR/record_operation.py" --directory "$METRICS_DIR" --operation media_replication
    ;;
  *) echo "usage: operations.sh {backup|maintenance|preflight|restore|replicate-media}" >&2; exit 2 ;;
esac
