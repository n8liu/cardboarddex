#!/usr/bin/env bash
# Invoked over SSH after a complete release has been uploaded.
set -euo pipefail
: "${1:?Release directory required}"
release=$(realpath "$1")
[[ "$release" == /opt/cardboarddex/releases/* ]] || { echo 'Invalid release path' >&2; exit 1; }
exec 9>/opt/cardboarddex/deploy.lock
flock -n 9 || { echo 'Another deployment is running' >&2; exit 1; }
export APP_ENV_FILE=/etc/cardboarddex/app.env
export BACKEND_IMAGE
BACKEND_IMAGE=$(cat "$release/image.txt")
[[ "$BACKEND_IMAGE" =~ @sha256:[a-f0-9]{64}$ ]] || { echo 'Require an immutable image digest' >&2; exit 1; }
compose=(docker compose -p app --env-file "$APP_ENV_FILE" -f "$release/docker-compose.prod.yml")
"${compose[@]}" config --quiet
mkdir -p /opt/cardboarddex/images
sudo -n bash "$release/scripts/lightsail/install_zram.sh"
old=$(readlink -f /opt/cardboarddex/current || true)
ingestion_paused=false
[[ ! -e /opt/cardboarddex/ingestion.paused ]] || ingestion_paused=true
# Roll back application configuration only: no schema changes run here.
rollback() {
  status=$?
  if (( status != 0 )) && [[ -n "$old" && -f "$old/image.txt" ]]; then
    echo 'Deployment failed; restoring previous release' >&2
    BACKEND_IMAGE=$(cat "$old/image.txt")
    export BACKEND_IMAGE
    restore_services=(postgres redis redis-cache backend cloudflared)
    if [[ "$ingestion_paused" == false ]]; then
      restore_services+=(celery-worker celery-beat)
    fi
    docker compose -p app --env-file "$APP_ENV_FILE" -f "$old/docker-compose.prod.yml" up -d --remove-orphans "${restore_services[@]}" || true
  fi
  exit "$status"
}
trap rollback EXIT
"${compose[@]}" stop celery-beat
"${compose[@]}" stop -t 3600 celery-worker
# Image downloads and the schema-check process need headroom on the 512 MB host.
# Keep the API serving while ingestion drains; restore it on any later failure.
COMPOSE_PARALLEL_LIMIT=1 "${compose[@]}" pull
[[ $(docker image inspect "$BACKEND_IMAGE" --format '{{.Architecture}}') == amd64 ]]
"${compose[@]}" run --rm --no-deps backend python -m jobs.check_revision
"${compose[@]}" up -d --wait --wait-timeout 180 postgres redis redis-cache backend
if [[ "$ingestion_paused" == false ]]; then
  "${compose[@]}" run --rm --no-deps --user 0 celery-beat chown -R 1001:1001 /beat
  "${compose[@]}" up -d celery-worker
  for attempt in {1..12}; do
    if "${compose[@]}" exec -T celery-worker celery -A app.celery_app inspect ping --timeout=5; then
      break
    fi
    (( attempt < 12 )) || exit 1
    sleep 5
  done
fi
curl -fsS --retry 5 --retry-delay 3 http://127.0.0.1:8000/ready
"${compose[@]}" up -d cloudflared
if [[ "$ingestion_paused" == false ]]; then
  "${compose[@]}" up -d celery-beat
  [[ $("${compose[@]}" ps --status running -q celery-beat | wc -l) -eq 1 ]]
else
  echo 'Ingestion remains paused by /opt/cardboarddex/ingestion.paused'
fi
actual=$(docker inspect --format '{{.Image}}' "$("${compose[@]}" ps -q backend)")
[[ "$actual" == "$(docker image inspect --format '{{.Id}}' "$BACKEND_IMAGE")" ]]
curl -fsS --retry 5 --retry-delay 3 https://api.cardboarddex.app/ready
curl -fsS --get --data-urlencode q=pikachu --data-urlencode limit=1 https://api.cardboarddex.app/cards/search > /dev/null
# Releases run as the SSH deployment user; system services require root.
# Keep failures visible rather than declaring success with backups disabled.
sudo -n systemctl enable --now cardboarddex-backup.timer
systemctl is-active --quiet cardboarddex-backup.timer
if [[ -n "$old" && "$old" != "$release" ]]; then
  ln -sfn "$old" /opt/cardboarddex/previous
fi
ln -sfn "$release" /opt/cardboarddex/current
trap - EXIT
echo 'Verified deployment completed'
