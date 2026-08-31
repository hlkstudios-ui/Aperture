#!/usr/bin/env bash
set -euo pipefail

# Startup script for the Aperture web frontend.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
env_file="$root_dir/.env"
next_cli="$root_dir/node_modules/next/dist/bin/next"

if [[ ! -f "$env_file" ]]; then
    echo "Error: root .env not found. Create it before starting Aperture." >&2
    exit 1
fi

if [[ ! -f "$next_cli" ]]; then
    echo "Error: Next.js is not installed. Run npm install from the repository root." >&2
    exit 1
fi

echo "Starting Aperture Web Frontend..."
echo "Frontend will be available at: http://localhost:3000"

# next.config.ts loads the root dotenv file. Passing Node's --env-file here would
# be propagated through NODE_OPTIONS to Next's child process, which Node rejects.
cd "$root_dir/apps/web"
exec node "$next_cli" dev --hostname 0.0.0.0 --port 3000
