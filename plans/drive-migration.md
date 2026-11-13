# Drive migration plan (2 drives to 3 drives)

> **Status: active plan. Delete this file when the migration is done; git history keeps it.** It records one owner's steps, not conventions: the rules are in AGENTS.md and the code.

Waiting on the owner's steps. The drives are bought; pinas's `drives` lists the T7 (`fast, primary`) and the IronWolf (`backup`); the P10 is not in it yet. The steps run on pinas.

Target, in the host's `drives` list (`ansible/host_vars/<host>/vars.yml`; roles are explained in [storage.md](../docs/storage.md)):

| Role | Drive | Mount | Holds |
|---|---|---|---|
| `fast` | Samsung T7 500GB SSD | `/mnt/t7` | Docker data, `appdata` (Immich database, configs, Copyparty `hist`), `stacks`, restic cache |
| `primary` | WD_BLACK P10 2TB | `/mnt/main` | `appdata` (Immich photos, Garage blocks, Crafty, pics photos and trash), `files`, `shared` |
| `backup` | Seagate IronWolf Pro 6TB (used) | `/mnt/backup` | restic repo, service dumps, logs |

Current layout: the T7 has `roles: [fast, primary]`; the IronWolf has `[backup]`.

## 0. Vet the new drives

Vet each new drive yourself, not on the seller's word: `sudo smartctl -d sat -a /dev/sdX` (power-on hours, reallocated and pending sectors), then a read-only `badblocks` scan. A long `smartctl` self-test aborts through the IronWolf's USB bridge.

