#!/bin/bash
# Garage metadata dump. Run by backup-services.sh, which passes the dump directory as $1
# and keeps the last 3 files named garage-*.
# Garage's metadata database and node key are owned by root and unreadable to the backup user, and a raw
# copy of a live database can be inconsistent. So Garage writes its own snapshot of the database, and
# docker cp (which needs no shell in the container) copies it out together with the node key and layout.
# The output is a .tar.gz named garage-meta-*; restoring it is described in docs/backups.md.
set -euo pipefail

DUMP_DIR="$1"
CONTAINER="${GARAGE_CONTAINER:-garage}"
META="/var/lib/garage/meta"
TARGET="$DUMP_DIR/garage-meta-$(date +%Y%m%dT%H%M%S).tar.gz"

if [ "$(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null)" != "true" ]; then
  echo "ERROR: container $CONTAINER is not running; no dump made" >&2
  exit 1
fi

# The dump holds the node key, so only the backup user may read it. The scratch directory is
# removed on exit.
umask 077
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

echo "Creating Garage metadata snapshot..."
docker exec "$CONTAINER" /garage meta snapshot
docker cp "$CONTAINER:$META/snapshots" "$WORK/snapshots"
for f in node_key node_key.pub cluster_layout; do
  docker cp "$CONTAINER:$META/$f" "$WORK/$f"
done

tar -C "$WORK" -czf "$TARGET" .
echo "Garage metadata dump written to $TARGET"
