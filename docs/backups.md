# Backups

Backups use [restic](https://restic.readthedocs.io/). The `backup` role installs restic, the scripts and the cron jobs. Deploy with `just deploy backup,common` (`common` installs the alert script, so run it after changing `system_alert_to` or `ntfy_destinations`). Defaults for every setting here are in `ansible/roles/backup/defaults/main.yml` (rules, timeout, cache) and `ansible/group_vars/all/defaults-backups.yml` (repositories, retention, logs).

**Something went wrong?**

| Situation | Go to |
|---|---|
| Lost or removed files | [Restore: files](#restore-files) |
| Immich, Gitea or Garage data is broken | [Immich](#restore-immich-database), [Gitea](#restore-gitea), [Garage](#restore-garage) |
| All drives gone | [Disaster recovery](#disaster-recovery-all-drives-fail) |
| Backups fail or the backup drive dropped out | [If the backup drive disconnects](#if-the-backup-drive-disconnects), [Checking backup status](#checking-backup-status) |
| Drive will not mount | [storage.md](./storage.md#a-drive-that-will-not-mount) |
| Lost the vault password | Nothing opens a repository without `vault_restic_password`, so those backups cannot be read. Make a new repository ([switching backups on](#switching-backups-on)) and keep the password in a password manager this time |

## Switching backups on

Two flags per host in `host_vars/<host>/vars.yml`. A host can set either or both. The restic password is `vault_restic_password` in `group_vars/all/vault.yml`.

- `backup_local_enabled: true`: daily to a drive, plus a weekly check of that repository. The host needs a `drives` entry with the `backup` role and a `uuid` ([storage.md](./storage.md)). The deploy stops with a message if it has none.
- `backup_cloud_enabled: true`: weekly to `restic_cloud_repository`. Give each host its own path. A prune (deleting old snapshots) takes an exclusive lock on the repository, so a second host backing up to the same repository at that moment fails. The deploy stops if the setting is empty.
- The web dashboard (`backup_status_enabled`) reads the local repository, so it needs `backup_local_enabled`.

The scripts run as the ansible user and refuse to run as anyone else: a root run leaves root-owned files that the nightly run cannot read. Files only root can read are covered in [Root-only files](#root-only-files).

<details>
<summary>A cloud-only host, locks and the cache</summary>

A cloud-only host (`backup_cloud_enabled` without `backup_local_enabled`):

- cannot report a job that never runs (host off, cron stopped): alerts fire only when a job runs and fails.
- has no automatic integrity check: the weekly `restic check` exists only for the local repository ([check the cloud repository by hand](#checking-the-cloud-repository-manual)).
- has the short default cloud list ([below](#what-is-backed-up-where)): add what you want to `restic_cloud_extra_rules` (restic sends only changed data but reads all of it each run).
- keeps its logs and dumps in `/var/lib/backup-work` on the root drive.

Each run starts with `restic unlock`, which removes only stale locks: a restic killed by a reboot otherwise leaves a lock that makes every later prune fail. The restic cache (`restic_cache_dir`) is safe to remove. That only costs speed.

</details>

## First backup

The first run into an empty repository reads and hashes everything: hours for hundreds of GB over USB. Start it by hand as the ansible user, detached so a dropped SSH session does not stop it. Start it early enough that it ends before the daily run (see [What runs automatically](#what-runs-automatically)), which runs the same script:

```bash
setsid nohup /opt/services/scripts/backup-restic-local.sh > /tmp/first-backup.log 2>&1 < /dev/null &
```

`setsid` and `nohup` keep the job running after you log out. The output goes to `/tmp/first-backup.log`, and `< /dev/null` stops SSH from waiting on the job. Read the log with `tail /tmp/first-backup.log`.

Afterwards `restic snapshots` and `restic check` show a good repository ([Connecting](#connecting)).

## What runs automatically

| Cron job | Schedule | What it does |
|---|---|---|
| `backup-local` | Daily 02:00 | Runs the service dumps, then backs up to the local repository |
| `backup-cloud` | Sunday 04:00 | Runs the service dumps, then backs up to the cloud repository |
| `restic-check` | Saturday 05:00 | `restic check` on the local repository, reading a 5% sample |

- Jobs exist only for the flags that are on. Turning one off removes its jobs on the next deploy. With both off Ansible skips the role: remove the jobs with `just teardown <host> --tags backup` ([teardown](../ansible/README.md#turn-off-or-remove-a-service)).
- The local repository is `restic_repo_path` (`<backup drive mount>/restic-repo` unless set). Retention is `restic_local_retention` and `restic_cloud_retention`.
- Dumps are in `service_dumps_dir` (see Dumps below), logs in `backup_logs_dir` (one file per job per day, plus `backup-cron.log`). They sit on the backup drive with a local backup, otherwise in `/var/lib/backup-work`.
- The local backup refuses to start when the backup drive is 95% full or more, because `restic forget --prune` needs free room to clean up. The alert fires and the log says how full it is.

<details>
<summary>Changing times, the timeout, the alert path</summary>

- **Times** are the `hour`, `minute` and `weekday` lines of the cron tasks in `roles/backup/tasks/local.yml` and `cloud.yml`, not settings. Edit one and `just deploy backup` (Ansible matches a job by name, so it replaces the old time). Cron uses the host's `timezone`. Keep the check away from the backup.
- **Timeout:** every restic call has `restic_command_timeout`, default 23 hours, enough for a first backup over a slow link or USB 2. So a stalled network pipe fails the run instead of holding the lock. A run that hits the timeout stops and alerts. Raise it in `host_vars/<host>/vars.yml` for a larger repository.
- **Alerts:** a failed job goes to the system log (`journalctl -t backup`) and, with an alert URL set and `just deploy common`, to your phone ([services.md](./services.md#ntfy-failure-alerts)).

</details>

Paths below use `/mnt/backup` for the backup drive and `/mnt/data` for the fast and primary drive. Use your own mounts from `drives`.

## What is backed up where

Two rules lists decide it (defaults in `roles/backup/defaults/main.yml`). `restic_local_rules` (daily) is the mounted `primary` and `fast` drives, or the ansible user's home on a host with neither. `restic_cloud_rules` (weekly) is `services_dir` and, if Copyparty runs, its config. To add to a default use `restic_local_extra_rules` or `restic_cloud_extra_rules`. Setting the main list replaces the default. Both repositories also include `service_dumps_dir`.

| Data | Local (daily, backup drive) | Cloud (Sunday) |
|---|---|---|
| Files on the `primary` and `fast` drives (photos, Copyparty files, service data) | Yes | Only paths you add to `restic_cloud_extra_rules` |
| Copyparty config (`copyparty_config_dir`) | Yes | Yes |
| Compose files, scripts, the credentials written into them (`services_dir`) | No | Yes |
| Immich database | Dump only (raw Postgres directory excluded) | Dump only |
| Gitea database and repositories | Dump, plus raw data (SSH host keys excluded) | Dump only |
| Garage metadata | Dump only (`garage_meta_dir` excluded). Data blocks (`garage_blocks_dir`) are plain files | Dump only |
| Restic password | No | No |

The restic password is in no backup. Keep it in two places:

- `vault_restic_password`, which the deploy writes to `restic_password_file` on the host.
- Your password manager, together with the vault password that opens the vault.

Changing `vault_restic_password` does not change an existing repository: it still opens only with the password it was created with, so every backup fails until you put the old one back. The deploy keeps the replaced file beside the new one: copy it over `.restic-password` to undo.

- **Enforced (local):** the deploy fails if an enabled service's data directory is outside every path in `restic_local_rules`. Moving a service to a drive without a role then cannot silently drop it from the backup. The exceptions are the directories a service lists as `no_backup`: Immich's raw Postgres directory (a dump covers it), Scrutiny's history and Copyparty's thumbnails (both are written again). The deploy checks encrypted folders too. To leave a directory out on purpose, add `- <that directory>` to `restic_local_extra_rules`.
- **Not enforced (cloud):** the cloud list is short on purpose. With the cloud backup on, each deploy prints the data it leaves out.
- **Dumps:** one script per service with a live database (`roles/<service>/files/dump.sh` for Immich, Gitea, Garage), installed into `service_dump_scripts_dir`. `backup-services.sh` runs them all before each backup and keeps the last 3 files named `<script name>-*`. Everything else is plain files. A new service's dump: add `files/dump.sh` to its role (copy Gitea's), its files starting with `<service>-`. For software this repo does not run, put a `<name>.sh` in `service_dump_scripts_dir` by hand.

<details>
<summary>Always excluded, and why</summary>

- the encrypted copy of each listed folder, except its `gocryptfs.conf` ([encryption.md](./encryption.md#dumps-and-backups)).
- `restic_cache_dir`, the restic repository itself, `**/.cache` folders.
- logins: the restic password file, the rclone config, Cloudflare's tunnel token and the alert tokens (`alert_token_dir`), with the alert script that holds a destination address. The deploy writes them from the vault, the rclone config once. They can be kept in an [encrypted folder](./encryption.md#dumps-and-backups).
- rebuildable, root-owned data that a restore as the ansible user could not write back, regenerated after a restore: Docker's storage with `docker_data_root` set, Caddy's certificate storage, Tinyauth's OIDC signing keys, Copyparty's salts and certificate. Crafty's own `backups/` archives belong here too.
- unsafe or useless to copy: Gitea's SSH host keys, Immich's raw database directory, Copyparty's `hist`, and Garage's metadata (carried as a dump, see [Restore: Garage](#restore-garage)).

The lists are `roles/backup/templates/restic-excludes-{local,cloud,services}.txt.j2`. **Crafty:** to keep its `backups/` archives add `- !<crafty_data_dir>/backups`. Restic copies worlds while the server runs, so a world written mid-backup can be inconsistent. `teardown.yml -e remove_data=true` removes the archives too.

</details>

### Root-only files

The backup runs as the ansible user, but some files (a container's secrets, for example) only root can read. With `backup_read_all_files: true` (the default):

- **What you get:** the backup runs its own copy of restic, `/usr/local/bin/restic-backup`, with the Linux capability `cap_dac_read_search`. A capability is one extra permission on a program, here "read any file". The copy is mode 0750 for the ansible user's group. The packaged `/usr/bin/restic` has no capability.
- **The cost:** whoever runs commands as the ansible user can read any file on the host through that copy, without sudo.
- **Updates:** each deploy copies restic again and sets the capability, so an apt upgrade is picked up on the next deploy.

To keep that boundary, set `backup_read_all_files: false`. The packaged restic then runs, and each root-only file makes a run exit 3. restic still saves the snapshot and prunes, then the run fails so the alert fires. Exclude the file (`restic_local_rules`, `restic_cloud_rules`) or change its permissions to stop it. Every drive's `lost+found` is one, and so are the root-only scripts in `scripts_dir`.

Restic restores as the ansible user, so a restore cannot write into root-owned folders: use `sudo restic` for those.


## Choosing what is backed up

Each rules list holds one rule per line, after `just deploy backup`. `/path` backs a path up. `- pattern` leaves it out: keep the dash and space on the line, and in restic's pattern syntax `**` matches any number of folders. `- !pattern` puts back something an earlier `- ` line left out.

```yaml
restic_local_extra_rules:
  - /home/user/notes                     # add a folder to the default
  - "- **/*.iso"                         # leave out every .iso file
  - "- !/mnt/data/downloads/keep.iso"    # but keep this one
```

Quote the `- ` lines in YAML. The `_extra_rules` lists add to the default. Setting `restic_local_rules` or `restic_cloud_rules` itself replaces it, so the default drives drop out unless you list them. The deploy fails if a line is none of the three forms.

<details>
<summary>Rule details and snapshot groups</summary>

- `- ` lines run after the built-in exclude lists, so `- !` can undo a default. The cloud list works the same way, and its `- ` lines apply to every path in it. A `- !` line cannot bring back a file inside a folder that a `- ` line left out whole: exclude that folder's other contents by pattern instead. `- !` needs restic 0.13.0 or newer (Debian bookworm ships 0.14). [restic's syntax](https://restic.readthedocs.io/en/stable/040_backup.html) is not gitignore's.
- restic groups snapshots by host and paths. Adding or removing a `/path` line starts a new group. The old one stops growing but keeps its last snapshots until you remove them by hand: `restic snapshots --group-by host,paths`, then `restic forget <snapshot-id> --prune`. A `- ` line never splits a group, so tune with those first. In the cloud repository each path is its own group.

</details>

## Connecting

The restore and check commands assume you are SSH'd in as the ansible user with these set once per session:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (restic_repo_path)
```

For the cloud repository: `export RESTIC_REPOSITORY="<your restic_cloud_repository>"` and `export RCLONE_CONFIG="<rclone_config_dir>/rclone.conf"` (default `~/.config/rclone/rclone.conf`), and add `-o rclone.args="<restic_cloud_rclone_args>"` (default `serve restic --stdio --tpslimit=10`) to each restic command.

## Inspecting a snapshot

Get an ID from `restic snapshots` (or the dashboard). `latest` works in place of one. Browse and extract with restic's [`ls`, `diff`, `find` and `dump`](https://restic.readthedocs.io/en/stable/045_working_with_repos.html).

## Restore: files

`--target` needs real free space: `/tmp` can be a RAM disk and the root drive small, so use a path on a data drive. On a host with encrypted folders run `unlock.sh` first ([encryption.md](./encryption.md)): a locked folder is immutable and a restore into it stops with "Operation not permitted".

```bash
# Restore into a scratch path to inspect first (does not touch originals)
restic restore latest --include /mnt/data/shared/files --target /mnt/data/restore-scratch

# Restore everything to original paths (replaces current files)
restic restore latest --target /
```

`latest` is the newest snapshot of any group, and a repository can hold several groups: find each group's ID with `restic snapshots`.

<details>
<summary>To another machine (a USB drive on your Mac)</summary>

Stream the snapshot as a tar over SSH:

```bash
ssh your-user@your-host 'RESTIC_PASSWORD_FILE=~/.restic-password RESTIC_REPOSITORY=/mnt/backup/restic-repo restic dump latest / --archive tar' \
  > /Volumes/YourDrive/snapshot.tar
tar -xf /Volumes/YourDrive/snapshot.tar -C /Volumes/YourDrive/restored/
```

Speed over Tailscale depends on `tailscale status` showing `direct`, not `relay`. exFAT/FAT32 destinations lose Unix permissions and symlinks. Use APFS or ext4 if that matters.

</details>

## Restore: Immich database

```bash
ls -lh /mnt/backup/service-dumps/immich-db-*.sql.gz
cd /opt/services/immich && docker compose stop immich_server
/opt/services/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-<timestamp>.sql.gz
docker compose start immich_server
```

The dump holds only the `immich` database. The restore replays it into the `immich` database Postgres creates on first start, so it also works on a fresh container after a disk loss. A dump of the whole Postgres cluster (named `immich-db-*`, with `\connect immich` lines inside) cannot be replayed this way. Open it with `gunzip -c`, copy the part between `\connect immich` and the next `\connect` into a new file, and restore that.

## Restore: Gitea

```bash
ls -lh /mnt/backup/service-dumps/gitea-dump-*.zip
/opt/services/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-<timestamp>.zip
# Gitea is stopped before the restore and started after, automatically
```

The restore **replaces** Gitea's current data and repositories with the dump's: whatever was committed since is gone. Copy what you need first.

## Restore: Garage

Garage's metadata (which objects and buckets exist, and the node key) is root-owned and a live database. The file backup leaves out `<garage_meta_dir>` and carries it as `garage-meta-<timestamp>.tar.gz` in `service-dumps`. The data blocks in `<garage_blocks_dir>` are plain files. The tarball holds the node key: keep it as private as the vault. A deploy stops when the blocks directory has files and the metadata directory is empty: Garage would start a new empty cluster beside the old blocks. Put the metadata back first.

```bash
cd /opt/services/garage && docker compose stop garage
mkdir -p /tmp/garage-restore
tar -xzf /mnt/backup/service-dumps/garage-meta-<timestamp>.tar.gz -C /tmp/garage-restore
# the newest snapshot is a single LMDB file: it becomes data.mdb of the db.lmdb directory
sudo mv <garage_meta_dir>/db.lmdb <garage_meta_dir>/db.lmdb.old
sudo mkdir <garage_meta_dir>/db.lmdb
sudo cp /tmp/garage-restore/snapshots/<newest>/db.lmdb <garage_meta_dir>/db.lmdb/data.mdb
sudo cp /tmp/garage-restore/node_key /tmp/garage-restore/node_key.pub /tmp/garage-restore/cluster_layout <garage_meta_dir>/
docker compose start garage
```

The metadata is an [LMDB](./glossary.md) database. Keep `db.lmdb.old` until buckets and keys show up correctly in the web UI.

## Disaster recovery (all drives fail)

1. Get the vault password from your password manager. Then get the two vault files, `group_vars/all/vault.yml` (holds `vault_restic_password`) and `host_vars/<host>/vault.yml`. They live only on your own machine, and no restic repository opens without them. Keep a copy of both somewhere that is not the host.
2. Re-flash the OS.
3. Format the replacement drives and put their `uuid` values in `drives` ([storage.md](./storage.md)). The deploy stops while a drive it expects is missing.
4. Run `just deploy` from `ansible/`.
5. Set the cloud repository as in [Connecting](#connecting) and pull from it. It holds one snapshot group per path and `latest` restores only one snapshot, so restore each:
   ```bash
   restic -o rclone.args="<restic_cloud_rclone_args>" snapshots --group-by path
   restic -o rclone.args="<restic_cloud_rclone_args>" restore <snapshot-id> --target /      # once per group
   ```
   With the default rules it holds no photos or Copyparty files ([above](#what-is-backed-up-where)). Those come back only from an [offline copy](#offline-copy-on-a-second-drive).
6. Restore the Immich and Gitea databases and Garage's metadata from the dumps restored in step 4 (the Restore sections above, using the restored `service-dumps` folder).

On a host with encrypted folders, [unlock them](./encryption.md#unlocking) first: backups refuse to run while one is locked.

## If the backup drive disconnects

A missing drive: [storage.md](./storage.md#with-a-drive-missing). The backup scripts and `restic-check` run `mountpoint -q <mount>/.` on the backup drive first. The backup scripts also run it on every data drive (`fast` or `primary`) and every `encrypted_folders` folder ([why the `/.`](./storage.md#how-a-drive-is-mounted)). So they never save a snapshot of an empty folder. A missing drive makes the script exit without writing, the cron line logs the failure to `journalctl -t backup`, and the next run mounts a returned drive.

Check with `mountpoint /mnt/backup/.`, `journalctl -t backup` and `systemctl status mnt-backup.automount`. If it keeps dropping out, on a Raspberry Pi `vcgencmd get_throttled` and `dmesg | grep -iE 'sdb|voltage|over-current'` show whether the power supply, cable or hub is at fault. `over-current` is the USB ports' own limit, which `get_throttled` does not report.

## Checking backup status

```bash
restic snapshots                                   # add --tag daily or --tag weekly to filter
tail -50 /mnt/backup/logs/backup-cron.log           # recent combined cron log (backup_logs_dir)
/bin/bash /opt/services/scripts/backup-restic-local.sh   # run a job by hand; or backup-restic-cloud.sh, restic-check.sh
```

The dashboard does not check that a `daily` snapshot exists, only that the job ran. The dashboard's job status comes from `<backup_logs_dir>/restic-<local|cloud|check>.status.json`, which each script writes when a run starts and when it ends. A missing, unreadable or too old file shows as an error, never ok. `cat` it to see what the last run did. A run that stops before writing it (a mount guard, such as a dropped drive) leaves the previous result. A card can then say ok for up to 36 hours (9 days for weekly jobs) after the first such failure. The alert is what reports it.

### Checking the cloud repository (manual)

No schedule checks the cloud repository (a full check reads all of it over the network). Run it occasionally as the ansible user, with the cloud repository from [Connecting](#connecting):

```bash
restic -o rclone.args="<restic_cloud_rclone_args>" check
```

Add `--read-data-subset=5%` to also read a sample of the stored data. For an SFTP repository leave out the `-o rclone.args` option.

## Cloud repository (`restic_cloud_repository`)

The URL scheme picks the backend. The deploy runs `restic init` on it and fails if that fails (no rclone remote, bad credentials, unreachable server). It leaves an existing repository alone.

**Google Drive** goes through rclone, which the deploy installs for `rclone:` repositories. Its login needs a browser, so the token comes from the vault:

1. On your Mac (needs `rclone`): `rclone authorize "drive" --drive-scope drive.file`, sign in. It prints a JSON token.
2. Put it in `group_vars/all/vault.yml` as `vault_rclone_gdrive_token` (single-quoted).
3. `just deploy backup`. Ansible writes `rclone.conf` in `rclone_config_dir` (default `~/.config/rclone`) with a `gdrive` remote only if the file does not exist (rclone writes refreshed tokens back into it).

To replace a broken login, remove `rclone.conf` from `rclone_config_dir` on the host and deploy again, or run `RCLONE_CONFIG=<rclone_config_dir>/rclone.conf rclone config reconnect gdrive:` there.

<details>
<summary>Google quotas and token expiry, and SFTP</summary>

- The remote uses rclone's default Google OAuth client, shared by all rclone users, which can return `403 RATE_LIMIT_EXCEEDED` on a large first backup. `restic_cloud_rclone_args` throttles requests. To use your own client, `rclone config`, edit `gdrive`, set the client ID and secret.
- Google expires the refresh token after 7 days for an app in "Testing" status and after 6 months unused. If cloud backups stop with an auth error, redo step 1 and replace `rclone.conf`.
- **SFTP:** `restic_cloud_repository: "sftp:backup@host:/srv/restic"` uses the host's SSH client. Set it up by hand as the ansible user that runs cron. It needs a passphrase-less key in `~/.ssh` and the server's host key in `~/.ssh/known_hosts` (`ssh-keyscan host >> ~/.ssh/known_hosts`, checked against the fingerprint). Without the host key the cron run waits on a prompt and fails. The rclone throttle does not apply.

</details>

## Web dashboard (read-only)

The `backup_status` role (`backup_status_enabled`, needs `backup_local_enabled`) deploys a read-only dashboard. It shows job status, the drive's mount state, a warning when a restic lock remains, and the snapshot list for both repositories. A local snapshot's files open as a folder tree with sizes, and the dashboard lists its changes since the previous snapshot on request. Running a job, restoring, removing and the cloud snapshots show the exact SSH command to copy and run yourself.

It runs at `https://backups.<private domain>` behind the [Tinyauth login](./services.md#tinyauth-login). A host without Tinyauth sets `backup_status_port` (for example `8091`) to publish it at `http://<host>:<port>` with no login, open to everyone on the network, local snapshot file names included. The deploy stops if the host has neither, so it never comes up without a login or a port you chose. The container mounts the repository, logs and password file read-only, so it cannot write to or remove a backup.

## Offline copy on a second drive

`restic copy` copies snapshots into a second repository, for example on a drive you unplug and store elsewhere. The destination is `-r` and the source is `--from-repo`. Each repository needs its own password option. Create it once, with the source's chunker settings so the copy stores identical data once:

```bash
restic -r /mnt/offline/restic-repo init \
  --password-file ~/.restic-password \
  --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password \
  --copy-chunker-params
```

Copy new snapshots (restic skips ones already copied):

```bash
restic -r /mnt/offline/restic-repo copy \
  --password-file ~/.restic-password \
  --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password
```
