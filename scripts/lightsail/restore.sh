#!/usr/bin/env bash
# Destination must already be running PostgreSQL 16 and contain no user tables.
set -euo pipefail
: "${RESTORE_CONTAINER:?Specify a disposable or empty PostgreSQL container}"
: "${RESTORE_DB:=cardboarddex}"
: "${RESTORE_USER:=cardboarddex}"
: "${1:?Usage: restore.sh /path/to/postgres.dump}"
[[ -s "$1" ]] || { echo 'Missing or empty archive' >&2; exit 1; }
count=$(docker exec "$RESTORE_CONTAINER" psql -U "$RESTORE_USER" -d "$RESTORE_DB" -At -v ON_ERROR_STOP=1 -c "SELECT count(*) FROM pg_tables WHERE schemaname NOT IN ('pg_catalog','information_schema')")
[[ "$count" == 0 ]] || { echo 'Refusing restore into a nonempty database' >&2; exit 1; }
docker exec -i "$RESTORE_CONTAINER" pg_restore --list < "$1" > /dev/null
docker exec -i "$RESTORE_CONTAINER" pg_restore -U "$RESTORE_USER" -d "$RESTORE_DB" --single-transaction --exit-on-error --no-owner --no-privileges < "$1"
docker exec "$RESTORE_CONTAINER" psql -U "$RESTORE_USER" -d "$RESTORE_DB" -v ON_ERROR_STOP=1 -c 'SELECT version_num FROM alembic_version; SELECT count(*) AS cards FROM cards; SELECT count(*) AS sets FROM sets;'
