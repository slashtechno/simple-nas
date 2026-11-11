# TODO

The owner's list: work that needs their time or hardware, or that lives outside this repo. Each item ends with what it waits for. Delete an item when it is done; facts and decisions belong in the docs, not here. Open plans: [plans/](./plans/).

- Restore a Garage metadata dump into a scratch Garage ([backups.md](./docs/backups.md#restore-garage)) — waits for: a quiet hour.
- Copyparty thumbnails for real NEF and HEIC files — waits for: opening a few in the web UI.
- Drive unplug tests: boot with a drive unplugged, unplug one while running, run a backup with the backup drive unplugged ([storage.md](./docs/storage.md#how-a-drive-is-mounted)) — waits for: someone at the host.
- A USB drive plugged into a host with `usb_automount_enabled: true` appears under `/run/media/system/<label>` and in Copyparty's `/drives` — waits for: a plug-in.
- The direct Ethernet link on Ubuntu Server ([networking.md](./docs/networking.md#direct-ethernet-link)) — waits for: an Ubuntu Server host and a cable to a laptop.
- Move pics to its own GitHub repo: set `pics_repo` to it and change `build: ./src/local/pics` in `roles/pics/templates/docker-compose.yml.j2` to `./src` — waits for: the owner creating the repo.
- A pics `archive_dir` option, with its path under a drive that has a role so the backup covers it — waits for: the owner writing it in the pics repository.
- Delete the stale `pi-nas-runner` entry in Gitea — waits for: a few minutes in Gitea's admin page.
- `restic forget` the snapshot group for the old `/opt/nas` path ([backups.md](./docs/backups.md#choosing-what-is-backed-up)) — waits for: the next Sunday offsite backup.
- Unlock encrypted folders without SSH: [plans/unlock-web-page.md](./plans/unlock-web-page.md) — waits for: the owner's decisions listed there.
- Drive migration: [plans/drive-migration.md](./plans/drive-migration.md) — waits for: the new drive passing its vetting.
- Encryption at rest ([encryption.md](./docs/encryption.md)): open the folder on a Mac (gocryptfs and macFUSE) before real data goes in — waits for: a spare drive.
- Open items of [plans/next-steps.md](./plans/next-steps.md) — waits for: each item's own condition.
