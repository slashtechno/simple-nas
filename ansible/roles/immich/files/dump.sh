#!/bin/bash
# Immich database dump. Run by backup-services.sh, which passes the dump
# directory as $1 and keeps the last 3 files named immich-*.
# restore-services.sh and docs/backups.md depend on the file name immich-db-*.sql.gz.
set -euo pipefail

DUMP_DIR="$1"
CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
# Postgres role inside the container; keep it the same as POSTGRES_USER in the immich compose file and restore-services.sh
DB_USER="${IMMICH_DB_USER:-immich}"
DUMP="$DUMP_DIR/immich-db-$(date +%Y%m%dT%H%M%S).sql.gz"

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "ERROR: container $CONTAINER is not running; no dump made" >&2
  exit 1
fi

echo "Dumping Immich DB..."
# Only the `immich` database (POSTGRES_DB in docker-compose.yml.j2). pg_dumpall would also drop and recreate the
# role and the maintenance database, which the restore cannot do while connected as that role.
# Write to a .tmp name and rename on success, so a half-written dump never
# looks like a good one (and never counts toward the "keep 3").
if ! docker exec "$CONTAINER" \
     pg_dump --clean --if-exists --username="$DB_USER" immich | gzip > "$DUMP.tmp"; then
  rm -f "$DUMP.tmp"
  echo "Error: Immich DB dump failed (check DB credentials)" >&2
  exit 1
fi
mv "$DUMP.tmp" "$DUMP"
