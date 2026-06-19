# Backups

Backups are fully automated by the `backup` Ansible role — cron jobs are created on the Pi when you run `ansible-playbook site.yml`. You don't configure cron manually.

## What runs automatically

| Schedule | What it does |
|---|---|
| Daily @ 2 AM | Immich DB dump + Gitea dump, then full `/mnt/t7` → local HDD via restic |
| Sunday @ 4 AM | Same dumps, then critical paths → Google Drive via rclone + restic |
| Wednesday @ 3 AM | `restic check` — verifies local repo integrity |

Database dumps land in `/mnt/backup/service-dumps/` and are pruned to the last 3 of each type. Logs go to `/mnt/backup/logs/`.

---

## One-time setup: rclone (Google Drive)

Ansible sets up restic automatically, but rclone OAuth needs a browser. Run this on the Pi:

```bash
rclone config
# n) New remote → name: gdrive-nas → type: Google Drive
# scope: 3 (drive.file — rclone-created files only)
# For the auth step, rclone gives you a URL — open it on your Mac and paste the token back
```

---

## Checking backup status

SSH into the Pi:

```bash
ssh pi@your-pi-ip

# See what snapshots exist
RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo \
  restic snapshots

# Check recent log
tail -50 /mnt/backup/logs/backup-cron.log

# Trigger a backup manually right now (same script cron uses)
/bin/bash /opt/nas/scripts/backup-restic-local.sh
```

---

## Restore: files

Restore any file or directory from any restic snapshot:

```bash
ssh pi@your-pi-ip

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# List snapshots — each has an ID like `a1b2c3d4`
restic snapshots

# Restore a single directory to inspect it first (safe)
restic restore latest --include /mnt/t7/files --target /tmp/restore
ls /tmp/restore/mnt/t7/files

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

For Google Drive snapshots, swap the repository:
```bash
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"
```

---

## Restore: Immich database

Stop Immich first, restore the dump, then restart:

```bash
ssh pi@your-pi-ip

# Find the dump you want
ls -lh /mnt/backup/service-dumps/immich-db-*.sql.gz

# Restore (script stops/restarts nothing automatically — Immich keeps running,
# but you should stop it first for a clean restore)
cd /opt/nas/immich && docker compose stop immich_server
/opt/nas/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-<timestamp>.sql.gz
docker compose start immich_server
```

---

## Restore: Gitea

The restore script stops Gitea, replaces all data, then restarts it:

```bash
ssh pi@your-pi-ip

ls -lh /mnt/backup/service-dumps/gitea-dump-*.zip

/opt/nas/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-<timestamp>.zip
# Gitea is automatically stopped before restore and started after
```

---

## Disaster recovery (both drives fail)

1. Re-flash Pi OS, re-run `ansible-playbook site.yml`
2. Pull from Google Drive:
   ```bash
   export RESTIC_PASSWORD_FILE=~/.restic-password
   export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"
   restic restore latest --target /
   ```
3. Restore Immich and Gitea databases from the service-dumps that were restored in step 2
