#!/bin/bash
# Immich database dump. Run by backup-services.sh, which passes the dump
# directory as $1 and keeps the last 3 files named immich-*.
# restore-services.sh and BACKUPS.md depend on the file name immich-db-*.sql.gz.
set -euo pipefail

DUMP_DIR="$1"
CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
# Postgres role inside the container (matches POSTGRES_USER in the immich compose file)
DB_USER="${IMMICH_DB_USER:-immich}"
DB_PASSWORD="${IMMICH_DB_PASSWORD:-}"   # optional; passed to pg_dumpall as PGPASSWORD
DUMP="$DUMP_DIR/immich-db-$(date +%Y%m%dT%H%M%S).sql.gz"

if ! docker ps -q -f name="^${CONTAINER}$" >/dev/null 2>&1; then
  echo "Warning: Immich container not running" >&2
  exit 0
fi

echo "Dumping Immich DB..."
env_args=()
[ -n "$DB_PASSWORD" ] && env_args=(-e "PGPASSWORD=$DB_PASSWORD")
if ! docker exec -t "${env_args[@]}" "$CONTAINER" \
     pg_dumpall --clean --if-exists --username="$DB_USER" | gzip > "$DUMP"; then
  echo "Error: Immich DB dump failed (check DB credentials)" >&2
  exit 1
fi
