#!/usr/bin/env bash
# Recover a snapshotted release without allowing stale app.env image selection.
set -euo pipefail
release=${1:-/opt/cardboarddex/current}
traffic=${2:-}
[[ -z "$traffic" || "$traffic" == --traffic ]] || { echo 'Use --traffic to reconnect the Tunnel' >&2; exit 1; }
: "${APP_ENV_FILE:=/etc/cardboarddex/app.env}"
BACKEND_IMAGE=$(cat "$release/image.txt")
[[ "$BACKEND_IMAGE" =~ ^349558247779\.(dkr\.ecr\.us-west-2\.amazonaws\.com|dkr-ecr\.us-west-2\.on\.aws)/cardboarddex-backend@sha256:[a-f0-9]{64}$ ]] || { echo 'Invalid release digest' >&2; exit 1; }
export BACKEND_IMAGE
docker image inspect "$BACKEND_IMAGE" > /dev/null
compose=(docker compose -p app --env-file "$APP_ENV_FILE" -f "$release/docker-compose.prod.yml")
"${compose[@]}" up -d --pull never --wait --wait-timeout 120 postgres redis redis-cache backend
backend=$("${compose[@]}" ps -q backend)
actual=$(docker inspect "$backend" --format '{{.Config.Image}}')
[[ "$actual" == "$BACKEND_IMAGE" ]] || { echo 'Running backend differs from release digest' >&2; exit 1; }
curl --fail --silent --show-error --max-time 10 http://127.0.0.1:8000/ready
if [[ "$traffic" == --traffic ]]; then
  "${compose[@]}" up -d --no-deps --pull never cloudflared
fi
