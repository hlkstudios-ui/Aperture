#!/usr/bin/env bash
set -euo pipefail
umask 077
root_dir=$(cd "$(dirname "$0")/../.." && pwd)
target="$root_dir/deploy/staging/.env.staging"
if [[ -e "$target" ]]; then
  echo "Refusing to overwrite $target" >&2
  exit 1
fi
secret() { openssl rand -hex 32; }
cat >"$target" <<EOF
STAGING_HTTPS_PORT=8443
STAGING_POSTGRES_PORT=55432
STAGING_MINIO_PORT=59000
STAGING_MAILPIT_PORT=58025
STAGING_WEB_HOST=staging.127.0.0.1.nip.io
STAGING_API_HOST=api.staging.127.0.0.1.nip.io
STAGING_STORAGE_HOST=storage.staging.127.0.0.1.nip.io
STAGING_WEB_ORIGIN=https://staging.127.0.0.1.nip.io:8443
STAGING_API_ORIGIN=https://api.staging.127.0.0.1.nip.io:8443
STAGING_STORAGE_ORIGIN=https://storage.staging.127.0.0.1.nip.io:8443
STAGING_COOKIE_DOMAIN=staging.127.0.0.1.nip.io
POSTGRES_DB=aperture_staging
POSTGRES_USER=aperture_staging
POSTGRES_PASSWORD=$(secret)
MINIO_ROOT_USER=aperture_staging
MINIO_ROOT_PASSWORD=$(secret)
S3_BUCKET=aperture-staging-media
SESSION_SECRET=$(secret)
SMTP_USERNAME=aperture-staging
SMTP_PASSWORD=$(secret)
SMTP_FROM_EMAIL=no-reply@staging.127.0.0.1.nip.io
ERROR_TRACKING_DSN=
METRICS_BEARER_TOKEN=$(secret)
EOF
chmod 600 "$target"
echo "Created $target with isolated random staging credentials."
echo "Keep it outside version control and replace local domains/DSN for shared staging."
