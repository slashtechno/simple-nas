# Backups

Backups use [restic](https://restic.readthedocs.io/). The `backup` role installs restic, the scripts and the cron jobs. Deploy it from `ansible/` with `just deploy backup`. Every setting named below, with its default, is in `ansible/roles/backup/defaults/main.yml` (rules, timeout, cache, alerts) or `ansible/group_vars/all/defaults.yml` (repositories, retention, logs).

## Switching backups on

Each host chooses its backups with two flags in `host_vars/<host>/vars.yml`:

- `backup_local_enabled: true` backs up daily to a drive and checks that repository weekly. The host needs a `drives` entry with the `backup` role and a `uuid` ([storage.md](./storage.md)). The deploy stops with a message if it has none.
- `backup_cloud_enabled: true` backs up weekly to `restic_cloud_repository`. Set that per host in `host_vars/<host>/vars.yml`, with a path no other host uses: hosts that share a repository prune each other's snapshots. The deploy stops with a message if it is empty.
- A host can set either flag or both. The restic password comes from `vault_restic_password` in `group_vars/all/vault.yml`.
- The web dashboard (`backup_status_enabled`) reads the local repository, so it needs `backup_local_enabled`.

A cloud-only host (`backup_cloud_enabled` without `backup_local_enabled`):

- It has no automatic integrity check. The weekly `restic check` job exists only for the local repository, and the cloud check is manual ([Checking the cloud repo](#checking-the-cloud-repo-manual)).
- It uploads its whole data set every week. With no local backup, the default `restic_cloud_rules` include everything the local rules would cover. restic sends only data that changed, but it reads all of it each run.
- Its logs and database dumps are kept on the root drive in `/var/lib/backup-work`.

The backups run as the ansible user. Files only root can read (`/etc`, data owned by a container's user) are skipped, and the log says "unreadable source files". The run still counts as done. A stack whose containers write as root needs its data dumped or its owner changed.

restic keeps its cache in `restic_cache_dir`. It is safe to delete: that only costs speed.

## What runs automatically

| Cron job | Schedule | What it does |
|---|---|---|
| `backup-local` | Daily 02:00 | Runs the service dumps, then backs up to the local repository |
| `backup-cloud` | Sunday 04:00 | Runs the service dumps, then backs up to the cloud repository |
| `restic-check` | Wednesday 03:00 | Runs `restic check` on the local repository |

- Jobs only exist for the flags that are on. Turning a flag off removes its jobs and scripts on the next deploy.
- Dumps: `service_dumps_dir`, the last 3 of each type kept.
- Logs: `backup_logs_dir`, one file per job per day, plus `backup-cron.log`.
- With a local backup both live on the backup drive (`<backup drive>/service-dumps`, `<backup drive>/logs`). Without one they live in `/var/lib/backup-work`.
- Every restic call has a timeout (`restic_command_timeout`), so a stalled network pipe fails the run instead of holding the repository lock.
- Snapshot retention is `restic_local_retention` and `restic_cloud_retention`.

Paths below use `/mnt/backup` for the backup drive and `/mnt/t7` for the fast and primary drive. Use the mounts from your `drives`.

## What is backed up where

What a host backs up is set by two rules lists: `restic_local_rules` for the daily backup and `restic_cloud_rules` for the weekly one. Their defaults are in `ansible/roles/backup/defaults/main.yml`. With the defaults on a NAS:

| Data | Local (daily, backup drive) | Cloud (Sunday) |
|---|---|---|
| Files on the `primary` and `fast` drives (photos, Copyparty files, service data) | Yes | Only with `backup_local_enabled` off, because then the cloud rules include the local ones |
| Copyparty config (`copyparty_config_dir`) | Yes | Yes |
| Compose files, scripts and the credentials written into them (`services_dir`) | No | Yes |
| Immich database | Dump only (the raw Postgres directory is excluded) | Dump only |
| Gitea database and repositories | Dump, plus the raw data (SSH host keys excluded) | Dump only |
| Restic password | No | No |

- The restic password is not in any backup. Its only copy is `vault_restic_password` in `group_vars/all/vault.yml`, and the vault password is in Bitwarden ([Disaster recovery](#disaster-recovery-all-drives-fail), step 1).
- Both repositories always include `service_dumps_dir` as well.
- Always excluded: `restic_cache_dir`, `**/.cache` folders, `lost+found` on the primary drive, Gitea's SSH host keys, Immich's raw database directory, Copyparty's `hist` directory and the `copyparty` folder inside its config directory, and Crafty's own `backups/` archives. The lists are `roles/backup/templates/restic-excludes-local.txt.j2`, `restic-excludes-cloud.txt.j2` and `restic-excludes-services.txt.j2`.
- Dumps: one script per service with a live database, installed into `service_dump_scripts_dir` by that service's role (`roles/immich/files/dump.sh`, `roles/gitea/files/dump.sh`). `backup-services.sh` runs them all before each backup and keeps the last 3 files named `<script name>-*`. Everything else is plain files.

## Choosing what is backed up

Each rules list holds one rule per line. A line is one of:

- `/path`: an absolute path to back up.
- `- pattern`: leave this out. The dash and the space are part of the line. The pattern uses restic's syntax, not gitignore's ([restic docs](https://restic.readthedocs.io/en/stable/040_backup.html)): `**` matches any number of folders.
- `- !pattern`: put back something an earlier `- ` line left out.

`- ` lines run after the built-in exclude lists, so a `- !` line can also undo a default. The cloud list works the same way, and its `- ` lines apply to every path in it. The deploy fails if a line is none of the three.

Worked example, in `host_vars/<host>/vars.yml`. Add a folder, leave out a kind of file, then keep one file of that kind:

```yaml
restic_local_rules:
  - /mnt/t7                              # the drive to back up
  - /home/user/notes                     # add a folder outside it
  - "- **/*.iso"                         # leave out every .iso file
  - "- !/mnt/t7/downloads/keep.iso"      # but keep this one
```

- Quote the `- ` lines in YAML, as above.
- Setting a list replaces its default. Start from the default paths in `ansible/roles/backup/defaults/main.yml` and add to them, or the default drives drop out.
- A `- !` line cannot bring back a file inside a folder that a `- ` line left out as a whole. To keep one file out of an excluded folder, exclude the folder's other contents by pattern instead.
- `- !` needs restic 0.13.0 or newer (Debian bookworm ships 0.14).
- After editing, run `just deploy backup`.

Consequences of changing the lists:

- restic groups snapshots by host and paths. Adding or removing a `/path` line starts a new snapshot group. The old group stops growing but keeps its last snapshots until you remove them by hand: `restic snapshots --group-by host,paths`, then `restic forget <snapshot-id> --prune`.
- Adding or removing a `- ` line never splits a group, so tune with those first.
- In the cloud repository each path is its own group.
- To keep Crafty's `backups/` archives, add `- !<crafty_data_dir>/backups` (the full path) to the list. Crafty worlds are copied while the server runs, so a world written mid-backup can be inconsistent.
- `teardown.yml -e remove_data=true` deletes the whole of `crafty_data_dir`, archives included.

To give a new service a database dump, add `files/dump.sh` to its role and install it into `service_dump_scripts_dir` as `<service>.sh` (copy the Gitea role). Its dump files must start with `<service>-`. `teardown_service.yml` removes the script again.

### Checking the cloud repo (manual)

No schedule checks the cloud repository: a full check reads all of it over the network. Run it now and then, as the ansible user on the host:

```bash
export RESTIC_PASSWORD_FILE=<restic_password_file> RESTIC_REPOSITORY=<restic_cloud_repository>
restic -o rclone.args="serve restic --stdio --tpslimit=10" check
```

Add `--read-data-subset=5%` to also read a sample of the stored data. For an SFTP repository leave out the `-o rclone.args` option.

---

## Offsite repository (`restic_cloud_repository`)

The URL scheme picks the backend. The deploy runs `restic init` on it and fails if that fails (no rclone remote, bad credentials, unreachable server). An existing repository is left alone.

### Google Drive

Google Drive goes through rclone, which the deploy installs for `rclone:` repositories. Its login needs a browser, so the token comes from the vault:

1. On your Mac (needs `rclone`): `rclone authorize "drive" --drive-scope drive.file`. Sign in; it prints a JSON token.
2. Put that JSON in `group_vars/all/vault.yml` as `vault_rclone_gdrive_token` (single-quoted).
3. `just deploy backup`. Ansible writes `~/.config/rclone/rclone.conf` with a `gdrive-nas` remote only if the file does not exist, because rclone writes refreshed tokens back into it.

To replace a broken login, delete `~/.config/rclone/rclone.conf` on the host and deploy again, or run `rclone config reconnect gdrive-nas:` there.

- The remote uses rclone's default Google OAuth client, shared by all rclone users, which can return `403 RATE_LIMIT_EXCEEDED` on a large first backup. `restic_cloud_rclone_args` throttles requests. To use your own client instead: `rclone config`, edit `gdrive-nas`, set client ID and secret.
- Google expires the refresh token after 7 days for an app in "Testing" status, and after 6 months unused. If cloud backups stop with an auth error, redo step 1 and replace `rclone.conf`.

### SFTP

Set `restic_cloud_repository: "sftp:backup@host:/srv/restic"`. restic uses the host's SSH client. Set up by hand, as the ansible user that runs cron: a key without a passphrase in `~/.ssh`, and the server's host key in `~/.ssh/known_hosts` (`ssh-keyscan host >> ~/.ssh/known_hosts`, checked against the fingerprint). Without the host key the cron run waits on a prompt and fails. Ansible does not manage this. The rclone throttle (`restic_cloud_rclone_args`) does not apply.

---

## Web dashboard (read-only)

The `backup_status` role deploys a read-only dashboard with job status, drive mount state and the snapshot list for both repositories. It needs `backup_local_enabled`.

```
http://<host-tailscale-name>:<backup_status_port>
```

- Reachable from the LAN and the tailnet, with no login.
- The container mounts the repository, logs and password file read-only, so it cannot write to or delete a backup.
- Each action shows the exact SSH command to copy and run yourself.
- Switch it on with `backup_status_enabled`; change the port with `backup_status_port`.

---

## Connecting

Every command below assumes you have SSH'd in as the ansible user and set these once per session:

```bash
ssh your-user@your-host

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (restic_repo_path)
```

For the Google Drive repo instead: `export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"` (your `restic_cloud_repository`), and add `-o rclone.args="serve restic --stdio --tpslimit=10"` to each restic command.

---

## Checking backup status

A failed job is written to the system log (`journalctl -t backup`) and, with `ntfy_alert_url` set, sent to your phone ([services.md](./services.md#ntfy-failure-alerts)).

```bash
restic snapshots                                  # add --tag daily or --tag weekly to filter
tail -50 /mnt/backup/logs/backup-cron.log          # recent combined cron log (backup_logs_dir)

# Trigger a job manually (same scripts cron uses)
/bin/bash /opt/services/scripts/backup-restic-local.sh    # or backup-restic-cloud.sh, restic-check.sh
```

---

## Inspecting a snapshot

Get an ID from `restic snapshots` (or the dashboard). `latest` works in place of an ID too.

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
# Restore into a scratch path to inspect first (safe: doesn't touch originals)
restic restore latest --include /mnt/t7/files --target /mnt/t7/restore-scratch

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

`latest` is the newest snapshot of any group, and a repository can hold several groups. Use `restic snapshots` to find the right ID for each group.

To another machine (for example a USB drive on your Mac), stream the snapshot as a tar over SSH:

```bash
ssh your-user@your-host 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar
tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

Speed over Tailscale depends on `tailscale status` showing `direct` rather than `relay`. exFAT/FAT32 destinations lose Unix permissions and symlinks on extract; use APFS or ext4 if that matters.

---

## Restore: Immich database

```bash
ls -lh /mnt/backup/service-dumps/immich-db-*.sql.gz
cd /opt/services/immich && docker compose stop immich_server
/opt/services/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-<timestamp>.sql.gz
docker compose start immich_server
```

---

## Restore: Gitea

```bash
ls -lh /mnt/backup/service-dumps/gitea-dump-*.zip
/opt/services/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-<timestamp>.zip
# Gitea is stopped before restore and started after automatically
```

---

## If the backup drive disconnects

`nofail` in `fstab` only covers mounting at boot. A drive that drops out later is not remounted by it, and its mount point then becomes a plain folder on the root drive. Two guards cover this:

1. The backup scripts and the `restic-check` job run `mountpoint -q` on the backup drive first. If it is not mounted they exit without writing anything. The cron line logs the failure to `journalctl -t backup`.
2. `roles/storage/files/99-drive-remount.rules` runs `mount -a` (through `drive-remount.service`) whenever a filesystem appears, so a reconnected drive remounts within seconds.

Check with `mountpoint /mnt/backup`, `journalctl -t backup` and `systemctl status drive-remount.service`. If backups fail because the drive keeps dropping out, `vcgencmd get_throttled` and `dmesg | grep -iE 'sdb|voltage'` show whether the power supply, cable or hub is at fault (Raspberry Pi).

## Disaster recovery (all drives fail)

1. Get the vault password from Bitwarden first; without it nothing below works. Re-flash the OS, then run `just deploy` from `ansible/`. This needs the vault files and that password: `group_vars/all/vault.yml` (holds `vault_restic_password`) and `host_vars/<host>/vault.yml`. They exist only on your own machine, and without them no restic repository can be opened. Keep a copy of both somewhere that is not the host.
2. Pull from the cloud repository. It holds one snapshot group per path, and `latest` restores only one snapshot, so restore each:
   ```bash
   export RESTIC_PASSWORD_FILE=~/.restic-password
   export RESTIC_REPOSITORY="rclone:gdrive-nas:/pi-nas-backups"   # restic_cloud_repository
   restic -o rclone.args="serve restic --stdio --tpslimit=10" snapshots --group-by path
   restic -o rclone.args="serve restic --stdio --tpslimit=10" restore <snapshot-id> --target /      # once per group
   ```
3. Restore the Immich and Gitea databases from the dumps restored in step 2 (see Restore: Immich database and Restore: Gitea above, using the restored `service-dumps` folder).
