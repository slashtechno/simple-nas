#!/bin/bash
set -o pipefail

## RESTIC_PASSWORD_FILE selection
# Default to caller's home file, but when running under sudo/root prefer the
# calling user's file if present. This avoids failures when calling via sudo
# without a root password file (common when the script is run from a cron
# job or by a system user).
if [ -n "${RESTIC_PASSWORD_FILE:-}" ]; then
  export RESTIC_PASSWORD_FILE
else
  if [ "$(id -u)" -eq 0 ]; then
    # We're root. Prefer /root/.restic-password if it exists, otherwise try
    # the sudo user's home file.
    if [ -f /root/.restic-password ]; then
      export RESTIC_PASSWORD_FILE=/root/.restic-password
    elif [ -n "${SUDO_USER:-}" ] && [ -f "/home/${SUDO_USER}/.restic-password" ]; then
      export RESTIC_PASSWORD_FILE="/home/${SUDO_USER}/.restic-password"
    elif [ -f "${HOME:-/root}/.restic-password" ]; then
      export RESTIC_PASSWORD_FILE="${HOME:-/root}/.restic-password"
    else
      # Fallback to a user-level default (will likely error later but message is clearer)
      export RESTIC_PASSWORD_FILE="/root/.restic-password"
    fi
  else
    export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-$HOME/.restic-password}"
  fi
fi

export RESTIC_REPOSITORY=/mnt/backup/restic-repo

LOG_FILE="/mnt/backup/logs/restic-local-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

# Directories to exclude from backups. Keep as an immutable list so callers
# can review or extend in one place. These exclude patterns avoid permission
# errors for socket/DB/ssh dirs and skip filesystem junk like lost+found.
readonly EXCLUDES=(
  "/mnt/t7/docker/gitea/ssh"
  "/mnt/t7/docker/immich_postgres"
  "/mnt/t7/docker/copyparty_config/copyparty"
  "/mnt/t7/lost+found"
)

# Build restic-friendly exclude arguments from the `EXCLUDES` array
EXCLUDE_ARGS=()
for p in "${EXCLUDES[@]}"; do
  EXCLUDE_ARGS+=( --exclude "$p" )
done

{
  echo "=== Local Backup: $(date) ==="
  # Create service dumps (Immich DB, Gitea)
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  # If the service dump helper exists, always invoke it with bash. This
  # avoids relying on the executable bit and ensures a consistent shell.
  if [ -f "$SCRIPT_DIR/backup-services.sh" ]; then
    bash "$SCRIPT_DIR/backup-services.sh" || { echo "Service dump failed"; exit 1; }
  fi

  # Backup /mnt/t7 and /mnt/backup/service-dumps
  restic backup /mnt/t7 /mnt/backup/service-dumps \
    --exclude "/mnt/t7/immich_model_cache" \
    --exclude "/mnt/t7/**/.cache" \
    "${EXCLUDE_ARGS[@]}" \
    --tag daily \
    --verbose
  
  if [ $? -eq 0 ]; then
    echo "Backup successful. Removing old snapshots..."
    # Keep last 7 daily + 4 weekly + 1 monthly snapshots
    restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 1 --prune
    
    echo "Repository stats:"
    restic stats
    echo "Free space on HDD:"
    df -h /mnt/backup
  else
    echo "ERROR: Backup failed!"
    exit 1
  fi
  
  echo "=== Complete: $(date) ==="
} | tee -a "$LOG_FILE"