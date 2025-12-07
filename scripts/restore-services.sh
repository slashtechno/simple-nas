#!/bin/bash
set -euo pipefail

# Restore Immich DB or Gitea from dump files
# Usage: ./restore-services.sh immich /path/to/immich-db-*.sql.gz
#        ./restore-services.sh gitea /path/to/gitea-dump-*.zip
#
# Notes (Gitea, Docker rootless best practices):
# - Stop Gitea before restoring to ensure consistency.
# - Use a one-off helper container with `--volumes-from gitea` to place files.
# - Paths (rootless): app.ini -> /etc/gitea/app.ini, data -> /var/lib/gitea,
#   repos -> /var/lib/gitea/git/repositories.
# - After file restore, regenerate hooks: `gitea admin regenerate hooks`.

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
    GITEA_IMAGE_HELPER="${GITEA_IMAGE_HELPER:-gitea/gitea:latest}"
    echo "Restoring Gitea (Docker, rootful) from: $DUMPFILE"

    if [ -z "$(docker ps -q -f name=^${GITEA_CONTAINER}$)" ] && [ -z "$(docker ps -aq -f name=^${GITEA_CONTAINER}$)" ]; then
      echo "Error: Gitea container '$GITEA_CONTAINER' not found" >&2
      exit 1
    fi

    echo "Stopping Gitea to ensure consistency..."
    docker stop "$GITEA_CONTAINER" >/dev/null

    echo "Running helper container to wipe and restore files into Gitea volumes..."
    docker run --rm \
      --name gitea-restore-helper \
      --volumes-from "$GITEA_CONTAINER" \
      -v "$(readlink -f "$DUMPFILE")":/tmp/dump.zip:ro \
      "$GITEA_IMAGE_HELPER" bash -lc '
        set -euo pipefail
        unzip -o /tmp/dump.zip -d /tmp/restore
        cd /tmp/restore
        # Wipe current data for a clean restore (KISS)
        rm -rf /data/gitea/* /data/git/repositories/* || true
        # app.ini (rootful: data/conf/app.ini -> /data/gitea/conf/app.ini)
        if [ -f data/conf/app.ini ]; then
          mkdir -p /data/gitea/conf
          cp -a data/conf/app.ini /data/gitea/conf/app.ini
        fi
        # data -> /data/gitea (APP_DATA_PATH)
        if [ -d data ]; then
          mkdir -p /data/gitea
          rsync -a data/ /data/gitea/
        fi
        # repos -> /data/git/repositories
        if [ -d repos ]; then
          mkdir -p /data/git/repositories
          rsync -a repos/ /data/git/repositories/
        fi
        chown -R git:git /data || true
        # Regenerate hooks to ensure paths are correct
        if command -v gitea >/dev/null 2>&1; then
          /usr/local/bin/gitea -c "/data/gitea/conf/app.ini" admin regenerate hooks || true
        fi
        # Auto-import SQLite DB if present (assumes sqlite-only setup)
        if [ -f gitea-db.sql ]; then
          # SQLite DB path under APP_DATA_PATH; common locations: /data/gitea/gitea.db or /data/gitea/data/gitea.db
          DB_PATH=""
          if [ -f /data/gitea/gitea.db ]; then DB_PATH="/data/gitea/gitea.db"; fi
          if [ -z "$DB_PATH" ] && [ -f /data/gitea/data/gitea.db ]; then DB_PATH="/data/gitea/data/gitea.db"; fi
          if [ -n "$DB_PATH" ]; then
            echo "Importing SQLite DB from gitea-db.sql into $DB_PATH"
            sqlite3 "$DB_PATH" < /tmp/restore/gitea-db.sql || echo "SQLite import failed; please import manually"
          else
            echo "SQLite DB file not found under /data/gitea; skipping import"
          fi
        fi
      '

    echo "Starting Gitea..."
    docker start "$GITEA_CONTAINER" >/dev/null
    echo "Gitea restore complete (rootful). SQLite DB import attempted if dump was present."
    ;;

  *)
    echo "Unknown target: $TARGET" >&2
    exit 1
    ;;
esac
