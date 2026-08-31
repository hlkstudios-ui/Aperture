#!/usr/bin/env bash
set -euo pipefail
umask 077
root_dir=$(cd "$(dirname "$0")/../.." && pwd)
template="$root_dir/.env.example"
target="$root_dir/.env"
if [[ -e "$target" ]]; then
  echo "Refusing to overwrite $target" >&2
  exit 1
fi
[[ -f "$template" ]] || { echo "Missing $template" >&2; exit 1; }
command -v python3 >/dev/null || { echo "Python 3 is required to generate .env." >&2; exit 1; }

python3 - "$template" "$target" <<'PY'
from __future__ import annotations

import re
import secrets
import sys
from pathlib import Path
from urllib.parse import quote

template = Path(sys.argv[1])
target = Path(sys.argv[2])
lines = template.read_text(encoding="utf-8").splitlines()
label_pattern = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")
positions: dict[str, int] = {}
values: dict[str, str] = {}

for number, line in enumerate(lines, 1):
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        continue
    match = label_pattern.match(line)
    if match is None:
        raise SystemExit(f"invalid dotenv syntax at template line {number}")
    label, value = match.groups()
    if label in positions:
        raise SystemExit(f"duplicate dotenv label in template: {label}")
    positions[label] = number - 1
    values[label] = value

required = {
    "APERTURE_POSTGRES_PORT",
    "POSTGRES_DB",
    "POSTGRES_USER",
    "POSTGRES_PASSWORD",
    "DATABASE_URL",
    "REDIS_PASSWORD",
    "S3_ACCESS_KEY",
    "S3_SECRET_KEY",
    "MINIO_ROOT_USER",
    "MINIO_ROOT_PASSWORD",
    "SESSION_SECRET",
    "SMTP_HOST",
    "SMTP_PORT",
    "SMTP_USERNAME",
    "SMTP_PASSWORD",
    "SMTP_FROM_EMAIL",
    "SMTP_STARTTLS",
    "METRICS_BEARER_TOKEN",
    "CDN_SIGNING_SECRET",
    "CDN_ORIGIN_SECRET",
    "GEO_ASSERTION_SECRET",
    "ORIGIN_EDGE_SECRET",
    "STUDIO_EDGE_SECRET",
}
missing = sorted(required - positions.keys())
if missing:
    raise SystemExit("missing required dotenv labels: " + ", ".join(missing))

postgres_password = secrets.token_hex(32)
storage_password = secrets.token_hex(32)
storage_user = values["S3_ACCESS_KEY"]
replacements = {
    "POSTGRES_PASSWORD": postgres_password,
    "DATABASE_URL": (
        "postgresql+psycopg://"
        f"{quote(values['POSTGRES_USER'], safe='')}:"
        f"{quote(postgres_password, safe='')}@127.0.0.1:{values['APERTURE_POSTGRES_PORT']}/"
        f"{quote(values['POSTGRES_DB'], safe='')}"
    ),
    "REDIS_PASSWORD": secrets.token_hex(32),
    "MINIO_ROOT_USER": storage_user,
    "MINIO_ROOT_PASSWORD": storage_password,
    "S3_SECRET_KEY": storage_password,
    "SESSION_SECRET": secrets.token_hex(32),
    "SMTP_HOST": "localhost",
    "SMTP_PORT": "1025",
    "SMTP_USERNAME": "aperture-local",
    "SMTP_PASSWORD": secrets.token_hex(32),
    "SMTP_FROM_EMAIL": "no-reply@localhost",
    "SMTP_STARTTLS": "false",
    "METRICS_BEARER_TOKEN": secrets.token_hex(32),
    "CDN_SIGNING_SECRET": secrets.token_hex(32),
    "CDN_ORIGIN_SECRET": secrets.token_hex(32),
    "GEO_ASSERTION_SECRET": secrets.token_hex(32),
    "ORIGIN_EDGE_SECRET": secrets.token_hex(32),
    "STUDIO_EDGE_SECRET": secrets.token_hex(32),
}

for label, value in replacements.items():
    lines[positions[label]] = f"{label}={value}"

with target.open("x", encoding="utf-8", newline="\n") as output:
    output.write("\n".join(lines) + "\n")
PY
chmod 600 "$target"
echo "Created the single root .env with fresh local secrets."
echo "Keep it outside version control; staging and local development now share this file."
