#!/usr/bin/env bash
# Stored-data maintenance only; never starts Celery or provider ingestion.
set -euo pipefail
exec 9>/opt/cardboarddex/deploy.lock
flock -sn 9 || exit 0
release=$(readlink -f /opt/cardboarddex/current)
[[ "$release" == /opt/cardboarddex/releases/* ]]
export APP_ENV_FILE=/etc/cardboarddex/app.env
export BACKEND_IMAGE
BACKEND_IMAGE=$(cat "$release/image.txt")
[[ "$BACKEND_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]]
container=cardboarddex-live-stats-refresh
cleanup() { docker rm -f "$container" >/dev/null 2>&1 || true; }
trap cleanup EXIT
trap 'exit 143' TERM
trap 'exit 130' INT
# Use the worker service's independent memory budget, not docker exec in the API.
docker compose -p app --env-file "$APP_ENV_FILE" -f "$release/docker-compose.prod.yml" \
  run --rm --no-deps -T --name "$container" celery-worker \
  python -c 'import logging; logging.basicConfig(level=logging.INFO)
from app.services import live_stats, trending_service
# Refresh both even if one fails; report either failure.
results = [live_stats.refresh_snapshot(), trending_service.refresh_snapshot()]
raise SystemExit(0 if all(results) else 1)' </dev/null
