# Open items

Work that is not done and needs the owner's time or hardware, or that lives outside this repo. Each item says what it is waiting for.

## Not verified on real hardware

- Restore drill: `restore-services.sh` and the disaster-recovery steps in [backups.md](./backups.md) have not been run end to end. Waiting for: a spare host or a quiet hour to try it.
- Copyparty thumbnails for real NEF and HEIC files. Waiting for: opening a few in the web UI.
- `pipelining = True` in `ansible.cfg` on a Pi. Waiting for: the first `just preview` on one.
- Garage, Caddy and Garage web UI image bumps on real data. Waiting for: a deploy and a look at each service.

## Outside this repo

- Alerts for a cron job that never runs (host off, cron stopped). Failure alerts fire only when a job runs and fails. Covering the rest needs an external heartbeat service, which this repo does not run.
- A pics `archive_dir` option. pics is a separate app with its own repository; the setting belongs there, and its path would then sit under a drive with a role so the backup covers it.

## Decided, not planned

- The offsite `restic check` stays manual: a full check reads the whole repository over the network ([backups.md](./backups.md)).
- `--ask-vault-pass` stays. A `vault_password_file` script (`bw get password <entry>`) is possible but needs the `bw` CLI unlocked on the laptop.
- `pics_version: main` follows the head of the owner's own private pics repository, so each deploy builds its latest commit. Set it to a tag or commit in `host_vars` when a stable build matters.

## Waiting for hardware

- Drive migration (4 TB backup drive, WD P10 as `primary`, T7 stays `fast`): [plans/drive-migration.md](./plans/drive-migration.md).
