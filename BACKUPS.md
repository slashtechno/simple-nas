# Backup Strategy for Pi NAS

**Goal**: Incremental backups with restic to 500GB HDD (local) + Google Drive (cloud). Supports multiple versions without extra storage via deduplication.

---

## Setup Instructions

### 1. Install Restic

Install restic on your Raspberry Pi:

```bash
sudo apt install -y restic
restic version
```

### 2. Set Restic Password

Create a secure password file for restic:

```bash
openssl rand -base64 32 > ~/.restic-password
chmod 600 ~/.restic-password
cat ~/.restic-password  # Save this in a password manager
```

### 3. Initialize Repositories

#### Local Repository (HDD)

Set up the local repository on your external HDD:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

restic init
```

#### Cloud Repository (Google Drive)

1. Configure rclone on your laptop:

```bash
rclone config
# n) New remote
# Name: gdrive-nas
# Type: Google Drive
# Use defaults for client ID/secret
# Scope: 3 (Access to files created by rclone only)
# Authorize in browser
```

2. Copy the rclone configuration to your Pi:

```bash
scp ~/.config/rclone/rclone.conf pi@your-pi:~/.config/rclone/
```

3. Initialize the cloud repository:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

restic init
```

---

## Backup Scripts

### Daily Local Backup

**What**: Full backup of `/mnt/t7` to HDD with deduplication (7 daily + 4 weekly snapshots).

1. Run the script directly from the project (recommended). If you cloned the repo to `~/simple-nas`:

```bash
# Make executable and run in-place
chmod +x ~/simple-nas/scripts/backup-restic-local.sh
~/simple-nas/scripts/backup-restic-local.sh
```

Note: Root is not required — certain sensitive/inaccessible paths are excluded from the local backup.

### Weekly Cloud Backup

**What**: Selective paths (e.g., service dumps, configs) to Google Drive.

1. Run the cloud backup script directly from the project (recommended). If you cloned the repo to `~/simple-nas`:

```bash
# Make executable and run in-place
chmod +x ~/simple-nas/scripts/backup-restic-cloud.sh
~/simple-nas/scripts/backup-restic-cloud.sh
```

2. Define critical paths in `~/simple-nas/scripts/backup-paths.txt` or use the default file.

### Service-Aware Backup

Create consistent service dumps before snapshotting with restic:

```bash
# Immich DB dump + Gitea dump into /mnt/backup/service-dumps
~/simple-nas/scripts/backup-services.sh
```

What it does:
- Immich: `pg_dumpall` from the `immich_postgres` container → `immich-db-*.sql.gz`
- Gitea: `gitea dump` inside the `gitea` container → `gitea-dump-*.zip`
- Keeps the last 3 dumps of each type

This ensures restic captures a consistent snapshot of service state without relying on raw live data directories.

---

## Backup Overview

| **Backup Type** | **Includes** | **Notes** |
|------------------|--------------|-----------|
| **Cloud**       | Service dumps, configs | Smaller, critical items |
| **Local**       | Full `/mnt/t7` | Fast restore copy |

**Key Notes**:
- Use logical dumps for databases (e.g., `backup-services.sh`).
- Avoid raw database directories in cloud backups.

---

## Restore Instructions

### From Local Backup

Restore from the local repository:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# List all snapshots
restic snapshots

# Restore latest snapshot to original paths
restic restore latest --target /

# Restore specific file or directory
restic restore latest --include "/mnt/backup/service-dumps" --target /tmp/restore

# Restore specific snapshot by ID
restic restore <snapshot-id> --target /
```

### From Cloud Backup

Restore from the cloud repository:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"

# List cloud snapshots
restic snapshots

# Restore critical configs to a temporary location
restic restore latest --target /tmp/cloud-restore

# Restore specific file or directory
restic restore latest --include "/mnt/backup/service-dumps" --target /tmp/cloud-restore
```

### Restore Service Dumps

#### Option 1: Use Helper Script

Restore Immich or Gitea dumps using the helper script (run from the cloned repo):

```bash
~/simple-nas/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-YYYYMMDDTHHMMSS.sql.gz
~/simple-nas/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-YYYYMMDDTHHMMSS.zip
```

#### Option 2: Manual Restore

**Immich Database:**

```bash
# Find the dump in restic
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo
restic restore latest --include "/mnt/backup/service-dumps" --target /tmp/restore

# Restore the database
gunzip -c /tmp/restore/mnt/backup/service-dumps/immich-db-*.sql.gz | \
  docker exec -i immich_postgres psql -U postgres postgres
```

**Gitea:**

Best practice is to restore from a `gitea dump` ZIP with Gitea stopped (Docker rootless paths). Our helper script automates this:

- Stop `gitea` to ensure consistency
- Unpack and place files:
  - `data/conf/app.ini` → `/etc/gitea/app.ini`
  - `data/*` → `/var/lib/gitea/`
  - `repos/*` → `/var/lib/gitea/git/repositories/`
- `chown -R git:git /etc/gitea /var/lib/gitea`
- Regenerate hooks: `gitea admin regenerate hooks`
- Start `gitea`

Optional DB import (if `gitea-db.sql` is present):

```bash
# Inside the container, import to the DB configured in /etc/gitea/app.ini
docker exec -it gitea bash
# SQLite only:
sqlite3 /data/gitea/gitea.db < /tmp/restore/gitea-db.sql
```

---

## Schedule Backups with Cron

Cron does not expand shell constructs in the command field (no $(...), no ~, no unexpanded $VAR). Use absolute paths.

**IMPORTANT: replace `user` with your actual username in these examples.**

```cron
# Daily local backup @ 2 AM
0 2 * * * /bin/bash /home/user/simple-nas/scripts/backup-restic-local.sh >> /mnt/backup/logs/backup-cron.log 2>&1

# Weekly cloud backup @ Sunday 4 AM
0 4 * * 0 /bin/bash /home/user/simple-nas/scripts/backup-restic-cloud.sh >> /mnt/backup/logs/backup-cron.log 2>&1

# Weekly integrity check @ Wednesday 3 AM (advanced)
0 3 * * 3 /bin/bash -lc 'export RESTIC_PASSWORD_FILE=/home/user/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo && restic check' >> /mnt/backup/logs/restic-check.log 2>&1
```

- Quick checklist:
- Either: `chmod +x /home/user/simple-nas/scripts/backup-restic-local.sh` so the script is directly executable
- Or: keep the script without the +x bit and call it from cron with `/bin/bash /home/user/simple-nas/scripts/backup-restic-local.sh` (recommended for cron)
- Test-run as the target user
- Ensure /mnt/backup is mounted and RESTIC_PASSWORD_FILE exists
- Check /mnt/backup/logs for output

Note: `$USER` or `~` is fine inside scripts or files read at runtime (e.g., [`scripts/backup-paths.txt`](scripts/backup-paths.txt:1)), but not in the crontab command field.

---

## Additional Commands

### Check Status

Monitor the status of your backups:

```bash
# Set environment variables
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# List snapshots
restic snapshots

# Repository stats
restic stats

# Verify integrity
restic check
```

### Space Management

Free up space by removing old snapshots:

```bash
# Set environment variables
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# Remove old snapshots
restic forget --keep-daily 3 --keep-weekly 2 --prune
```

---

## Troubleshooting

| Problem                  | Fix                                      |
|--------------------------|------------------------------------------|
| "Failed to create lock"  | Wait or kill other restic processes      |
| "Permission denied"      | Check file permissions                  |
| Restore fails            | Verify repository integrity with `check` |
