# Backups

Backups are fully automated by the `backup` Ansible role — cron jobs are created on the Pi when you run `ansible-playbook site.yml`. You don't configure cron manually.

## What runs automatically

| Schedule | What it does |
|---|---|
| Daily @ 2 AM | Immich DB dump + Gitea dump, then full `/mnt/t7` → local HDD via restic |
| Sunday @ 4 AM | Same dumps, then critical paths → Google Drive via rclone + restic |
| Wednesday @ 3 AM | `restic check` — verifies local repo integrity |

Database dumps land in `/mnt/backup/service-dumps/` and are pruned to the last 3 of each type. Logs go to `/mnt/backup/logs/`, one dated file per run.

Every restic call the scripts make is wrapped in a timeout (`restic_command_timeout`, default 2h) — a stalled network/rclone pipe becomes a normal failed cron run instead of hanging indefinitely while holding the repo lock.

---

## One-time setup: rclone (Google Drive)

Ansible sets up restic automatically, but rclone OAuth needs a browser. Run this on the Pi:

```bash
rclone config
# n) New remote → name: gdrive-nas → type: Google Drive
# scope: 3 (drive.file — rclone-created files only)
# For the auth step, rclone gives you a URL — open it on your Mac and paste the token back
```

By default this uses rclone's shared Google OAuth client, whose request quota is
split across every rclone user worldwide — the cloud backup script already
throttles requests (`restic_cloud_rclone_args`, `--tpslimit=10`) to stay under
it, but a large first backup can still hit `403 RATE_LIMIT_EXCEEDED` from
Google Drive. If that happens, get your own private quota instead:

1. In [Google Cloud Console](https://console.cloud.google.com/), create a
   project, enable the **Google Drive API**, then create an **OAuth client ID**
   (type: Desktop app). Note the Client ID and Client Secret.
2. Re-edit the existing remote (not a new one) on the Pi:
   ```bash
   rclone config
   # e) Edit existing remote → gdrive-nas
   # "Google Application Client Id" → paste your client ID
   # "Client Secret" → paste your client secret
   # leave scope/other answers as they were
   ```
3. Changing the OAuth client forces a new consent flow — same browser/paste-token
   step as the original setup, just once.

---

## Web dashboard (read-only)

The `backup-status` Ansible role deploys a small read-only dashboard — last-run
status for each job, whether the backup drive is mounted, and the snapshot list
for both repos. It's Tailscale-only (no `cloudflared_ingress` entry) and needs no
login: the container only ever gets a **read-only** bind mount of the repo and
password file, so there's no code path in it that could write to or delete a
backup.

```
http://<your-pi-tailscale-host>:<backup_status_port>
```

(`backup_status_port` defaults to `8091` — see `group_vars/nas/vars.yml`.)

Every command on the dashboard — run a job, preview a prune, inspect/restore/delete
a snapshot — only ever opens with the exact SSH command to copy and run yourself,
matching the commands documented below. Disable it entirely with `backup_status_enabled: false`.

---

## Connecting

Every command below assumes you've SSH'd in and set these once per session:

```bash
ssh your-user@your-pi-ip

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (default below)
```

For the Google Drive repo instead of local, use this `RESTIC_REPOSITORY` instead:
```bash
export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"
```

---

## Checking backup status

```bash
# List snapshots (add --tag daily or --tag weekly to filter)
restic snapshots

# Recent combined cron log
tail -50 /mnt/backup/logs/backup-cron.log

# Trigger a backup manually right now (same script cron uses)
/bin/bash /opt/nas/scripts/backup-restic-local.sh    # or backup-restic-cloud.sh, restic-check.sh
```

---

## Inspecting a snapshot

Get an ID from `restic snapshots` above (or the dashboard) — every restic
command below accepts `latest` in place of an ID too.

```bash
# List every file/directory the snapshot contains
restic ls <snapshot-id>

# See what changed between two snapshots
restic diff <snapshot-id-1> <snapshot-id-2>

# Find which snapshot(s) contain a file — glob patterns work (*.jpg, etc.)
restic find <pattern>

# Extract a single file without restoring the whole snapshot
restic dump <snapshot-id> <path-in-snapshot> > recovered-file
```

---

## Restore: files

`--target` needs somewhere with actual free space — `/tmp` is tmpfs (RAM-backed,
only a couple GB) and `/` is often nearly full, so prefer a spot on `/mnt/t7` or
`/mnt/backup` instead (check with `df -h` first if unsure).

```bash
# Restore into a scratch path to inspect first (safe — doesn't touch originals)
restic restore latest --include /mnt/t7/files --target /mnt/t7/restore-scratch
ls /mnt/t7/restore-scratch/mnt/t7/files

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

### Restore straight to another machine (skip the Pi's disk entirely)

If you'd rather restore onto a USB/external drive on your Mac (or any other
machine) than find space on the Pi, stream the snapshot as a tar file over the
same SSH connection instead — nothing is written to the Pi at any point:

```bash
ssh your-user@your-pi-ip 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar

tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

This runs entirely over your existing SSH setup — no need for Tailscale's
`tailcat` or installing restic locally, since restic only ever needs to run on
the Pi (where the password file already lives) and the data just streams
through the SSH pipe to wherever you redirect it. Speed depends on whether
Tailscale gets a direct connection to the Pi or falls back to a relay — check
with `tailscale status`; `active; direct ...` is fast (LAN speed), anything
saying `relay` will be much slower.

One caveat: if the destination drive is exFAT or FAT32 (common for drives
formatted for Windows/cross-platform use), Unix permissions and symlinks in
the tar won't survive extraction — fine for just recovering file contents,
but format the drive as APFS (or ext4, if you'll plug it into the Pi later)
if you need an exact restore.

---

## Restore: Immich database

Stop Immich first, restore the dump, then restart:

```bash
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
