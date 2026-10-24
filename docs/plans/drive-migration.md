# Drive migration plan (2 drives to 3 drives)

Waiting on the drive purchases. The NAS moves to pi5 first with the current two drives ([multi-host.md](./multi-host.md#cutover-from-the-pi-4-to-pi5)); the steps below then run on pi5.

Target, in the host's `drives` list (`ansible/host_vars/<host>/vars.yml`; roles are explained in [storage.md](../storage.md)):

| Role | Drive | Mount | Holds |
|---|---|---|---|
| `fast` | Samsung T7 500GB SSD | `/mnt/t7` | Docker data, Immich database, configs, restic cache, Copyparty `hist` |
| `primary` | WD_BLACK P10 2TB | `/mnt/main` | photos, files, collab |
| `backup` | Seagate ST4000NM0033 4TB | `/mnt/backup` | restic repo, service dumps, logs |

Starting layout: the T7 has `roles: [fast, primary]`; the 500GB ST3500418AS has `[backup]`.

## 0. Vet the new drives

Run on each new drive, especially the used ST4000NM0033:

```bash
smartctl -a /dev/sdX        # power-on hours, reallocated and pending sectors
smartctl -t long /dev/sdX   # wait for it to finish, then read smartctl -a again
```

- [ ] ST4000NM0033 (3.5") needs a powered USB-SATA dock (12V).
- [ ] P10 (2.5") is bus-powered. On pi5 the T7 and P10 share a 1.6A USB budget (the 500GB HDD has its own brick); check their combined draw or use a powered hub.

## 1. Backup drive swap (low risk, first)

- [ ] Format the ST4000NM0033 as ext4 on the host and note its UUID.
- [ ] Unmount the old backup drive (`sudo umount /mnt/backup`) and plug in the new one.
- [ ] Set the `uuid:` of the `backup` entry in `drives` to the new drive (mount stays `/mnt/backup`).
- [ ] `just deploy storage,backup --limit <host>`. The storage role updates the fstab line for `/mnt/backup` and mounts the new drive; the backup role runs `restic init` on it.
- [ ] After the 02:00 `backup-local` cron job (or `/opt/services/scripts/backup-restic-local.sh` by hand), check `restic snapshots` and `restic check` on the new repo.
- [ ] Keep the old drive, unplugged or mounted at another path (a `drives` entry with no `roles`), until 2-3 verified snapshots exist on the new one.

## 2. Primary drive and fast/primary split

- [ ] Format the P10 as ext4. In `drives`, add `mount: /mnt/main`, `roles: [primary]` and change the T7 to `roles: [fast]`.
- [ ] `just deploy storage --limit <host>` mounts `/mnt/main` and creates the directory tree.
- [ ] Stop the services that write to `photos`, `files` and `collab` (`cd /opt/services/<service> && docker compose down` for Immich, Copyparty and Gitea).
- [ ] Copy: `rsync -aHAX /mnt/t7/photos/ /mnt/main/photos/`, the same for `files` and `collab`. Databases, Docker and config directories stay on the T7.
- [ ] `just deploy`, then check Immich, Gitea and Copyparty. Copyparty re-scans its index on the first start (its `hist` database starts empty); that is expected.

## 3. Backup follow-up after the split

The default `restic_local_rules` lists the `primary` and `fast` mounts as separate paths. While both roles are on the T7 that is one path. Once they are different drives it is two, so the first backup starts a new restic snapshot group ([backups.md](../backups.md#choosing-what-is-backed-up)).

- [ ] After that backup, list the groups with `restic snapshots --group-by host,paths`, then remove the old group's snapshots by hand (`restic forget <snapshot-id> --prune`). The retention policy never touches a group that no longer grows.

## 4. Retire the old 500GB HDD

- [ ] Use it as an offline copy: plug it in, mount it (for example at `/mnt/offline`), and copy the snapshots into a second repository on it. `restic copy` takes the destination as the repository (`-r`) and the source with `--from-repo`; each repository needs its own password option (the same password file here).
- [ ] Create the second repository once, with the source's chunker settings so the copy deduplicates:

  ```bash
  restic -r /mnt/offline/restic-repo init \
    --password-file ~/.restic-password \
    --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password \
    --copy-chunker-params
  ```

- [ ] Each month, copy new snapshots. Already-copied snapshots are skipped:

  ```bash
  restic -r /mnt/offline/restic-repo copy \
    --password-file ~/.restic-password \
    --from-repo /mnt/backup/restic-repo --from-password-file ~/.restic-password
  ```

- [ ] Unplug the drive and store it elsewhere.

## Not done on purpose

Deduplication is off: in-place edits through the mounted Copyparty volume are a main use, and hardlinks would share content between paths. Reflinks need btrfs.
