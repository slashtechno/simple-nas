#!/bin/bash
set -euo pipefail

# Restore Immich DB or Gitea from dump files
# Usage: ./restore-services.sh immich /path/to/immich-db-*.sql.gz
#        ./restore-services.sh gitea /path/to/gitea-dump-*.zip
#
# Gitea: the container is stopped, a one-off helper container (--volumes-from gitea)
# replaces the data and repositories from the dump, hooks are regenerated, then it restarts.

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
    # Must match POSTGRES_USER in roles/immich/templates/docker-compose.yml.j2 (and backup-services.sh).
    IMMICH_DB_USER="${IMMICH_DB_USER:-immich}"
    
    echo "Restoring Immich DB from: $DUMPFILE"
    if [ -z "$(docker ps -q -f name="^${IMMICH_DB_CONTAINER}$")" ]; then
      docker start "$IMMICH_DB_CONTAINER" && sleep 3
    fi
    
    gunzip -c "$DUMPFILE" | docker exec -i "$IMMICH_DB_CONTAINER" psql -v ON_ERROR_STOP=1 --username="$IMMICH_DB_USER" postgres
    echo "Immich DB restored"
    ;;

  gitea)
    GITEA_CONTAINER="${GITEA_CONTAINER:-gitea}"
    echo "Restoring Gitea from: $DUMPFILE"

    if [ -z "$(docker ps -q -f name=^${GITEA_CONTAINER}$)" ] && [ -z "$(docker ps -aq -f name=^${GITEA_CONTAINER}$)" ]; then
      echo "Error: Gitea container '$GITEA_CONTAINER' not found" >&2
      exit 1
    fi

    # The helper uses the image Gitea is already running, so no version is guessed.
    GITEA_IMAGE_HELPER="${GITEA_IMAGE_HELPER:-$(docker inspect -f '{{.Config.Image}}' "$GITEA_CONTAINER")}"

    echo "Stopping Gitea to ensure consistency..."
    docker stop "$GITEA_CONTAINER" >/dev/null
    # If the restore fails below, Gitea stays stopped on purpose: starting it on half-restored data is worse.
    trap 'echo "Restore FAILED. Gitea is left stopped; fix the error above and rerun." >&2' ERR

    echo "Running helper container to wipe and restore files into Gitea volumes..."
    docker run --rm \
      --name gitea-restore-helper \
      --volumes-from "$GITEA_CONTAINER" \
      -v "$(readlink -f "$DUMPFILE")":/tmp/dump.zip:ro \
      "$GITEA_IMAGE_HELPER" bash -lc '
        set -euo pipefail
        unzip -o /tmp/dump.zip -d /tmp/restore
        cd /tmp/restore
        # Wipe the current data so the restore is clean
        rm -rf /data/gitea/* /data/git/repositories/*
        # app.ini (rootful: data/conf/app.ini -> /data/gitea/conf/app.ini)
        if [ -f data/conf/app.ini ]; then
          mkdir -p /data/gitea/conf
          cp -a data/conf/app.ini /data/gitea/conf/app.ini
        fi
        # data -> /data/gitea (APP_DATA_PATH)
        if [ -d data ]; then
          mkdir -p /data/gitea
          cp -a data/. /data/gitea/
        fi
        # repos -> /data/git/repositories
        if [ -d repos ]; then
          mkdir -p /data/git/repositories
          cp -a repos/. /data/git/repositories/
        fi
        chown -R git:git /data || true
        # Regenerate hooks to ensure paths are correct
        if command -v gitea >/dev/null 2>&1; then
          /usr/local/bin/gitea -c "/data/gitea/conf/app.ini" admin regenerate hooks || true
        fi
      '

    echo "Starting Gitea..."
    docker start "$GITEA_CONTAINER" >/dev/null
    echo "Gitea restore complete."
    ;;

  *)
    echo "Unknown target: $TARGET" >&2
    exit 1
    ;;
esac
