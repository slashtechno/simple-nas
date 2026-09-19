# Backups

Backups are fully automated by the `backup` Ansible role — cron jobs are created on the Pi when you run `ansible-playbook site.yml`. You don't configure cron manually.

## What runs automatically

| Schedule | What it does |
|---|---|
| Daily @ 2 AM | Immich DB dump + Gitea dump, then full `/mnt/t7` → local HDD via restic |
| Sunday @ 4 AM | Same dumps, then critical paths → Google Drive via rclone + restic |
| Wednesday @ 3 AM | `restic check` — verifies local repo integrity |

Dumps land in `/mnt/backup/service-dumps/` (pruned to the last 3 of each type). Logs go to `/mnt/backup/logs/`, one dated file per run. Every restic call is wrapped in a timeout (`restic_command_timeout`, default 2h), so a stalled network/rclone pipe fails the cron run instead of hanging indefinitely while holding the repo lock.

---

## One-time setup: rclone (Google Drive)

Ansible sets up restic automatically, but rclone OAuth needs a browser. Run this on the Pi:

```bash
rclone config
# n) New remote → name: gdrive-nas → type: Google Drive
# scope: 3 (drive.file — rclone-created files only)
# For the auth step, rclone gives you a URL — open it on your Mac and paste the token back
```

The shared default Google OAuth client can hit `403 RATE_LIMIT_EXCEEDED` on a large
first backup (the cloud script already throttles via `restic_cloud_rclone_args` to
reduce this). If it keeps happening, get your own OAuth client: create a project +
OAuth client ID (Desktop app) in [Google Cloud Console](https://console.cloud.google.com/),
then `rclone config` → edit `gdrive-nas` → paste the client ID/secret (forces a one-time
re-auth in the browser).

---

## Web dashboard (read-only)

The `backup-status` role deploys a small read-only dashboard — job status, drive
mount state, and the snapshot list for both repos:

```
http://<your-pi-tailscale-host>:<backup_status_port>   # default port 8091
```

Tailscale-only, no login needed: the container gets a **read-only** mount of the
repo and password file, so it has no code path that can write to or delete a backup.
Every action opens the exact SSH command to copy and run yourself. Disable with
`backup_status_enabled: false`.

---

## Connecting

Every command below assumes you've SSH'd in and set these once per session:

```bash
ssh your-user@your-pi-ip

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (default below)
```

For the Google Drive repo instead: `export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"`

---

## Checking backup status

```bash
restic snapshots                                  # add --tag daily or --tag weekly to filter
tail -50 /mnt/backup/logs/backup-cron.log          # recent combined cron log

# Trigger a job manually (same scripts cron uses)
/bin/bash /opt/nas/scripts/backup-restic-local.sh    # or backup-restic-cloud.sh, restic-check.sh
```

---

## Inspecting a snapshot

Get an ID from `restic snapshots` (or the dashboard) — `latest` works in place of an ID too.

```bash
restic ls <snapshot-id>                                   # list everything it contains
restic diff <snapshot-id-1> <snapshot-id-2>                # what changed between two snapshots
restic find <pattern>                                      # which snapshot(s) contain a file (globs OK)
restic dump <snapshot-id> <path-in-snapshot> > recovered-file   # extract one file
```

---

## Restore: files

`--target` needs real free space — `/tmp` is tmpfs (RAM, a couple GB) and `/` is
often nearly full, so prefer `/mnt/t7` or `/mnt/backup`.

```bash
# Restore into a scratch path to inspect first (safe — doesn't touch originals)
restic restore latest --include /mnt/t7/files --target /mnt/t7/restore-scratch

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

**Restoring to another machine instead** (e.g. a USB drive on your Mac) skips the
Pi's disk entirely — stream the snapshot as a tar over the same SSH connection:

```bash
ssh your-user@your-pi-ip 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar
tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

No need for Tailscale's `tailcat` — restic only runs on the Pi, plain SSH already
does the job. Speed depends on `tailscale status` showing `direct` vs `relay`.
exFAT/FAT32 destinations lose Unix permissions/symlinks on extract — use APFS or
ext4 if that matters.

---

## Restore: Immich database

```bash
ls -lh /mnt/backup/service-dumps/immich-db-*.sql.gz
cd /opt/nas/immich && docker compose stop immich_server
/opt/nas/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-<timestamp>.sql.gz
docker compose start immich_server
```

---

## Restore: Gitea

```bash
ls -lh /mnt/backup/service-dumps/gitea-dump-*.zip
/opt/nas/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-<timestamp>.zip
# Gitea is stopped before restore and started after automatically
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
3. Restore Immich and Gitea databases from the service-dumps restored in step 2
