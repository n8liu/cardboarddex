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
"${compose[@]}" pull
[[ $(docker image inspect "$BACKEND_IMAGE" --format '{{.Architecture}}') == amd64 ]]
"${compose[@]}" run --rm --no-deps backend python -m jobs.check_revision
old=$(readlink -f /opt/cardboarddex/current || true)
# Roll back application configuration only: no schema changes run here.
rollback() {
  status=$?
  if (( status != 0 )) && [[ -n "$old" && -f "$old/image.txt" ]]; then
    echo 'Deployment failed; restoring previous release' >&2
    BACKEND_IMAGE=$(cat "$old/image.txt")
    export BACKEND_IMAGE
    docker compose -p app --env-file "$APP_ENV_FILE" -f "$old/docker-compose.prod.yml" up -d --remove-orphans || true
  fi
  exit "$status"
}
trap rollback EXIT
"${compose[@]}" stop celery-beat
"${compose[@]}" stop -t 3600 celery-worker
"${compose[@]}" up -d --wait --wait-timeout 180 postgres redis redis-cache backend
"${compose[@]}" run --rm --no-deps --user 0 celery-beat chown -R 1001:1001 /beat
"${compose[@]}" up -d celery-worker
for attempt in {1..12}; do
  if "${compose[@]}" exec -T celery-worker celery -A app.celery_app inspect ping --timeout=5; then
    break
  fi
  (( attempt < 12 )) || exit 1
  sleep 5
done
curl -fsS --retry 5 --retry-delay 3 http://127.0.0.1:8000/ready
"${compose[@]}" up -d celery-beat cloudflared
[[ $("${compose[@]}" ps --status running -q celery-beat | wc -l) -eq 1 ]]
actual=$(docker inspect --format '{{.Image}}' "$("${compose[@]}" ps -q backend)")
[[ "$actual" == "$(docker image inspect --format '{{.Id}}' "$BACKEND_IMAGE")" ]]
curl -fsS --retry 5 --retry-delay 3 https://api.cardboarddex.app/ready
curl -fsS --get --data-urlencode q=pikachu --data-urlencode limit=1 https://api.cardboarddex.app/cards/search > /dev/null
if [[ -n "$old" && "$old" != "$release" ]]; then
  ln -sfn "$old" /opt/cardboarddex/previous
fi
ln -sfn "$release" /opt/cardboarddex/current
systemctl enable --now cardboarddex-backup.timer 2>/dev/null || true
trap - EXIT
echo 'Verified deployment completed'
