#!/bin/bash
set -euo pipefail

# Restore Immich DB or Gitea from dump files
# Usage: ./restore-services.sh immich /path/to/immich-db-*.sql.gz
#        ./restore-services.sh gitea /path/to/gitea-dump-*.zip

if [ $# -lt 2 ]; then
  echo "Usage: $0 <immich|gitea> <dump-file>"
  exit 1
fi

TARGET="$1"
DUMPFILE="$2"

if [ ! -f "$DUMPFILE" ]; then
  echo "Error: Dump file not found: $DUMPFILE" >&2
  exit 1
fi

case "$TARGET" in
  immich)
    IMMICH_DB_CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
    IMMICH_DB_USER="${IMMICH_DB_USER:-postgres}"
    
    echo "Restoring Immich DB from: $DUMPFILE"
    if [ -z "$(docker ps -q -f name="^${IMMICH_DB_CONTAINER}$")" ]; then
      docker start "$IMMICH_DB_CONTAINER" && sleep 3
    fi
    
    gunzip -c "$DUMPFILE" | docker exec -i "$IMMICH_DB_CONTAINER" psql --username="$IMMICH_DB_USER" postgres
    echo "Immich DB restored"
    ;;

  gitea)
    GITEA_CONTAINER="${GITEA_CONTAINER:-gitea}"
    echo "Restoring Gitea from: $DUMPFILE"
    echo "Unpacking dump inside container at /tmp/gitea-restore"
    docker cp "$DUMPFILE" "$GITEA_CONTAINER:/tmp/"
    docker exec "$GITEA_CONTAINER" bash -c "unzip -o /tmp/$(basename "$DUMPFILE") -d /tmp/gitea-restore"
    echo ""
    echo "Gitea dump unpacked. Manual steps required:"
    echo "  docker exec -it $GITEA_CONTAINER bash"
    echo "  cd /tmp/gitea-restore"
    echo "  # Move data, repos, app.ini to proper locations"
    echo "  # Import gitea-db.sql into your database"
    ;;

  *)
    echo "Unknown target: $TARGET" >&2
    exit 1
    ;;
esac
