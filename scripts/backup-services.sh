#!/bin/bash
set -euo pipefail

# Creates Immich DB dump and Gitea dump in /mnt/backup/service-dumps/
# Keeps last 3 dumps of each type. Called automatically by restic backup scripts.

DUMP_DIR="${DUMP_DIR:-/mnt/backup/service-dumps}"
mkdir -p "$DUMP_DIR"
timestamp() { date +%Y%m%dT%H%M%S; }

# Source repository .env if present so the script can pick up IMMIH_DB_* settings
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)/.."
ENV_FILE="$SCRIPT_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
fi

# Immich DB dump
IMMICH_DB_CONTAINER="${IMMICH_DB_CONTAINER:-immich_postgres}"
# DB role inside Postgres for Immich (default matches docker-compose `DB_USERNAME`)
IMMICH_DB_USER="${IMMICH_DB_USER:-immich}"
IMMICH_DB_PASSWORD="${IMMICH_DB_PASSWORD:-}" # optional; read from environment if provided
IMMICH_DUMP="$DUMP_DIR/immich-db-$(timestamp).sql.gz"

if docker ps -q -f name="^${IMMICH_DB_CONTAINER}$" >/dev/null 2>&1; then
  echo "Dumping Immich DB..."
  # Run pg_dumpall inside the container as root and specify the DB user with -U.
  # If a password is provided via IMMICH_DB_PASSWORD, pass it as PGPASSWORD to avoid prompts.
  if [ -n "$IMMICH_DB_PASSWORD" ]; then
    if ! docker exec -t -e PGPASSWORD="$IMMICH_DB_PASSWORD" "$IMMICH_DB_CONTAINER" \
         pg_dumpall --clean --if-exists --username="$IMMICH_DB_USER" | gzip > "$IMMICH_DUMP"; then
      echo "Error: Immich DB dump failed (check DB credentials)" >&2
      exit 1
    fi
  else
    if ! docker exec -t "$IMMICH_DB_CONTAINER" \
         pg_dumpall --clean --if-exists --username="$IMMICH_DB_USER" | gzip > "$IMMICH_DUMP"; then
      echo "Error: Immich DB dump failed (no password provided)" >&2
      exit 1
    fi
  fi
else
  echo "Warning: Immich container not running" >&2
fi

# Gitea dump
GITEA_CONTAINER="${GITEA_CONTAINER:-gitea}"
if docker ps -q -f name="^${GITEA_CONTAINER}$" >/dev/null 2>&1; then
  echo "Creating Gitea dump..."
  # Locate the gitea binary inside the container and run the documented
  # dump command with an explicit tempdir. This is a simple, deterministic
  # invocation that works for the gitea 1.25.2 binary present on this host.
  GITEA_BIN="$(docker exec "$GITEA_CONTAINER" bash -lc 'command -v gitea' || true)"
  if [ -z "$GITEA_BIN" ]; then
    echo "Warning: gitea binary not found inside container; skipping gitea dump" >&2
  else
    if docker exec --user git "$GITEA_CONTAINER" bash -lc "$GITEA_BIN dump -t /tmp" >/dev/null 2>&1; then
      echo "Gitea dump invoked successfully"
    else
      echo "Warning: gitea dump failed" >&2
    fi
  fi

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
