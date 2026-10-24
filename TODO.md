# TODO

The owner's list: work that needs their time or hardware, or that lives outside this repo. Each item says what it waits for. Delete an item when it is done; facts and decisions belong in the docs, not here.

## To check on hardware

- Restore drill: `restore-services.sh` and the disaster-recovery steps in [backups.md](./docs/backups.md) have not been run end to end. Waiting for: a spare host or a quiet hour.
- Copyparty thumbnails for real NEF and HEIC files. Waiting for: opening a few in the web UI.
- Drive unplug tests: boot with a drive unplugged, unplug one while running, run a backup with the backup drive unplugged ([storage.md](./docs/storage.md#how-a-drive-is-mounted)). Waiting for: someone at the host.
- A USB drive plugged into a host with `usb_automount_enabled: true` appears under `/run/media/system/<label>` and in Copyparty's `/drives`. Waiting for: a plug-in.
- The netplan direct Ethernet link on Ubuntu Server ([networking.md](./docs/networking.md#direct-ethernet-link)). Waiting for: an Ubuntu Server host with a cable to a laptop.

## Clean-up after a deploy

- Delete the stale `pi-nas-runner` entry in Gitea.
- After the next Sunday offsite backup: `restic forget` the snapshot group for the old `/opt/nas` path ([backups.md](./docs/backups.md#choosing-what-is-backed-up)).

## Waiting for hardware or a decision

- Drive migration: [plans/drive-migration.md](./plans/drive-migration.md).
- Encryption at rest: [docs/research/encryption.md](./docs/research/encryption.md).
- A pics `archive_dir` option belongs in the pics repository, with its path under a drive that has a role so the backup covers it.
