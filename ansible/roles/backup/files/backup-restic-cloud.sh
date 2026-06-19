#!/bin/bash
set -o pipefail

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

## Load backup paths from a newline-delimited file next to this script.
## This avoids sourcing arbitrary shell code. Optionally set
## BACKUP_PATHS_FILE to point to a different file.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
BACKUP_PATHS_FILE="${BACKUP_PATHS_FILE:-$SCRIPT_DIR/backup-paths.txt}"
if [ ! -f "$BACKUP_PATHS_FILE" ]; then
  echo "ERROR: backup paths file not found: $BACKUP_PATHS_FILE" >&2
  exit 1
fi
# Read non-empty lines into BACKUP_PATHS array, strip CRs
mapfile -t BACKUP_PATHS < <(grep -v '^[[:space:]]*$' "$BACKUP_PATHS_FILE" | sed 's/\r$//')

LOG_FILE="/mnt/backup/logs/restic-cloud-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "=== Cloud Backup: $(date) ==="
  # Create service dumps (Immich DB, Gitea)
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  if [ -x "$SCRIPT_DIR/backup-services.sh" ]; then
    "$SCRIPT_DIR/backup-services.sh" || { echo "Service dump failed"; exit 1; }
  fi

  # Load environment-specified paths (safe parse, do NOT source arbitrary .env)
  # Prefer project `.env` (repo root) falling back to `.env.example`.
  ENV_FILE="${ENV_FILE:-$SCRIPT_DIR/../.env}"
  if [ ! -f "$ENV_FILE" ] && [ -f "$SCRIPT_DIR/../.env.example" ]; then
    ENV_FILE="$SCRIPT_DIR/../.env.example"
  fi
  SKIP_PATHS=()
  # Read only the specific keys we care about from ENV_FILE. This avoids
  # sourcing and stays simple and readable.
  if [ -f "$ENV_FILE" ]; then
    DB_DATA_LOCATION=""
    GITEA_DB_PATH=""
    while IFS='=' read -r raw_key raw_val || [ -n "$raw_key" ]; do
      # trim key and value
      key=$(echo "$raw_key" | xargs)
      # remove surrounding quotes from value, then trim
      val=$(printf '%s' "$raw_val" | sed -E "s/^['\"]|['\"]$//g" | xargs)

      # skip comments/empty keys
      case "$key" in
        ''|\#*) continue ;;
      esac

      case "$key" in
        DB_DATA_LOCATION)
          DB_DATA_LOCATION="$val" ;;
        GITEA__database__PATH)
          GITEA_DB_PATH="$val" ;;
      esac
    done < <(grep -E '^[[:space:]]*[A-Za-z_][A-Za-z0-9_]*=' "$ENV_FILE" || true)

    [ -n "$DB_DATA_LOCATION" ] && SKIP_PATHS+=("$DB_DATA_LOCATION")
    if [ -n "$GITEA_DB_PATH" ]; then
      SKIP_PATHS+=("$(dirname "$GITEA_DB_PATH")")
    fi
  fi

  # Backup service dumps first
  if [ -d "/mnt/backup/service-dumps" ]; then
    restic backup /mnt/backup/service-dumps --tag weekly --verbose
  fi

  # Backup critical paths from backup-paths.txt
  for path in "${BACKUP_PATHS[@]}"; do
    expanded_path="$path"
    # Expand leading ~ to $HOME without using eval
    if [[ "$expanded_path" == ~* ]]; then
      expanded_path="${expanded_path/#\~/$HOME}"
    fi
    # Replace literal $USER with the current user name (safe textual replacement)
    expanded_path="${expanded_path//\$USER/$USER}"

    # Avoid backing up live database data directories (e.g. postgres data) to cloud.
    # Prefer logical dumps produced by `backup-services.sh` (stored in /mnt/backup/service-dumps).
    # If the repo `.env` defines DB_DATA_LOCATION or UPLOAD_LOCATION, skip those paths.
    skip=false
    for sp in "${SKIP_PATHS[@]:-}"; do
      if [ -n "$sp" ]; then
        # If expanded_path equals or is under the env path, skip it
        if [[ "$expanded_path" == "$sp" || "$expanded_path" == "$sp"/* ]]; then
          echo "Skipping path defined in .env for cloud backup: $expanded_path (match $sp)"
          skip=true
          break
        fi
      fi
    done
    if $skip; then
      continue
    fi

    if [ -d "$expanded_path" ]; then
      echo "Backing up $expanded_path..."
      restic backup "$expanded_path" --tag weekly --verbose
    else
      echo "Skipping missing path: $expanded_path"
    fi
  done
  
  if [ $? -eq 0 ]; then
    echo "Cloud backup successful. Removing old snapshots..."
    restic forget --keep-weekly 12 --keep-monthly 6 --prune
    
    echo "Cloud repository stats:"
    restic stats
  else
    echo "ERROR: Cloud backup failed!"
    exit 1
  fi
  
  echo "=== Complete: $(date) ==="
} | tee -a "$LOG_FILE"