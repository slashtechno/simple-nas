#!/bin/bash
set -euo pipefail

# Creates Immich DB dump and Gitea dump in /mnt/backup/service-dumps/
# Keeps last 3 dumps of each type. Called automatically by restic backup scripts.

DUMP_DIR="${DUMP_DIR:-/mnt/backup/service-dumps}"
mkdir -p "$DUMP_DIR"
timestamp() { date +%Y%m%dT%H%M%S; }

# Immich DB dump
IMMICH_DB_CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
IMMICH_DB_USER="${IMMICH_DB_USER:-postgres}"
IMMICH_DUMP="$DUMP_DIR/immich-db-$(timestamp).sql.gz"

if docker ps -q -f name="^${IMMICH_DB_CONTAINER}$" >/dev/null 2>&1; then
  echo "Dumping Immich DB..."
  docker exec -t "$IMMICH_DB_CONTAINER" pg_dumpall --clean --if-exists --username="$IMMICH_DB_USER" | gzip > "$IMMICH_DUMP"
else
  echo "Warning: Immich container not running" >&2
fi

# Gitea dump
GITEA_CONTAINER="${GITEA_CONTAINER:-gitea}"
if docker ps -q -f name="^${GITEA_CONTAINER}$" >/dev/null 2>&1; then
  echo "Creating Gitea dump..."
  docker exec --user git "$GITEA_CONTAINER" bash -c "/usr/local/bin/gitea dump --output /tmp" || true
  GITEA_ZIP="$(docker exec "$GITEA_CONTAINER" bash -c 'ls -1t /tmp/gitea-dump-*.zip 2>/dev/null | head -n1' || true)"
  if [ -n "$GITEA_ZIP" ]; then
    docker cp "$GITEA_CONTAINER:$GITEA_ZIP" "$DUMP_DIR/"
    docker exec "$GITEA_CONTAINER" rm -f "$GITEA_ZIP"
  fi
else
  echo "Warning: Gitea container not running" >&2
fi

# Keep only last 3 dumps of each type
find "$DUMP_DIR" -name 'immich-db-*.sql.gz' -type f | sort -r | tail -n +4 | xargs -r rm -f
find "$DUMP_DIR" -name 'gitea-dump-*.zip' -type f | sort -r | tail -n +4 | xargs -r rm -f

echo "Service dumps complete in $DUMP_DIR"
