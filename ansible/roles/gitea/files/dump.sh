#!/bin/bash
# Gitea dump. Run by backup-services.sh, which passes the dump directory as $1
# and keeps the last 3 files named gitea-*.
# restore-services.sh and docs/backups.md depend on the file name gitea-dump-*.zip.
set -euo pipefail

DUMP_DIR="$1"
CONTAINER="${GITEA_CONTAINER:-gitea}"
APP_INI="${GITEA_APP_INI:-/data/gitea/conf/app.ini}"
TARGET="/tmp/gitea-dump-$(date +%Y%m%dT%H%M%S).zip"

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "ERROR: container $CONTAINER is not running; no dump made" >&2
  exit 1
fi

# Run as the git user (the container's runtime user) with an explicit config
# and target file so the output is deterministic.
if ! docker exec --user git "$CONTAINER" test -r "$APP_INI"; then
  echo "ERROR: gitea config not readable at $APP_INI; no dump made" >&2
  exit 1
fi

echo "Creating Gitea dump..."
if docker exec --user git "$CONTAINER" gitea dump \
     --config "$APP_INI" --tempdir /tmp --file "$TARGET" --skip-log; then
  docker cp "$CONTAINER:$TARGET" "$DUMP_DIR/"
  docker exec "$CONTAINER" rm -f "$TARGET"
  echo "Gitea dump written to $DUMP_DIR/$(basename "$TARGET")"
else
  echo "ERROR: gitea dump failed" >&2
  exit 1
fi
