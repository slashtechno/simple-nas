# Backups

`just deploy backup` (from `ansible/`) installs the scripts and cron jobs on the NAS. Nothing to set up by hand.

On another host (`servers_general`), set `backup_enabled: true` in its `host_vars` and give one drive in `drives` the `backup` role. It then backs up the user's home daily. Add other paths (such as `/opt/stacks`) in `restic_local_paths`; the job runs as the ansible user, so files only root can read are skipped and the log says "unreadable source files". The Sunday cloud copy runs only with `backup_cloud_enabled: true` and a `restic_cloud_repository` of that host's own. The dashboard (`backup-status`) is NAS only.

restic keeps its cache in `restic_cache_dir` (`<fast_drive>/restic-cache`). It is safe to delete: that only costs speed.

## What runs automatically

| Schedule | What it does |
|---|---|
| Daily 02:00 | Immich and Gitea dumps, then the local backup (see [What is backed up where](#what-is-backed-up-where)) to the backup drive with restic |
| Sunday 04:00 | Same dumps, then the dumps and cloud paths to the cloud repository |
| Wednesday 03:00 | `restic check` of the local repo (the cloud repo is checked by hand, see below) |

- Dumps: `<backup_drive>/service-dumps/` (`service_dumps_dir`), last 3 of each type kept.
- Logs: `<backup_drive>/logs/` (`backup_logs_dir`), one file per job per day, plus `backup-cron.log`.
- Every restic call has a timeout (`restic_command_timeout`, default 2h), so a stalled network pipe fails the run instead of holding the repo lock.

Paths below use `/mnt/backup` for `backup_drive` and `/mnt/t7` for the fast and primary drive; use your `drives` mounts (in `host_vars/<host>/vars.yml`).

## What is backed up where

| Data | Local (daily, backup drive) | Cloud (Sunday) |
|---|---|---|
| Photos, Copyparty files (`primary_drive`) | Yes | No |
| Service data under `fast_drive/docker` (Gitea, pics, Homebridge, Garage, Crafty, Copyparty config) | Yes | Only Copyparty config |
| Immich database | Dump only (raw Postgres dir excluded) | Dump only |
| Gitea database and repos | Dump, plus raw data (SSH host keys excluded) | Dump only |
| Compose files and scripts (`/opt/nas`), rclone config | No | Yes |
| Restic password | No | Also copied to the cloud, but that copy is useless alone: you need the password to open the repo that holds it. The real copy is `vault_restic_password` in `group_vars/all/vault.yml`, and the vault password is in Bitwarden (see Disaster recovery). |

Where each is declared:
- Local paths and excludes: `restic_local_paths` and `restic_local_excludes` in `ansible/group_vars/all/vars.yml` (default on the NAS: `primary_drive` and `fast_drive`). The script adds the dumps directory itself. Default excludes (caches, `lost+found`, Copyparty's thumbnail cache) are in `roles/backup/templates/restic-excludes-local.txt.j2`; your extras are added after them.
- Cloud paths and excludes: `restic_cloud_extra_paths` and `restic_cloud_excludes` in `vars.yml` (defaults in `restic-excludes-cloud.txt.j2`). The fixed cloud paths (`/opt/nas`, rclone config, restic password file, Copyparty config) are in `ansible/roles/backup/templates/backup-paths.txt.j2`.
- Dumps: one script per service with a live database, installed into `service_dump_scripts_dir` (`/opt/nas/scripts/dump.d/`) by that service's role: `roles/immich/files/dump.sh`, `roles/gitea/files/dump.sh`. `backup-services.sh` runs them all before each backup and keeps the last 3 files named `<script name>-*`. Everything else is plain files.

Caveats:
- Crafty worlds are copied while the server runs, so a world written mid-backup can be inconsistent. Crafty's own `backups/` archives are excluded from the local backup (`restic-excludes-local.txt.j2`; they dedupe badly), so they exist only on the fast drive. To keep them, add `"!{{ crafty_data_dir }}/backups"` to `restic_local_excludes`, or add `{{ crafty_data_dir }}/backups` to `restic_cloud_extra_paths` for offsite. `teardown.yml -e remove_data=true` deletes all of `crafty_data_dir`, archives included; only the local restic copy of `servers/` survives, and nothing offsite.
- `restic forget` groups snapshots by host and paths, so changing `restic_local_paths` starts a new group. The old group stops growing but keeps its last snapshots until you remove them by hand (`restic forget --path <old path> --prune`). Excludes never split a group, so tune with `restic_local_excludes` first. Exclude lines use restic's syntax, not gitignore's: `**` for any depth, and a leading `!` re-includes something an earlier line excluded (needs a restic release that supports `!`; check `restic version`).
- To add a path to the cloud backup, put it in `restic_cloud_extra_paths`. Adding is safe. Removing one leaves its snapshots until you forget them by hand.
- To give a new service a database dump, add `files/dump.sh` to its role and install it into `service_dump_scripts_dir` as `<service>.sh` (copy the Gitea role). Its dump files must start with `<service>-`. `teardown_service.yml` removes the script again.

### Checking the cloud repo (manual)

No schedule checks the cloud repo (a full check reads all of it over the network). Run it now and then, on the NAS:

```bash
sudo -E bash -c 'export RESTIC_PASSWORD_FILE=<restic_password_file> RESTIC_REPOSITORY=<restic_cloud_repository>; restic -o rclone.args="serve restic --stdio --tpslimit=10" check'
```

Add `--read-data-subset=5%` to also read a sample of the stored data.

---

## Offsite repository (`restic_cloud_repository`)

The URL scheme picks the backend. The deploy runs `restic init` on it and **fails if that fails** (no rclone remote, bad credentials, unreachable server). An existing repository is left alone.

### Google Drive (default)

Google Drive goes through rclone. Its login needs a browser, so the token comes from the vault:

1. On your Mac (needs `rclone`): `rclone authorize "drive" --drive-scope drive.file`. Sign in; it prints a JSON token.
2. Put that JSON in `group_vars/all/vault.yml` as `vault_rclone_gdrive_token` (single-quoted).
3. `just deploy backup`. Ansible writes `~/.config/rclone/rclone.conf` with a `gdrive-nas` remote **only if the file does not exist**, because rclone writes refreshed tokens back into it.

To replace a broken login, delete `~/.config/rclone/rclone.conf` on the host and deploy again, or run `rclone config reconnect gdrive-nas:` there.

- The remote uses rclone's default Google OAuth client, shared by all rclone users, which can return `403 RATE_LIMIT_EXCEEDED` on a large first backup. `restic_cloud_rclone_args` (`--tpslimit=10`) throttles requests. To use your own client instead: `rclone config`, edit `gdrive-nas`, set client ID and secret.
- Google expires the refresh token after 7 days for an app in "Testing" status, and after 6 months unused. If cloud backups stop with an auth error, redo step 1 and replace `rclone.conf`.

### SFTP (if you want it later)

Set `restic_cloud_repository: "sftp:backup@host:/srv/restic"`. restic uses the host's SSH client. Set up by hand, as the NAS user that runs cron: a key without a passphrase in `~/.ssh`, and the server's host key in `~/.ssh/known_hosts` (`ssh-keyscan host >> ~/.ssh/known_hosts`, checked against the fingerprint). Without the host key the cron run waits on a prompt and fails. Ansible does not manage this. The rclone-specific throttle (`restic_cloud_rclone_args`) does not apply.

---

## Web dashboard (read-only)

The `backup-status` role deploys a read-only dashboard with job status, drive mount state and the snapshot list for both repos:

```
http://<your-pi-tailscale-host>:<backup_status_port>   # default port 8091
```

- Reachable from the LAN and the tailnet, with no login.
- The container mounts the backup drive and password file read-only, so it cannot write to or delete a backup.
- Each action shows the exact SSH command to copy and run yourself.
- Disable with `backup_status_enabled: false`; change the port with `backup_status_port`.

---

## Connecting

Every command below assumes you've SSH'd in and set these once per session:

```bash
ssh your-user@your-nas-ip

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (restic_repo_path)
```

For the Google Drive repo instead: `export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"`

---

## Checking backup status

A failed job is written to the system log (`journalctl -t nas-backup`) and, with `ntfy_alert_url` set, sent to your phone ([services.md](./services.md#ntfy-failure-alerts)).

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

`--target` needs real free space. `/tmp` is in RAM and `/` is small, so use a path on a data drive such as `/mnt/t7` or `/mnt/backup`.

```bash
# Restore into a scratch path to inspect first (safe — doesn't touch originals)
restic restore latest --include /mnt/t7/files --target /mnt/t7/restore-scratch

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

**To another machine** (for example a USB drive on your Mac), stream the snapshot as a tar over SSH:

```bash
ssh your-user@your-nas-ip 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar
tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

Speed over Tailscale depends on `tailscale status` showing `direct` rather than `relay`. exFAT/FAT32 destinations lose Unix permissions and symlinks on extract; use APFS or ext4 if that matters.

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

`nofail` in `fstab` only covers mounting at boot. A drive that drops out later is not remounted by it, and `/mnt/backup` then becomes a plain directory on the root filesystem. Two guards cover this:

1. The backup scripts and the `restic check` job run `mountpoint -q /mnt/backup` first. If it is not mounted they exit without writing anything. The cron line logs the failure to `journalctl -t nas-backup`.
2. `roles/storage/files/99-nas-drive-remount.rules` runs `mount -a` (through `nas-drive-remount.service`) whenever a filesystem appears, so a reconnected drive remounts within seconds.

Check with `mountpoint /mnt/backup`, `journalctl -t nas-backup` and `systemctl status nas-drive-remount.service`. If backups fail because the drive keeps dropping out, `vcgencmd get_throttled` and `dmesg | grep -iE 'sdb|voltage'` show whether the power supply, cable or hub is at fault.

## Disaster recovery (both drives fail)

1. Re-flash Pi OS, then run `just deploy`. This needs the `vault.yml` files (`group_vars/all/` and `group_vars/nas/`) and their vault password; `group_vars/all/vault.yml` holds `vault_restic_password` and exist only on your own machine. Without them neither restic repo can be opened, so keep a copy of both somewhere that is not the Pi.
2. Pull from the cloud repo. It holds one snapshot group per path, and `latest` restores only one snapshot, so restore each:
   ```bash
   export RESTIC_PASSWORD_FILE=~/.restic-password
   export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"   # restic_cloud_repository
   restic snapshots --group-by path
   restic restore <snapshot-id> --target /      # once per group
   ```
3. Restore the Immich and Gitea databases from the dumps restored in step 2 (see Restore: Immich database and Restore: Gitea above, using the restored `service-dumps` folder).