- [x] IronWolf: vetted (SMART counters all 0, full read-only `badblocks` scan found no bad blocks). It is plugged into pinas and formatted ext4 (UUID in `host_vars/pinas/vars.yml`).
- [ ] IronWolf (3.5") needs a powered USB-SATA dock (12V).
- [ ] Power and ports: the T7 and the P10 share the Pi's USB current budget (1.6 A on a Pi 5 with a 5 A supply or `usb_max_current_enable=1`; 1.2 A on a Pi 4), and the IronWolf has its own 12 V supply. Put the T7 and the P10 on the two USB 3 ports and the IronWolf on USB 2. With all three plugged in, check `lsusb -t` (separate buses, the driver and speed of each), `dmesg | grep -iE 'usb|uas|reset|over-current|voltage'`, and `vcgencmd get_throttled` (`0x0`, also while the P10 spins up and during the 02:00 backup). If the P10 resets, try `usb-storage.quirks=<vid>:<pid>:u` in `cmdline.txt`; if the budget is exceeded, put it in a self-powered dock.
- [ ] P10 (WD_BLACK P10, 2.5", bus-powered, USB 3.2 Gen 1): vet it before it holds photos. WD publishes no failure rate, and it may be SMR. It must not hold the only copy or the restic repository.
  - Done: SMART and `smartctl -t long` work through its bridge; a full read-only `badblocks -b 4096` scan found 8 bad blocks in 4 small spots (13 pending sectors, 0 reallocated), which were overwritten ([storage.md](../docs/storage.md#drive-damage-and-wear)); a full-surface long test then passed.
  - Open: pending still reads 13 until the drive recounts on its next scan. Run `smartctl -t offline`, then read pending again: a count that stays or rises means the repair failed. Also write 100 GB or more in one run and watch whether the speed collapses (SMR).
  - Until 2026-11-24, watch pending and reallocated in Scrutiny (a rise means new bad blocks), then run `smartctl -t long` again.
  - Keep it for `primary` only if, on that date, pending is 0 or unchanged, reallocated is small and stable, no new bad block has appeared and the second long test passes. Otherwise replace it; plan to buy a replacement either way.

## 1. Backup drive swap (low risk, first)

- [ ] Format the IronWolf as ext4 on the host and note its UUID.
- [ ] Stop whatever holds the old backup drive open: `docker compose down` in `/opt/services/backup-status` (it mounts the repository and logs), then `sudo systemctl stop mnt-backup.automount mnt-backup.mount` (docs/storage.md "Detach a drive"), and plug in the new one. The drive's UUID changes, so a container that kept the old mount shows nothing until it is recreated; the deploy below recreates it.
- [ ] Set the `uuid:` of the `backup` entry in `drives` to the new drive (mount stays `/mnt/backup`).
- [ ] `just deploy storage,backup --limit <host>`. The storage role updates the fstab line for `/mnt/backup` and mounts the new drive; the backup role runs `restic init` on it.
- [ ] After the 02:00 `backup-local` cron job (or `/opt/services/scripts/backup-restic-local.sh` by hand), check `restic snapshots` and `restic check` on the new repo.
- [ ] The new repository starts empty: its history begins with the first backup, and the old history stays on the old drive. To carry it over instead, copy the repository first (`rsync -aHAX` of `restic-repo` with nothing writing to it, then `restic check`), or use the second-repository method in [backups.md](../docs/backups.md#offline-copy-on-a-second-drive).
- [ ] Keep the old drive, unplugged or mounted at another path (a `drives` entry with no `roles`), until 2-3 verified snapshots exist on the new one.

## 2. Primary drive and fast/primary split

- [ ] Format the P10 as ext4. In `drives`, add `mount: /mnt/main`, `roles: [primary]` and change the T7 to `roles: [fast]`.
- [ ] `just deploy storage --limit <host>` mounts `/mnt/main`. The bulk folders in `appdata` (`primary_appdata_dir`), `files` and `shared` come from the rsync below and from the service roles.
- [ ] Stop the services that write to the bulk folders, `files` and `shared` (`cd /opt/services/<service> && docker compose down` for Immich, Copyparty, Garage, Crafty and pics; their only data on the T7 is what is copied).
- [ ] Copy: `rsync -aHAX /mnt/t7/appdata/<service>/<part>/ /mnt/main/appdata/<service>/<part>/` for each bulk part (Immich `photos`, Garage `data`, Crafty, pics `photos` and `trash`), the same for `files` and `shared`. Databases, Docker and config directories stay on the T7.
- [ ] Run no full `just deploy` between changing `drives` and finishing the copy: the service roles would recreate Immich and Copyparty on the empty `/mnt/main`. Deploy `storage` only until the copy is done.
- [ ] `just deploy`, then check Immich. Copyparty re-scans its index on the first start; that is expected.
- [ ] After a good backup and a check that the copies match (`diff -rq` or file counts and sizes), delete the old folders from the T7 (the bulk parts, `files`, `shared`): left behind they are backed up twice and fill the SSD.
- [ ] Docker's images and layers stay on the root drive unless `docker_data_root` is set ([storage.md](../docs/storage.md#dockers-own-storage)); the table above does not assume it. Setting it means Docker does not start when the T7 is missing.

## 3. Backup follow-up after the split

The default `restic_local_rules` lists the `primary` and `fast` mounts as separate paths. While both roles are on the T7 that is one path. Once they are different drives it is two, so the first backup starts a new restic snapshot group ([backups.md](../docs/backups.md#choosing-what-is-backed-up)).

- [ ] After that backup, list the groups with `restic snapshots --group-by host,paths`, then remove the old group's snapshots by hand (`restic forget <snapshot-id> --prune`). The retention policy never touches a group that no longer grows.

## 4. Encryption (optional, after steps 1 to 3)

Do this only once the new repository has verified snapshots and the old snapshot group is gone, and one folder at a time ([encryption.md](../docs/encryption.md#set-up-a-folder)). Doing it during step 2 would move the data twice.

- [ ] Pick the folders ([encryption.md](../docs/encryption.md#which-folders-to-list)); they must sit under `/mnt/main` or `/mnt/t7`, which the default backup rules cover. To encrypt `service_dumps_dir` as well, add it to `restic_local_extra_rules`.
- [ ] Decide on `/mnt/t7/appdata`: it holds Immich's Postgres, which would then run on the encrypted view. `docker_data_root` must stay outside every listed folder.
- [ ] After each reboot of pinas, nothing is backed up and the encrypted services stay down until someone runs `sudo /opt/services/scripts/unlock.sh`. Point `unlock_alert_to` at a destination on a host that stays up so a locked pinas raises an alert.
- [ ] After the first backup of each encrypted folder, check that the snapshot holds its `gocryptfs.conf`.

## 5. Retire the old 500GB HDD

- [ ] Use it as an offline copy: [backups.md](../docs/backups.md#offline-copy-on-a-second-drive).
- [ ] Unplug the drive and store it elsewhere.

## Not done on purpose

Deduplication is off: in-place edits through the mounted Copyparty volume are a main use, and hardlinks would share content between paths. Reflinks need btrfs.
