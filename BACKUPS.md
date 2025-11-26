# Backup Strategy for Pi NAS

**Goal**: Incremental backups with restic to 500GB HDD (local) + Google Drive (cloud). Supports multiple versions without extra storage via deduplication.

---

## Quick Setup

### 1. Install Restic

```bash
sudo apt install -y restic
restic version
```

### 2. Set Restic Password

Choose a strong password (required for accessing backups):

```bash
# Create secure password file (only readable by you)
openssl rand -base64 32 > ~/.restic-password
chmod 600 ~/.restic-password
cat ~/.restic-password  # Save this in password manager too
```

### 3. Initialize Local Repository (HDD)

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

restic init
# Output shows repository ID (note for records)
```

### 4. Configure Rclone for Cloud (One-Time, Laptop with Browser)

**On your laptop:**

```bash
rclone config
# n) New remote
# Name: gdrive-nas
# Type: Google Drive
# Use defaults for client ID/secret
# Scope: 3 (Access to files created by rclone only) ← IMPORTANT
# Authorize in browser
```

**Why scope 3?** Even if rclone config is stolen, rclone can ONLY access files it created.

**Copy to Pi:**

```bash
scp ~/.config/rclone/rclone.conf pi@your-pi:~/.config/rclone/
```

**Test on Pi:**

```bash
rclone lsd gdrive-nas:
```

### 5. Initialize Cloud Repository

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

restic init
```

---

## Daily Local Backup Script

**What**: Everything from `/mnt/t7` → HDD with automatic deduplication (keeps 7 daily + 4 weekly snapshots)

```bash
cat > ~/backup-restic-local.sh << 'EOF'
#!/bin/bash
set -o pipefail

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

LOG_FILE="/mnt/backup/logs/restic-local-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "=== Local Backup: $(date) ==="
  
  # Backup everything except cache
  restic backup /mnt/t7 \
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
EOF

chmod +x ~/backup-restic-local.sh
```

**Test it**: `~/backup-restic-local.sh`

---

## Weekly Cloud Backup Script

**What**: Selective paths → Google Drive (config databases, Gitea repos)

```bash
cat > ~/.backup-restic-cloud-config << 'EOF'
# Paths to backup to cloud (whitelist)
BACKUP_PATHS=(
  "/mnt/t7/docker/immich_postgres"
  "/mnt/t7/docker/gitea"
  "/mnt/t7/docker/copyparty_config"
  "/home/$USER/nas-docker/.env"
  "/home/$USER/nas-docker/docker-compose.yml"
  "/home/$USER/nas-docker/Caddyfile"
)
EOF
```

**Backup script**:

```bash
cat > ~/backup-restic-cloud.sh << 'EOF'
#!/bin/bash
set -o pipefail

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

source ~/.backup-restic-cloud-config

LOG_FILE="/mnt/backup/logs/restic-cloud-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"

{
  echo "=== Cloud Backup: $(date) ==="
  
  # Backup only critical paths
  for path in "${BACKUP_PATHS[@]}"; do
    if [ -d "$path" ]; then
      echo "Backing up $path..."
      restic backup "$path" --tag weekly --verbose
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
EOF

chmod +x ~/backup-restic-cloud.sh
```

**Test it**: `~/backup-restic-cloud.sh`

---

## Schedule with Cron

```bash
crontab -e
```

Add:

```cron
# Daily local backup @ 2 AM
0 2 * * * /home/$(whoami)/backup-restic-local.sh

# Weekly cloud backup @ Sunday 4 AM
0 4 * * 0 /home/$(whoami)/backup-restic-cloud.sh

# Weekly integrity check @ Wednesday 3 AM
0 3 * * 3 bash -c "export RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo && restic check" >> /mnt/backup/logs/restic-check.log 2>&1
```

---

## Check Status

```bash
# List all snapshots (local)
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo
restic snapshots

# Recent backup size
restic stats

# HDD free space
df -h /mnt/backup

# Recent logs
tail -30 /mnt/backup/logs/restic-local-*.log

# Verify repository integrity
restic check
```

**Cloud snapshots:**

```bash
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"
restic snapshots
```

---

## Restore from Local Backup

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# List all snapshots with dates
restic snapshots

# Restore latest snapshot (to original paths)
restic restore latest --target /

# Or restore to a different location
restic restore latest --target /tmp/restore-test

# Restore specific file or directory (use --include)
restic restore latest --include "/mnt/t7/docker/gitea" --target /

# Restore specific snapshot (use ID from snapshots list)
restic restore abc12345 --target /
```

### Restore Databases

**Immich database:**

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# Stop server while restoring
docker compose stop immich_server immich_microservices

# Restore database backup (if backed up as a dump)
# Or restore the postgres data directory
restic restore latest --include "/mnt/t7/docker/immich_postgres" --target /

# Restart
docker compose start immich_server immich_microservices
```

**Gitea:**

```bash
docker compose stop gitea

# Restore entire Gitea directory
restic restore latest --include "/mnt/t7/docker/gitea" --target /

docker compose start gitea
```

---

## Restore from Cloud

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

# List cloud snapshots
restic snapshots

# Restore critical configs to temp location
restic restore latest --target /tmp/cloud-restore
```

---

## Important: Browse Backups Without Restoring

Mount a snapshot as read-only filesystem to browse without restoring:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# Mount latest snapshot
mkdir -p /tmp/restic-mount
restic mount /tmp/restic-mount &

# Browse (in another terminal)
ls /tmp/restic-mount/
# Structure: /tmp/restic-mount/snapshots/SNAPSHOT_ID/mnt/t7/

# Unmount
fusermount -u /tmp/restic-mount
```

---

## Space Management

Restic deduplication means multiple snapshots take minimal extra space.

**Monitor:**

```bash
df -h /mnt/backup
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo
restic stats  # Shows total repo size
```

**If HDD fills (>90%)**:

```bash
# Remove old snapshots manually
restic forget --keep-daily 3 --keep-weekly 2 --prune

# Check freed space
df -h /mnt/backup
```

---

## Troubleshooting

| Problem | Fix |
|---------|-----|
| "Failed to create lock" | Another restic process running; wait or kill it |
| "Permission denied" | Check: `chmod 600 ~/.restic-password` and `ls -la /mnt/backup/restic-repo` |
| Restore fails | Verify: `restic check` runs first; restore to /tmp to test |
| Cloud upload stalls | Check rclone: `rclone lsd gdrive-nas:` |
| "Repository not found" | Verify: `RESTIC_REPOSITORY` env var is set correctly |
