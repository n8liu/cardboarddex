#!/usr/bin/env bash
# One-time hardening of the current host when AWS blocks a replacement instance.
# Requires an independently restored S3 backup and a staged rollback release.
set -euo pipefail
[[ $(id -u) == 0 ]] || { echo 'Run as root' >&2; exit 1; }
: "${1:?Reviewed release directory required}"
: "${VERIFIED_OFFSITE_BACKUP:?Provide the S3 key of the independently restored backup}"
release=$(realpath "$1")
[[ "$release" == /opt/cardboarddex/releases/* ]]
[[ -f /etc/cardboarddex/app.env && -f /opt/cardboarddex/releases/legacy/docker-compose.prod.yml ]]
[[ ! -e /etc/cardboarddex/cutover-complete ]] || { echo 'Cutover already completed; use regular deployment' >&2; exit 1; }
umask 077
install -d -m 0700 /var/backups/cardboarddex/cutover
root=/var/backups/cardboarddex/cutover
seeded=false
restore_service() {
  code=$?
  if (( code != 0 )); then
    echo 'Cutover failed; restoring application availability' >&2
    if [[ "$seeded" == true ]]; then
      docker compose -p app --env-file /etc/cardboarddex/app.env -f /opt/cardboarddex/releases/legacy/docker-compose.prod.yml up -d --remove-orphans || true
    else
      docker start cardboarddex-backend cardboarddex-celery-worker || true
    fi
  fi
  systemctl start cardboarddex-backup.timer || true
  exit "$code"
}
trap restore_service EXIT
systemctl stop cardboarddex-backup.timer cardboarddex-backup.service
docker stop -t 3600 cardboarddex-celery-worker
docker stop -t 60 cardboarddex-backend
docker exec cardboarddex-postgres pg_dump -U cardboarddex -d cardboarddex -Fc --no-owner --no-privileges > "$root/postgres.dump"
docker exec -i cardboarddex-postgres pg_restore --list < "$root/postgres.dump" > /dev/null
docker exec cardboarddex-postgres psql -U cardboarddex -d cardboarddex -Atc "SELECT count(*) FROM cards; SELECT count(*) FROM sets; SELECT count(*) FROM price_observations; SELECT version_num FROM alembic_version;" > "$root/before-counts.txt"
docker exec cardboarddex-redis redis-cli --rdb /tmp/cutover.rdb
docker cp cardboarddex-redis:/tmp/cutover.rdb "$root/redis.rdb"
redis_image=$(docker inspect --format '{{.Image}}' cardboarddex-redis)
if docker volume inspect app_redis_durable > /dev/null 2>&1; then
  echo 'Durable Redis volume already exists; inspect interrupted cutover before proceeding' >&2
  exit 1
fi
docker volume create app_redis_durable > /dev/null
docker run --rm --network none --user 0 -v app_redis_durable:/data -v "$root/redis.rdb:/seed.rdb:ro" "$redis_image" sh -c 'cp /seed.rdb /data/dump.rdb && chown redis:redis /data/dump.rdb'
docker run -d --name cardboarddex-redis-seed --network none -v app_redis_durable:/data "$redis_image" redis-server --maxmemory 64mb --maxmemory-policy noeviction --appendonly no --save '' > /dev/null
for attempt in {1..30}; do
  if docker exec cardboarddex-redis-seed redis-cli ping; then break; fi
  (( attempt < 30 )) || exit 1
  sleep 1
done
docker exec cardboarddex-redis-seed redis-cli CONFIG SET appendonly yes
for attempt in {1..60}; do
  info=$(docker exec cardboarddex-redis-seed redis-cli INFO persistence)
  if grep -q 'aof_rewrite_in_progress:0' <<< "$info" && grep -q 'aof_last_bgrewrite_status:ok' <<< "$info"; then break; fi
  (( attempt < 60 )) || exit 1
  sleep 1
done
docker stop -t 30 cardboarddex-redis-seed > /dev/null
docker rm cardboarddex-redis-seed > /dev/null
seeded=true
python3 "$release/scripts/lightsail/rotate_password.py"
sudo -u ubuntu bash "$release/scripts/lightsail/release.sh" "$release"
BACKEND_IMAGE=$(cat "$release/image.txt")
export BACKEND_IMAGE
compose=(docker compose -p app --env-file /etc/cardboarddex/app.env -f "$release/docker-compose.prod.yml")
"${compose[@]}" exec -T postgres psql -U cardboarddex -d cardboarddex -Atc "SELECT count(*) FROM cards; SELECT count(*) FROM sets; SELECT count(*) FROM price_observations; SELECT version_num FROM alembic_version;" > "$root/after-counts.txt"
# Ingestion has resumed; table counts may increase, but must never fall.
python3 - "$root" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1])
a=(p/'before-counts.txt').read_text().splitlines()
b=(p/'after-counts.txt').read_text().splitlines()
assert a[-1] == b[-1], 'Schema revision changed unexpectedly'
assert all(int(y) >= int(x) for x,y in zip(a[:-1],b[:-1])), 'A table lost rows during cutover'
print('Schema and data counts verified')
PY
python3 - <<'PY'
from pathlib import Path
p=Path('/etc/cardboarddex/backup.env')
s=p.read_text().splitlines()
s=[line for line in s if not line.startswith(('APP_ENV_FILE=','COMPOSE_FILE='))]
p.write_text('\n'.join(s)+'\n')
PY
date -u +%FT%TZ > /etc/cardboarddex/cutover-complete
systemctl start --no-block cardboarddex-backup.service
trap - EXIT
systemctl start cardboarddex-backup.timer
echo 'Current-host hardening completed; 1 GB upgrade remains pending AWS quota'
