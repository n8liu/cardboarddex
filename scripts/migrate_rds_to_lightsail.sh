#!/usr/bin/env bash
# Historical RDS export helper. No production destination is selected by default.
set -euo pipefail
umask 077
: "${PGHOST:?Set the source PostgreSQL host}"
: "${PGUSER:?Set the source user}"
: "${PGDATABASE:?Set the source database}"
: "${PGPASSFILE:?Use a mode-0600 libpq password file}"
: "${EXPORT_FILE:?Set a new archive filename}"
[[ ! -e "$EXPORT_FILE" && ! -e "$EXPORT_FILE.partial" ]] || { echo 'Refusing to overwrite an export' >&2; exit 1; }
export PGSSLMODE="${PGSSLMODE:-require}"
pg_dump -Fc --no-owner --no-privileges --file "$EXPORT_FILE.partial"
pg_restore --list "$EXPORT_FILE.partial" > /dev/null
mv "$EXPORT_FILE.partial" "$EXPORT_FILE"
if [[ -n "${RESTORE_CONTAINER:-}" ]]; then
  bash "$(dirname "$0")/lightsail/restore.sh" "$EXPORT_FILE"
fi
