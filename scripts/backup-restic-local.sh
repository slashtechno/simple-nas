#!/bin/bash
set -o pipefail

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

LOG_FILE="/mnt/backup/logs/restic-local-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "=== Local Backup: $(date) ==="
  # Create service dumps (Immich DB, Gitea)
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
  if [ -x "$SCRIPT_DIR/backup-services.sh" ]; then
    "$SCRIPT_DIR/backup-services.sh" || { echo "Service dump failed"; exit 1; }
  fi

  # Backup /mnt/t7 and /mnt/backup/service-dumps
  restic backup /mnt/t7 /mnt/backup/service-dumps \
    --exclude "/mnt/t7/immich_model_cache" \
    --exclude "/mnt/t7/**/.cache" \
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