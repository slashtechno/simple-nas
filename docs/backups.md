# Backups

Backups are fully automated by the `backup` Ansible role — cron jobs are created on the Pi when you run `ansible-playbook site.yml`. You don't configure cron manually.

All restic invocations use a local cache on the fast drive (`RESTIC_CACHE_DIR`, via the drive-role map): snapshot/index reads hit the SSD instead of the backup drive or Google Drive round-trips. The cache is disposable — deleting it only costs speed, never data.

## What runs automatically

| Schedule | What it does |
|---|---|
| Daily @ 2 AM | Immich DB dump + Gitea dump, then the local backup (see [What is backed up where](#what-is-backed-up-where)) → HDD via restic |
| Sunday @ 4 AM | Same dumps, then the cloud paths → Google Drive via rclone + restic |
| Wednesday @ 3 AM | `restic check` — verifies local repo integrity (the cloud repo is checked by hand, see below) |

Dumps land in `/mnt/backup/service-dumps/` (pruned to the last 3 of each type). Logs go to `/mnt/backup/logs/`, one dated file per run. Every restic call is wrapped in a timeout (`restic_command_timeout`, default 2h), so a stalled network/rclone pipe fails the cron run instead of hanging indefinitely while holding the repo lock.

## What is backed up where

| Data | Local (daily, HDD) | Cloud (Sunday, Google Drive) |
|---|---|---|
| Photos, Copyparty files (`main_drive`) | Yes | No |
| Service data under `fast_drive/docker` (Gitea, pics, Homebridge, Garage, Crafty, Copyparty config) | Yes | Only Copyparty config |
| Immich database | Dump only (raw Postgres dir excluded) | Dump only |
| Gitea database and repos | Dump, plus raw data (SSH host keys excluded) | Dump only |
| Compose files and scripts (`/opt/nas`), rclone config | No | Yes |
| Restic password | No | Also copied to the cloud, but that copy is useless alone: you need the password to open the repo that holds it. The real copy is `vault_restic_password` in `vault.yml`, and the vault password is in Bitwarden (see Disaster recovery). |

Where each is declared:
- Local paths and excludes: `restic_local_paths` and `restic_local_excludes` in `ansible/group_vars/nas/vars.yml`. The script adds the dumps directory itself. Default excludes (caches, `lost+found`, Copyparty's thumbnail cache) are in `roles/backup/templates/restic-excludes-local.txt.j2`; your extras are added after them.
- Cloud paths and excludes: `restic_cloud_extra_paths` and `restic_cloud_excludes` in `vars.yml` (defaults in `restic-excludes-cloud.txt.j2`). The fixed cloud paths (`/opt/nas`, rclone config, restic password file, Copyparty config) are in `ansible/roles/backup/templates/backup-paths.txt.j2`.
- Dumps: one script per service with a live database, installed into `service_dump_scripts_dir` (`/opt/nas/scripts/dump.d/`) by that service's role: `roles/immich/files/dump.sh`, `roles/gitea/files/dump.sh`. `backup-services.sh` runs them all before each backup and keeps the last 3 files named `<script name>-*`. Everything else is plain files.

Caveats:
- Crafty worlds are copied while the server runs, so a world written mid-backup can be inconsistent. Crafty's own `backups/` archives are excluded from the local backup by default (`restic-excludes-local.txt.j2`), because they dedupe badly and would grow the repo. So the archives exist only on the fast drive, in neither backup. To keep them, add `"!{{ crafty_data_dir }}/backups"` to `restic_local_excludes`, or add `{{ crafty_data_dir }}/backups` to `restic_cloud_extra_paths` for offsite. Note that `teardown.yml -e remove_data=true` deletes all of `crafty_data_dir`, archives included; by default only the local restic copy of `servers/` would survive, with nothing offsite.
- `restic forget` groups snapshots by host and paths, so changing `restic_local_paths` starts a new group. The old group stops growing but keeps its last snapshots until you remove them by hand (`restic forget --path <old path> --prune`). Excludes never split a group, so tune with `restic_local_excludes` first. Exclude lines use restic's syntax, not gitignore's: `**` for any depth, and a leading `!` re-includes something an earlier line excluded (check `restic version` on the Pi first: older releases may not support `!`).
- To add a path to the cloud backup, put it in `restic_cloud_extra_paths`. Adding is safe. Removing one leaves its snapshots until you forget them by hand.
- To give a new service a database dump, add `files/dump.sh` to its role and install it into `service_dump_scripts_dir` as `<service>.sh` (copy the Gitea role). Its dump files must start with `<service>-`. `teardown_service.yml` removes the script again.

### Checking the cloud repo (manual)

The cloud repository is not checked on a schedule: a full check reads the whole repo over the network. Run it yourself now and then, on the Pi:

```bash
sudo -E bash -c 'export RESTIC_PASSWORD_FILE=<restic_password_file> RESTIC_REPOSITORY=<restic_cloud_repository>; restic -o rclone.args="serve restic --stdio --tpslimit=10" check'
```

Add `--read-data-subset=5%` to also read a sample of the stored data.

---

## Offsite repository (`restic_cloud_repository`)

The URL scheme picks the backend. The deploy runs `restic init` on it and **fails if that fails** (no rclone remote, bad credentials, unreachable server), so a cloud backup that could never run is noticed at deploy time. An existing repository is left alone.

### Google Drive (default)

Google Drive goes through rclone, whose login needs a browser. The token lives in the vault, so a new host needs no manual rclone setup:

1. On your Mac (needs `rclone`): `rclone authorize "drive" --drive-scope drive.file`. Sign in; it prints a JSON token.
2. Put that JSON in `vault.yml` as `vault_rclone_gdrive_token` (single-quoted).
3. `just deploy backup`. Ansible writes `~/.config/rclone/rclone.conf` with a `gdrive-nas` remote **only if the file does not exist**. rclone writes refreshed tokens back into that file, so overwriting it on every deploy would replace a fresh token with the old one.

To replace a broken login, delete `~/.config/rclone/rclone.conf` on the host and deploy again, or run `rclone config reconnect gdrive-nas:` there.

The remote uses rclone's default Google OAuth client, which is shared with every rclone user and can hit `403 RATE_LIMIT_EXCEEDED` on a large first backup. The cloud script throttles with `restic_cloud_rclone_args` for that reason. A custom OAuth client is not used (owner decision); if the throttle is not enough, `rclone config` → edit `gdrive-nas` → client ID/secret is the way to add one. Google also expires the refresh token after 7 days for an app in "Testing" status, and after 6 months unused; if cloud backups stop with an auth error, re-run step 1 and replace `rclone.conf`.

### SFTP (if you want it later)

Set `restic_cloud_repository: "sftp:backup@host:/srv/restic"`. restic uses the host's SSH client, so on the NAS user (the one running cron) set up key login to that server by hand: a key without a passphrase in `~/.ssh`, and the server's host key in `~/.ssh/known_hosts` (`ssh-keyscan host >> ~/.ssh/known_hosts`, checked against the fingerprint). Without the host key the cron run waits on a prompt and fails. Nothing in the repo manages this yet; it is added when there is a real SFTP target.

---

## Web dashboard (read-only)

The `backup-status` role deploys a small read-only dashboard — job status, drive mount state, and the snapshot list for both repos:

```
http://<your-pi-tailscale-host>:<backup_status_port>   # default port 8091
```

Reachable from the LAN and the tailnet, with no login (the port is published on the Pi): the container gets a **read-only** mount of the repo and password file, so it has no code path that can write to or delete a backup. Every action opens the exact SSH command to copy and run yourself. Disable with `backup_status_enabled: false`.

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

`--target` needs real free space — `/tmp` is tmpfs (RAM, a couple GB) and `/` is often nearly full, so prefer `/mnt/t7` or `/mnt/backup`.

```bash
# Restore into a scratch path to inspect first (safe — doesn't touch originals)
restic restore latest --include /mnt/t7/files --target /mnt/t7/restore-scratch

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

**Restoring to another machine instead** (e.g. a USB drive on your Mac) skips the Pi's disk entirely — stream the snapshot as a tar over the same SSH connection:

```bash
ssh your-user@your-pi-ip 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar
tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

No need for Tailscale's `tailcat` — restic only runs on the Pi, plain SSH already does the job. Speed depends on `tailscale status` showing `direct` vs `relay`. exFAT/FAT32 destinations lose Unix permissions/symlinks on extract — use APFS or ext4 if that matters.

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

## If the backup drive disconnects

`nofail` in `fstab` only covers mounting at boot. A drive that drops out later is not remounted, so `/mnt/backup` silently becomes a small plain directory on the root filesystem. This happened once, caused by a Pi-side USB brown-out rather than the drive. If it recurs, run `vcgencmd get_throttled` and `dmesg | grep -iE 'sdb|voltage'`; undervoltage points at the PSU, cable or hub.

Two guards cover it:

1. The backup scripts and the `restic check` job run `mountpoint -q /mnt/backup` first. On failure they log to `journalctl -t nas-backup` and write nothing to root.
2. `roles/storage/files/99-nas-drive-remount.rules` runs `mount -a` through a oneshot systemd service whenever a filesystem reappears, so a reconnected drive remounts within seconds.

Check with `mountpoint /mnt/backup`, `journalctl -t nas-backup` and `systemctl status nas-drive-remount.service`.

## Disaster recovery (both drives fail)

1. Re-flash Pi OS, re-run `ansible-playbook site.yml`. This needs `vault.yml` and its vault password, which hold `vault_restic_password` and exist only on your own machine. Without them neither restic repo can be opened, so keep a copy of both somewhere that is not the Pi.
2. Pull from Google Drive:
   ```bash
   export RESTIC_PASSWORD_FILE=~/.restic-password
   export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"
   restic restore latest --target /
   ```
3. Restore Immich and Gitea databases from the service-dumps restored in step 2
