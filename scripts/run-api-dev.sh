#!/usr/bin/env bash
set -euo pipefail

# Startup script for the Aperture backend API.
script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
root_dir=$(CDPATH= cd -- "$script_dir/.." && pwd)
api_dir="$root_dir/apps/api"
env_file="$root_dir/.env"
env_reader="$root_dir/deploy/production/hostinger/read_env.py"

if [[ ! -f "$env_file" ]]; then
    echo "Error: root .env not found. Create it before starting Aperture." >&2
    exit 1
fi

if [[ -x "$api_dir/venv/Scripts/python.exe" ]]; then
    python_bin="$api_dir/venv/Scripts/python.exe"
elif [[ -x "$api_dir/venv/bin/python" ]]; then
    python_bin="$api_dir/venv/bin/python"
else
    echo "Error: API virtual-environment Python was not found." >&2
    exit 1
fi

# Process environment wins; otherwise read the literal dotenv value without sourcing it.
if [[ -n "${API_PORT:-}" ]]; then
    api_port="$API_PORT"
elif grep -Eq '^[[:space:]]*API_PORT=' "$env_file"; then
    api_port=$("$python_bin" "$env_reader" --input "$env_file" --label API_PORT)
else
    api_port=8001
fi

if [[ ! "$api_port" =~ ^[0-9]+$ ]] || (( api_port < 1 || api_port > 65535 )); then
    echo "Error: API_PORT must be an integer between 1 and 65535." >&2
    exit 1
fi

echo "Starting Aperture API Server..."
echo "API will be available at: http://localhost:$api_port"
echo "API Docs will be available at: http://localhost:$api_port/docs"

cd "$api_dir"
exec "$python_bin" -m uvicorn app.main:app --reload --host 0.0.0.0 --port "$api_port"
