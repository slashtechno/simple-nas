#!/bin/bash
# Immich database dump. Run by backup-services.sh, which passes the dump
# directory as $1 and keeps the last 3 files named immich-*.
# restore-services.sh and docs/backups.md depend on the file name immich-db-*.sql.gz.
set -euo pipefail

DUMP_DIR="$1"
CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
# Postgres role inside the container (matches POSTGRES_USER in the immich compose file)
DB_USER="${IMMICH_DB_USER:-immich}"
DB_PASSWORD="${IMMICH_DB_PASSWORD:-}"   # optional; passed to pg_dumpall as PGPASSWORD
DUMP="$DUMP_DIR/immich-db-$(date +%Y%m%dT%H%M%S).sql.gz"

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "ERROR: container $CONTAINER is not running; no dump made" >&2
  exit 1
fi

echo "Dumping Immich DB..."
env_args=()
[ -n "$DB_PASSWORD" ] && env_args=(-e "PGPASSWORD=$DB_PASSWORD")
# Write to a .tmp name and rename on success, so a half-written dump never
# looks like a good one (and never counts toward the "keep 3").
if ! docker exec "${env_args[@]}" "$CONTAINER" \
     pg_dumpall --clean --if-exists --username="$DB_USER" | gzip > "$DUMP.tmp"; then
  rm -f "$DUMP.tmp"
  echo "Error: Immich DB dump failed (check DB credentials)" >&2
  exit 1
fi
mv "$DUMP.tmp" "$DUMP"
