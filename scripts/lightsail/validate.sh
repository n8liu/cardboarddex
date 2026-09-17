#!/usr/bin/env bash
set -euo pipefail
repo=$(cd "$(dirname "$0")/../.." && pwd)
cd "$repo"
for script in scripts/*.sh scripts/lightsail/*.sh; do bash -n "$script"; done
stage=$(mktemp -d)
trap 'rm -rf "$stage"' EXIT
cp deploy/lightsail/.env.example "$stage/app.env"
export APP_ENV_FILE="$stage/app.env" DATA_VOLUME=validation-only POSTGRES_PASSWORD=validation-only TUNNEL_TOKEN=validation-only
export BACKEND_IMAGE=example.invalid/backend@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export POSTGRES_IMAGE=example.invalid/postgres@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export REDIS_IMAGE=example.invalid/redis@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
export CLOUDFLARED_IMAGE=example.invalid/cloudflared@sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
docker compose --env-file "$stage/app.env" -f docker-compose.prod.yml config --quiet
# A missing production password must fail before any service is started.
if POSTGRES_PASSWORD='' docker compose --env-file "$stage/app.env" -f docker-compose.prod.yml config --quiet 2> "$stage/error"; then
  echo 'Compose accepted a missing database password' >&2
  exit 1
fi
grep -q POSTGRES_PASSWORD "$stage/error"
