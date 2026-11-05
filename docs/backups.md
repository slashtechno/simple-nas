# Backups

Backups use [restic](https://restic.readthedocs.io/). The `backup` role installs restic, the scripts and the cron jobs.

- **Deploy:** `just deploy backup,common` from `ansible/`. `common` installs the alert script, so run it after changing `ntfy_alert_url`.
- **Settings:** every setting named below, with its default, is in `ansible/roles/backup/defaults/main.yml` (rules, timeout, cache) or `ansible/group_vars/all/backups.yml` (repositories, retention, logs).

## Switching backups on

Each host chooses its backups with two flags in `host_vars/<host>/vars.yml`:

- `backup_local_enabled: true` backs up daily to a drive and checks that repository weekly. The host needs a `drives` entry with the `backup` role and a `uuid` ([storage.md](./storage.md)). The deploy stops with a message if it has none.
- `backup_cloud_enabled: true` backs up weekly to `restic_cloud_repository`. Set that per host in `host_vars/<host>/vars.yml`, with a path no other host uses: hosts that share a repository prune each other's snapshots. The deploy stops with a message if it is empty.
- A host can set either flag or both. The restic password comes from `vault_restic_password` in `group_vars/all/vault.yml`.
- The web dashboard (`backup_status_enabled`) reads the local repository, so it needs `backup_local_enabled`.

A cloud-only host (`backup_cloud_enabled` without `backup_local_enabled`):

- It cannot report a job that never runs (host off, cron stopped): alerts fire only when a job runs and fails. Covering that needs an external heartbeat service, which this repo does not run.
- It has no automatic integrity check. The weekly `restic check` job exists only for the local repository, and the cloud check is manual ([Checking the cloud repo](#checking-the-cloud-repo-manual)).
- Its offsite list is the short default ([What is backed up where](#what-is-backed-up-where)). Add what you want offsite to `restic_cloud_extra_rules`; restic sends only data that changed, but it reads all of it each run.
- Its logs and database dumps are kept on the root drive in `/var/lib/backup-work`.

The backups run as the ansible user, and the scripts refuse to run as anyone else: a run as root leaves root-owned files in the repository that the nightly run cannot read.

- **Unreadable files are skipped.** Files only root can read (data owned by a container's user) are reported by restic as `error:` lines. The snapshot is saved without them, old snapshots are still pruned, and then the run fails so the alert fires.
- **The fix** for a stack whose containers write as root: dump its data, or change its owner.

Each backup and check run starts with `restic unlock`, which removes only stale locks. Without it a restic killed by a reboot leaves a lock that makes every later prune fail with "repository is already locked", and old snapshots then pile up.

restic keeps its cache in `restic_cache_dir`. It is safe to delete: that only costs speed.

## First backup

The first run into an empty repository reads and hashes everything, so it takes hours for hundreds of GB over USB.

- Start it by hand rather than waiting for the cron job, detached so a dropped SSH session does not stop it: `setsid nohup /opt/services/scripts/backup-restic-local.sh > /tmp/first-backup.log 2>&1 < /dev/null &`, as the ansible user.
- Start it so that it ends before 02:00, when the cron job runs the same script.
- Files the backup user cannot read are reported as `error:` lines. restic still saves the snapshot, and the run then exits 3 and fires the alert ([Switching backups on](#switching-backups-on)).
- Afterwards `restic snapshots` and `restic check` show a good repository ([Connecting](#connecting)).

## What runs automatically

| Cron job | Schedule | What it does |
|---|---|---|
| `backup-local` | Daily 02:00 | Runs the service dumps, then backs up to the local repository |
| `backup-cloud` | Sunday 04:00 | Runs the service dumps, then backs up to the cloud repository |
| `restic-check` | Saturday 05:00 | Runs `restic check` on the local repository, reading a 5% sample of the data |

- **Times:** the `hour`, `minute` and `weekday` lines of the cron tasks in `ansible/roles/backup/tasks/local.yml` and `cloud.yml`, not settings. Edit one and `just deploy backup`: a job is matched by its name, so the old time is replaced.
- Cron uses the host's `timezone`. The jobs are independent; keep the check away from the backup so they do not run together.
- The local repository is `restic_repo_path`, `<backup drive mount>/restic-repo` unless you set it.
- Jobs only exist for the flags that are on. Turning one flag off removes its jobs and scripts on the next deploy. Turning both off skips the role, so remove the jobs with `just teardown <host> --tags backup` ([teardown](../ansible/README.md#disable-or-remove-a-service)).
- Dumps: `service_dumps_dir`, the last 3 of each type kept.
- Logs: `backup_logs_dir`, one file per job per day, plus `backup-cron.log`.
- With a local backup both live on the backup drive (`<backup drive>/service-dumps`, `<backup drive>/logs`). Without one they live in `/var/lib/backup-work`.
- Every restic call has a timeout, `restic_command_timeout`, so a stalled network pipe fails the run instead of holding the repository lock. It defaults to 23 hours, long enough for the first backup into an empty repository over a slow link or USB 2.
- A run that hits the timeout is killed and alerts. Raise it in `host_vars/<host>/vars.yml` and `just deploy backup` if a repository is larger still; nightly runs finish far sooner.
- Snapshot retention is `restic_local_retention` and `restic_cloud_retention`.
- The local backup refuses to start when the backup drive is 95% full or more: `restic forget --prune` needs free room to rewrite packs, so a full drive cannot clean itself up. The failure reaches the alert, and the log says how full the drive is.

Paths below use `/mnt/backup` for the backup drive and `/mnt/data` for the fast and primary drive (your mount points will differ). Use the mounts from your `drives`.

## What is backed up where

What a host backs up is set by two rules lists, with defaults in `ansible/roles/backup/defaults/main.yml`:

- `restic_local_rules` (daily): the mounted `primary` and `fast` drives, or the ansible user's home on a host with neither.
- `restic_cloud_rules` (weekly): the host's base directory (`services_dir`) and, if Copyparty runs, Copyparty's config.
- To add to a default, put lines in `restic_local_extra_rules` or `restic_cloud_extra_rules`. Setting the main list replaces the default.

With the defaults on a NAS:

| Data | Local (daily, backup drive) | Cloud (Sunday) |
|---|---|---|
| Files on the `primary` and `fast` drives (photos, Copyparty files, service data) | Yes | Only the paths you add to `restic_cloud_extra_rules` |
| Copyparty config (`copyparty_config_dir`) | Yes | Yes |
| Compose files, scripts and the credentials written into them (`services_dir`) | No | Yes |
| Immich database | Dump only (the raw Postgres directory is excluded) | Dump only |
| Gitea database and repositories | Dump, plus the raw data (SSH host keys excluded) | Dump only |
| Garage metadata | Dump only (`<garage_data_dir>/meta` is excluded); the data blocks are plain files | Dump only |
| Restic password | No | No |

- The restic password is not in any backup. It is in `vault_restic_password` (`group_vars/all/vault.yml`) and in `restic_password_file` on the host, and the vault password is in your password manager ([Disaster recovery](#disaster-recovery-all-drives-fail), step 1).
- Both repositories always include `service_dumps_dir` as well.
- **Enforced (local):** the deploy fails if an enabled service's data directory is outside every path in `restic_local_rules` (`roles/backup/tasks/check_coverage.yml`), so moving a service to a drive without a role cannot silently drop it from the backup. Encrypted folders are checked the same way. Immich's raw database directory is not checked: it is excluded and reaches the backup through its dump.
- **Leaving a directory out on purpose** (data you can lose): add `- <that directory>` to `restic_local_extra_rules`; it then counts as decided.
- **Not enforced (offsite):** the offsite list is short on purpose. With the cloud backup on, each deploy prints the enabled services' data it leaves out.
- **Always excluded:**
  - the encrypted copy of each listed folder, except its `gocryptfs.conf` ([encryption.md](./encryption.md#dumps-and-backups));
  - `restic_cache_dir`, the restic repository itself, the `**/.cache` folders and the data drives' `lost+found`;
  - logins: the restic password file, the rclone config, and Cloudflare's tunnel token (`services_dir/cloudflared/token`, rewritten from the vault on each deploy);
  - rebuildable data: Docker's storage when `docker_data_root` is set, Caddy's certificate storage (`caddy_data_dir/caddy`) and Copyparty's salts and certificate (`copyparty_config_dir/copyparty`), both root-owned and regenerated after a restore, Crafty's own `backups/` archives;
  - files that are unsafe or useless to copy: Gitea's SSH host keys, Immich's raw database directory, Copyparty's `hist` directory, and Garage's metadata directory (carried as a dump instead, see [Restore: Garage](#restore-garage)).

  The lists are `roles/backup/templates/restic-excludes-local.txt.j2`, `restic-excludes-cloud.txt.j2` and `restic-excludes-services.txt.j2`.
- Dumps: one script per service with a live database, installed into `service_dump_scripts_dir` by that service's role (`roles/immich/files/dump.sh`, `roles/gitea/files/dump.sh`, `roles/garage/files/dump.sh`). `backup-services.sh` runs them all before each backup and keeps the last 3 files named `<script name>-*`. Everything else is plain files.

## Choosing what is backed up

Each rules list holds one rule per line. A line is one of:

- `/path`: an absolute path to back up.
- `- pattern`: leave this out. The dash and the space are part of the line. The pattern uses restic's syntax, not gitignore's ([restic docs](https://restic.readthedocs.io/en/stable/040_backup.html)): `**` matches any number of folders.
- `- !pattern`: put back something an earlier `- ` line left out.

`- ` lines run after the built-in exclude lists, so a `- !` line can also undo a default. The cloud list works the same way, and its `- ` lines apply to every path in it. The deploy fails if a line is none of the three.

Worked example, in `host_vars/<host>/vars.yml`. Add a folder, leave out a kind of file, then keep one file of that kind:

```yaml
restic_local_extra_rules:
  - /home/user/notes                     # add a folder to the default
  - "- **/*.iso"                         # leave out every .iso file
  - "- !/mnt/data/downloads/keep.iso"      # but keep this one
```

- Quote the `- ` lines in YAML, as above.
- The `_extra_rules` lists add to the default. Setting `restic_local_rules` or `restic_cloud_rules` itself replaces the default, so the default drives drop out unless you list them.
- A `- !` line cannot bring back a file inside a folder that a `- ` line left out as a whole. To keep one file out of an excluded folder, exclude the folder's other contents by pattern instead.
- `- !` needs restic 0.13.0 or newer (Debian bookworm ships 0.14).
- After editing, run `just deploy backup`.

Consequences of changing the lists:

- restic groups snapshots by host and paths. Adding or removing a `/path` line starts a new snapshot group. The old group stops growing but keeps its last snapshots until you remove them by hand: `restic snapshots --group-by host,paths`, then `restic forget <snapshot-id> --prune`.
- Adding or removing a `- ` line never splits a group, so tune with those first.
- In the cloud repository each path is its own group.

**Crafty:** its own `backups/` archives are excluded. To keep them, add `- !<crafty_data_dir>/backups` (the full path) to the list. Worlds are copied while the server runs, so a world written mid-backup can be inconsistent. `teardown.yml -e remove_data=true` deletes the whole of `crafty_data_dir`, archives included.

To give a new service a database dump, add `files/dump.sh` to its role and install it into `service_dump_scripts_dir` as `<service>.sh` (copy the Gitea role). Its dump files must start with `<service>-`. `teardown_service.yml` removes the script again. For software this repo does not run, put an executable `<name>.sh` in `service_dump_scripts_dir` by hand; the backup runs every `*.sh` there.

### Checking the cloud repo (manual)

No schedule checks the cloud repository: a full check reads all of it over the network. Run it now and then, as the ansible user on the host, with the cloud repository from [Connecting](#connecting):

```bash
restic -o rclone.args="serve restic --stdio --tpslimit=10" check
```

Add `--read-data-subset=5%` to also read a sample of the stored data. For an SFTP repository leave out the `-o rclone.args` option.

## Offsite repository (`restic_cloud_repository`)

The URL scheme picks the backend. The deploy runs `restic init` on it and fails if that fails (no rclone remote, bad credentials, unreachable server). An existing repository is left alone.

### Google Drive

Google Drive goes through rclone, which the deploy installs for `rclone:` repositories. Its login needs a browser, so the token comes from the vault:

1. On your Mac (needs `rclone`): `rclone authorize "drive" --drive-scope drive.file`. Sign in; it prints a JSON token.
2. Put that JSON in `group_vars/all/vault.yml` as `vault_rclone_gdrive_token` (single-quoted).
3. `just deploy backup`. Ansible writes `~/.config/rclone/rclone.conf` with a `gdrive` remote only if the file does not exist, because rclone writes refreshed tokens back into it.

To replace a broken login, delete `~/.config/rclone/rclone.conf` on the host and deploy again, or run `rclone config reconnect gdrive:` there.

- The remote uses rclone's default Google OAuth client, shared by all rclone users, which can return `403 RATE_LIMIT_EXCEEDED` on a large first backup. `restic_cloud_rclone_args` throttles requests. To use your own client instead: `rclone config`, edit `gdrive`, set client ID and secret.
- Google expires the refresh token after 7 days for an app in "Testing" status, and after 6 months unused. If cloud backups stop with an auth error, redo step 1 and replace `rclone.conf`.

### SFTP

Set `restic_cloud_repository: "sftp:backup@host:/srv/restic"`. restic uses the host's SSH client. Set up by hand, as the ansible user that runs cron: a key without a passphrase in `~/.ssh`, and the server's host key in `~/.ssh/known_hosts` (`ssh-keyscan host >> ~/.ssh/known_hosts`, checked against the fingerprint). Without the host key the cron run waits on a prompt and fails. Ansible does not manage this. The rclone throttle (`restic_cloud_rclone_args`) does not apply.

## Web dashboard (read-only)

The `backup_status` role deploys a read-only dashboard with job status, the drive's mount state, a warning when a restic lock is left on the repository, and the snapshot list for both repositories. It needs `backup_local_enabled`; switch it on with `backup_status_enabled`.

It is served at `https://backups.<private domain>` behind the [Tinyauth login](./services.md#tinyauth-login), and a host without Tinyauth sets `backup_status_port` (for example `8091`) to publish it at `http://<host>:<port>` with no login, open to everyone on the network. The deploy stops if the host has neither, so the dashboard never comes up without a login or a port you chose.

- The container mounts the repository, logs and password file read-only, so it cannot write to or delete a backup.
- Each action shows the exact SSH command to copy and run yourself.

## Connecting

Every command below assumes you have SSH'd in as the ansible user and set these once per session:

```bash
ssh your-user@your-host

export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo   # local repo (restic_repo_path)
```

For the Google Drive repo instead: `export RESTIC_REPOSITORY="<your restic_cloud_repository>"`, and add `-o rclone.args="serve restic --stdio --tpslimit=10"` to each restic command.

## Offline copy on a second drive

`restic copy` copies snapshots into a second repository, for example on a drive that is unplugged and stored elsewhere. The destination is the repository (`-r`) and the source is `--from-repo`; each repository needs its own password option.

Create the second repository once, with the source's chunker settings so the copy deduplicates:

```bash
restic -r /mnt/offline/restic-repo init \
  --password-file ~/.restic-password \
  --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password \
  --copy-chunker-params
```

To copy new snapshots (already-copied ones are skipped):

```bash
restic -r /mnt/offline/restic-repo copy \
  --password-file ~/.restic-password \
  --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password
```

## Checking backup status

The dashboard's job status comes from `<backup_logs_dir>/restic-<local|cloud|check>.status.json`, which each script writes when a run starts and again when it ends. A missing, unreadable or too old file shows as an error, never as ok; the `.log` files are for reading. `cat /mnt/backup/logs/restic-local.status.json` shows what the last run did. A run that stops before writing the file (a mount guard, such as a dropped backup drive) leaves the previous result in place, so a card can still say ok for up to 36 hours (9 days for the weekly jobs) after the first such failure; the alert is what reports it.

A failed job is written to the system log (`journalctl -t backup`) and, with `ntfy_alert_url` set (and `just deploy common`), sent to your phone ([services.md](./services.md#ntfy-failure-alerts)).

```bash
restic snapshots                                  # add --tag daily or --tag weekly to filter
tail -50 /mnt/backup/logs/backup-cron.log          # recent combined cron log (backup_logs_dir)

# Trigger a job manually (same scripts cron uses)
/bin/bash /opt/services/scripts/backup-restic-local.sh    # or backup-restic-cloud.sh, restic-check.sh
```

## Inspecting a snapshot

Get an ID from `restic snapshots` (or the dashboard). `latest` works in place of an ID too.

```bash
restic ls <snapshot-id>                                   # list everything it contains
restic diff <snapshot-id-1> <snapshot-id-2>                # what changed between two snapshots
restic find <pattern>                                      # which snapshot(s) contain a file (globs OK)
restic dump <snapshot-id> <path-in-snapshot> > recovered-file   # extract one file
```

## Restore: files

`--target` needs real free space. `/tmp` is in RAM and `/` is small, so use a path on a data drive such as `/mnt/data` or `/mnt/backup`.

```bash
# Restore into a scratch path to inspect first (safe: doesn't touch originals)
restic restore latest --include /mnt/data/files --target /mnt/data/restore-scratch

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

## Restore: Immich database

```bash
ls -lh /mnt/backup/service-dumps/immich-db-*.sql.gz
cd /opt/services/immich && docker compose stop immich_server
/opt/services/scripts/restore-services.sh immich /mnt/backup/service-dumps/immich-db-<timestamp>.sql.gz
docker compose start immich_server
```

The dump holds only the `immich` database, and the restore replays it into the `immich` database that Postgres creates on first start, so it also works on a fresh Immich container after a disk loss. A dump of the whole Postgres cluster (named `immich-db-*`, with `\connect immich` lines inside) cannot be replayed this way: open it with `gunzip -c`, copy the part between `\connect immich` and the next `\connect` into a new file, and restore that.

## Restore: Gitea

```bash
ls -lh /mnt/backup/service-dumps/gitea-dump-*.zip
/opt/services/scripts/restore-services.sh gitea /mnt/backup/service-dumps/gitea-dump-<timestamp>.zip
# Gitea is stopped before restore and started after automatically
```

## Restore: Garage

Garage's metadata (which objects and buckets exist, and the node key) is root-owned and a live database.

- `<garage_data_dir>/meta` is excluded from the file backup. It reaches the backup as `garage-meta-<timestamp>.tar.gz` in `service-dumps`; the data blocks under `<garage_data_dir>/data` are plain files in the backup.
- The tarball holds the node key: keep it as private as the vault.
- A deploy stops when `<garage_data_dir>/data` has files and `<garage_data_dir>/meta` is empty, because Garage would start a new empty cluster beside the old blocks. Put the metadata back first.

```bash
cd /opt/services/garage && docker compose stop garage
mkdir -p /tmp/garage-restore
tar -xzf /mnt/backup/service-dumps/garage-meta-<timestamp>.tar.gz -C /tmp/garage-restore
# the newest snapshot is a single LMDB file: it becomes data.mdb of the db.lmdb directory
sudo mv <garage_data_dir>/meta/db.lmdb <garage_data_dir>/meta/db.lmdb.old
sudo mkdir <garage_data_dir>/meta/db.lmdb
sudo cp /tmp/garage-restore/snapshots/<newest>/db.lmdb <garage_data_dir>/meta/db.lmdb/data.mdb
sudo cp /tmp/garage-restore/node_key /tmp/garage-restore/node_key.pub /tmp/garage-restore/cluster_layout <garage_data_dir>/meta/
docker compose start garage
```

This restore has not been rehearsed on a real host. Try it once into a scratch Garage before relying on it, and keep `db.lmdb.old` until buckets and keys show up correctly in the web UI.

## If the backup drive disconnects

What happens with a drive missing is in [storage.md](./storage.md#with-a-drive-missing). The backup scripts and the `restic-check` job run `mountpoint -q <mount>/.` on the backup drive first, and the backup scripts also on every data drive (role `fast` or `primary`) and every folder in `encrypted_folders` ([why the `/.`](./storage.md#how-a-drive-is-mounted)), so they never save a snapshot of an empty folder. A missing drive makes the script exit without writing anything, and the cron line logs the failure to `journalctl -t backup`. The next run mounts a returned drive.

Check with `mountpoint /mnt/backup/.`, `journalctl -t backup` and `systemctl status mnt-backup.automount`. If backups fail because the drive keeps dropping out, `vcgencmd get_throttled` and `dmesg | grep -iE 'sdb|voltage'` show whether the power supply, cable or hub is at fault (Raspberry Pi).

## Disaster recovery (all drives fail)

1. Get the vault password from your password manager first; without it nothing below works. Re-flash the OS, then run `just deploy` from `ansible/`. This needs the vault files and that password: `group_vars/all/vault.yml` (holds `vault_restic_password`) and `host_vars/<host>/vault.yml`. They exist only on your own machine, and without them no restic repository can be opened. Keep a copy of both somewhere that is not the host.
2. Format the replacement drives and put their `uuid` values in `drives` ([storage.md](./storage.md)), then pull from the cloud repository, with the cloud repository set as in [Connecting](#connecting). With the default rules it holds no photos or Copyparty files ([What is backed up where](#what-is-backed-up-where)), so those come back only from an [offline copy](#offline-copy-on-a-second-drive). It holds one snapshot group per path, and `latest` restores only one snapshot, so restore each:
   ```bash
   restic -o rclone.args="serve restic --stdio --tpslimit=10" snapshots --group-by path
   restic -o rclone.args="serve restic --stdio --tpslimit=10" restore <snapshot-id> --target /      # once per group
   ```
3. Restore the Immich and Gitea databases and Garage's metadata from the dumps restored in step 2 (see Restore: Immich database, Restore: Gitea and Restore: Garage above, using the restored `service-dumps` folder).

If the host uses [encryption](./encryption.md), the backup scripts refuse to run while a listed folder is locked; unlock first.
