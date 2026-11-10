# Storage: drive roles

Drives are listed per host, in `host_vars/<host>/vars.yml`; a host that lists none has `drives: []`. The `storage` role mounts them: it runs everywhere and `storage_enabled: false` skips it on a host whose drives are mounted another way.

Each `drives` entry has these fields:

| Field | Meaning |
|---|---|
| `mount` | Where the drive is mounted (required) |
| `uuid` | The drive's UUID ([how to read it](#preparing-a-drive)). An entry without one is a folder on the root drive ([below](#using-the-root-drive-for-fast-or-primary)) |
| `fstype` | Filesystem, default `ext4` |
| `reserved_percent` | Optional, ext2/3/4 only. The share of the drive kept for root, set with `tune2fs -m` (ext4's default is 5). Left out, the drive is not touched (a value set earlier stays; set `5` to undo). Needs a `uuid`. On a data drive, `1` is usual: a database running as another user gets "No space left" once free space falls below the reserve, while `df` still shows some free ([what the number means](#reserved-space)) |
| `options` | Mount options, default `defaults` |
| `roles` | The roles the drive fills. A drive with no `roles` is only mounted |

- One drive can hold several roles. Each role is claimed by at most one drive per host; the deploy fails on a duplicate claim or an unknown role name.
- Which roles a host needs is under [Examples](#examples).

| Role | Holds |
|---|---|
| `fast` | Random-IO data (Docker stacks, database directories, every other service's config directory) and caches (restic cache, Copyparty `hist`); the full list is the settings in `group_vars/all/defaults-data-dirs.yml` |
| `primary` | Bulk data (photos, files) |
| `backup` | The restic repo, service dumps, logs |

Service paths come from `fast_drive`, `primary_drive` and `backup_drive`, worked out from `drives` in `group_vars/all/derived.yml`. Giving a role its own drive later moves that role's paths to the new mount point, and you copy the data there once.

## What lives where

Mount points below are examples; yours are the `mount` values in `drives`.

```
/mnt/fast/                      fast drive
├─ appdata/<service>/           each service's own data: databases, configs, sessions
├─ stacks/<stack>/              your Dockge stacks: a compose.yaml and its data each
├─ fast/                        Copyparty's /fast volume
└─ restic-cache/                restic's cache
/mnt/primary/                   primary drive
├─ photos/                      Immich's photos
├─ files/, collab/              Copyparty's files
└─ apps/pics/{photos,trash}/    pics
/mnt/backup/                    backup drive: restic repository, dumps, logs
/opt/services/<service>/        root drive: the compose.yaml and .env Ansible generates (overwritten each deploy)
/var/lib/docker/                root drive: Docker's images and layers (movable, see "Docker's own storage")
```

- Every path is a setting in `group_vars/all/defaults-data-dirs.yml`.

## Examples

The rule is the same on every host: a drive claims roles, and service paths follow the roles. A host needs a drive for each role its enabled services use; an unclaimed role fails the deploy with a message naming it, only on a host that enables a service needing it.

- `backup` is needed where `backup_local_enabled` is true ([backups.md](./backups.md)).

Docker's own storage (images, layers) is separate: it stays on the root drive unless `docker_data_root` is set; see [Docker's own storage](#dockers-own-storage).

A host that keeps its apps in a folder on the root drive lists it without a `uuid` ([Using the root drive](#using-the-root-drive-for-fast-or-primary)).

A host with one USB drive for apps and backups (`[fast, backup]`), or for everything including photos (`[fast, primary, backup]`):

- The backup drive must have a `uuid`.
- A backup on the drive that holds the data is lost with it. That is fine for data you can replace; `backup_cloud_enabled: true` ([backups.md](./backups.md)) adds an offsite copy.

```yaml
drives:
  - { uuid: "1111-AAAA", mount: /mnt/data, roles: [fast, backup] }
```

An SSD for apps and files plus a separate backup drive. The root drive (the SD card, USB or NVMe drive the OS boots from) is not listed:

```yaml
drives:
  - { uuid: "...", mount: /mnt/data,     roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

A three-drive NAS (fast SSD, slow bulk drive, backup target):

```yaml
drives:
  - { uuid: "...", mount: /mnt/data,     roles: [fast] }
  - { uuid: "...", mount: /mnt/bulk,    roles: [primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

### How a drive is mounted

The role adds `x-systemd.automount,x-systemd.device-timeout=30s` to each drive's `options` in fstab. It also adds `nofail` unless your `options` already have it.

- **Automount:** at boot systemd puts a placeholder filesystem on the mount point, and mounts the real drive the first time anything opens a path under it. While the drive is missing, that access waits up to 30 seconds and then fails with `No such device`. The mount point is a placeholder, not a plain folder, so a container cannot write to the root drive. After the drive returns, the next access mounts it again, with no script or udev rule.
- **`nofail` and no idle timeout:** `nofail` keeps a drive that fails to mount from stopping a headless host booting. `x-systemd.idle-timeout` is left out because it would unmount a quiet drive, and a running container keeps its old, dead mount.
- **Armed at boot:** `daemon-reload` generates the units, but only the boot arms them. Until the reboot after the first deploy, the drive is a plain mount with no guard against it vanishing.
- **In `systemctl status`:** `mnt-data.automount` is `active (waiting)` and `mnt-data.mount` is inactive until something opens the path. `df` shows the drive only after that.
- **Remount by hand:** `sudo systemctl restart mnt-data.automount`, if systemd gave up on a drive. It does after five failed mount attempts within 10 seconds, which a fast failure such as a broken filesystem reaches; the mount point is then a plain folder until you restart it.
- **Backups:** the backup scripts run `mountpoint -q <mount>/.` before they write anything. The trailing `/.` opens the path: that mounts the drive, or fails after up to 30 seconds so the script refuses to run. Without it `mountpoint` succeeds on the placeholder of a missing drive.

## Reserved space

An ext4 drive keeps a share of its blocks for root. When free space falls below that share, programs running as other users (a database in a container) fail with "No space left on device", while root and `df` still see free space. `df` shows `Avail` 0 and `Use%` 100%.

- **The number** is a percentage of the whole drive. 5 (ext4's default, from the drive's creation) keeps 5%, about 23 GiB on a 466 GiB filesystem (what `df` calls 458G); 1 keeps 1%, about 4.7 GiB; 0 keeps nothing.
- **Which value:** a data drive holds no system files, so 1 is enough; a drive that holds the system keeps the default. The reserve also leaves room for root to clean up after a drive fills.
- **Read the current value:** `sudo tune2fs -l /dev/disk/by-uuid/<uuid> | grep -i "block count"` (reserved blocks divided by block count).
- **Set it with `reserved_percent`** on the drive's entry (the fields table at the top of this page); the deploy changes it only when it differs. It takes effect at once, with no remount, and setting 5 puts it back.
- **A full drive is the problem, not the reserve:** a lower reserve gives back only the margin. Free space as well.

## With a drive missing

- **At boot:** the host starts. Opening a path on the missing drive fails with `No such device` after 30 seconds. Containers whose data is on it fail to start, and nothing is written under the mount point on the root drive.
- **Drive returns:** the next access mounts it. Containers that failed to start, or lost their mount, stay down until restarted: `just deploy '' --limit <host>` or `docker compose up -d`.
- **Unplugged while running:** systemd unmounts the drive. If a process still holds it, the unmount fails and every access returns an I/O error until `sudo umount -l <mount>` or a reboot; the automount does not help there.
- **Backup drive only:** the services keep running. The backup scripts refuse to run until it is back.

## A drive that will not mount

Signs: `systemctl status mnt-<name>.mount` says `probably corrupted filesystem`, and `dmesg | grep EXT4` shows `error loading journal`, usually after the drive dropped off USB mid-write. systemd then gives up the automount ([Remount by hand](#how-a-drive-is-mounted)), so the mount point is a plain folder and containers write to the root drive. On the host:

1. Stop the containers that use the drive.
2. Check read-only: `sudo e2fsck -fn /dev/disk/by-uuid/<uuid>`.
3. Repair: the same with `-fy`. A journal that fails its checksum is discarded, losing writes since the last good mount. For worse damage, [restore from backup](./backups.md).
4. Mount: `sudo systemctl reset-failed mnt-<name>.mount mnt-<name>.automount && sudo systemctl restart mnt-<name>.automount`.
5. Recreate the containers ([step 4 here](#adding-replacing-or-retiring-a-drive)). What they wrote to the root drive sits under the mount point; delete it after `umount`.

exFAT has no journal: `fsck.exfat -n /dev/sdX1` (or `diskutil verifyVolume` on a Mac) only reads.

## Using the root drive for fast or primary

A `drives` entry with no `uuid` is a folder on the root drive (the drive the OS boots from: an SD card, USB or NVMe drive). It is created, and nothing goes in fstab:

```yaml
drives:
  - { mount: /srv/data, roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

The `backup` role needs an entry with a `uuid`, or the deploy fails: a backup on the root drive dies with it. Other downsides: the Immich database wears out an SD card, and one root drive failure loses the OS and the data together.

## Plugged-in USB drives (`/drives`)

Set `usb_automount_enabled: true` in the host's `host_vars` (off by default) and any USB drive or card reader you plug in appears in Copyparty under `/drives/<label>`. A camera's SD card in a reader works. Re-deploy to apply: `just deploy storage,copyparty`.

- **Host path:** `/run/media/system/<label>`.
- **Read-only** unless `usb_automount_writable: true`. Nothing on it can run (`nosuid,nodev,noexec`).
- **Writable drives are checked first** (`fsck -y`, which repairs what it finds) and appear only when the check ends. Read-only drives are not checked.
- **Unmount before unplugging**, or a writable drive can corrupt: `sudo systemctl stop 'run-media-system-<label>.mount'` (`systemctl list-units 'run-media-*'` shows the name), then power off as in step 4 of [Detach a drive](#detach-a-drive). The drive's empty folder stays until the next reboot.
- **Owners:** Copyparty runs as root, so files it creates on an ext4 drive belong to root. exFAT, FAT and NTFS store no owners.
- Drives listed in `drives` never appear here. A wrong `uuid` there means that drive is also mounted a second time.
- On a desktop OS (Ubuntu Desktop) keep it off: the desktop's own automounter also mounts plugged-in drives.

## Preparing a drive

For a drive that is new to the host, before it goes in `drives`. Run on the host.

1. **Identify it.** `lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE` lists the drives. Letters such as `sdc` change when drives are replugged, so before erasing check the model and serial (`sudo smartctl -i -d sat /dev/sdX`) against the label on the drive, and give every command below the `/dev/disk/by-id/...` path or a letter you have just re-checked.
2. **Look before erasing.** A second-hand drive can hold files. Mount it read-only and list everything, hidden folders included: `sudo mount -o ro /dev/sdX1 /mnt/check` (add `-t ntfs-3g` for NTFS), `sudo ls -la /mnt/check`, then `sudo umount /mnt/check`.
3. **Vet a used drive** with SMART and a read-only `badblocks` scan ([Checking a drive over USB](#checking-a-drive-over-usb)).
4. **Partition and format** (this erases the drive):

   ```bash
   sudo wipefs -a /dev/sdX1                                   # skip if the drive has no partition yet
   sudo parted -s /dev/sdX mklabel gpt mkpart data ext4 1MiB 100%
   sudo mkfs.ext4 -L <label> -m 0 /dev/sdX1
   ```

   `-m 0` turns off ext4's 5% reserve for root, which a data or backup drive does not need. The backup scripts already refuse to run at 95% full ([backups.md](./backups.md#what-runs-automatically)).
5. **Read the UUID** with `sudo blkid /dev/sdX1` (`lsblk` can lag behind) and put it in the `drives` entry.

Then `just deploy storage --limit <host>` mounts it.

## Adding, replacing or retiring a drive

To add or replace a drive:

1. Prepare the drive and its entry:
   - Prepare it ([Preparing a drive](#preparing-a-drive)); a drive bought with exFAT or NTFS will not mount until it is formatted ext4.
   - Add or point a `drives` entry at it: a new `uuid`, on the same `mount` or a new one, with `roles` updated.
   - If the mount point stays the same, stop the old drive's units first (`sudo systemctl stop mnt-<name>.automount mnt-<name>.mount`, as in [Detach a drive](#detach-a-drive)) so the new one can take its place.
2. `just deploy storage --limit <host>`.
3. Copy the data over, for example `rsync -aHAX`.
4. Recreate the containers that bind the drive: a container keeps the old mount until it is recreated, and a deploy does not recreate one whose compose file and image are unchanged. Run `docker compose up -d --force-recreate` in each project under `/opt/services` that uses the drive, including `backup-status`, which binds the restic repository.

To retire a drive, delete its entry. The role adds or updates fstab lines and never removes one, so remove the old line from `/etc/fstab` by hand (and `sudo umount` it); nothing is unmounted or deleted for you.

A backup drive that drops out and comes back is covered in [backups.md](./backups.md#if-the-backup-drive-disconnects).

## Checking a drive over USB

A USB-to-SATA bridge hides the drive from the kernel's temperature driver (`drivetemp`).

- **Read the temperature:** `sudo smartctl -d sat -a /dev/sdX` (attribute 194). Scrutiny reads the same data ([services.md](./services.md)).
- **Long self-tests** (`smartctl -t long`) can abort with "Aborted by host" through some bridges. A read-only `badblocks` scan is the alternative.
- **Waking a sleeping drive:** a plain `smartctl -A` spins it up; `smartctl -n standby -A` skips a drive that is asleep.
- **If the bridge answers `unsupported field in scsi command`:** its pass-through is broken. The fix is a `usb-storage.quirks` kernel option for that bridge, applied at boot (see smartmontools' USB page).

Check the drive maker's operating range; a hard drive in a closed enclosure can run near its limit, and a fan on the enclosure lowers it by 10 to 15 °C. Reading the temperature wakes a spun-down drive. To pause a long job such as `badblocks` while a drive cools, freeze its systemd unit (`systemctl freeze` and `thaw`; start it with `systemd-run --unit=<name>`); stopping the unit kills it.

## Move one service's data

Each service's data directories are settings listed in `ansible/group_vars/all/defaults-data-dirs.yml`. To move a service to another drive:

1. Set its data directory settings in `host_vars/<host>/vars.yml` to paths under a drive that has a role. The default local backup (`restic_local_rules`) covers only the `primary` and `fast` drives.
2. Stop the service: `cd /opt/services/<service> && docker compose down`.
3. Copy the data: `rsync -aHAX <old path>/ <new path>/`.
4. `just deploy <service> --limit <host>`, then check it works. Delete the old copy by hand.

## Docker's own storage

Docker keeps images, layers and anonymous volumes under `/var/lib/docker` and `/var/lib/containerd`, on the root drive unless you move them. Docker 29 stores image layers through containerd, and Docker's `data-root` setting does not move those, so both are set together.

**The rule: state lives in bind mounts under a drive role, never in Docker's own storage.** Anything in Docker's storage can then be deleted and re-created (images re-pull, containers are recreated by `just deploy`). New services follow the same rule.

### Put it on a drive

1. Add the drive to `drives` in the host's `host_vars` and deploy it (`just deploy storage`).
2. In `host_vars/<host>/vars.yml` set `docker_data_root: "/mnt/data/docker-root"` (see `ansible/group_vars/all/defaults.yml`).
3. Stop Docker and containerd by hand (`docker.socket` too, or socket activation restarts Docker mid-change). A deploy restarts them only when it writes their config, so a run that failed after writing it leaves them running the old settings until you restart them:
   ```bash
   sudo systemctl stop docker.service docker.socket containerd.service
   ```
4. `just deploy common --limit <host>`. This writes `data-root` into `/etc/docker/daemon.json` and `root = ".../containerd"` into `/etc/containerd/config.toml`. With the drive missing, Docker and containerd fail to start instead of creating their directories on the root drive.
5. `sudo systemctl start containerd.service docker.service`.
6. `just deploy '' --limit <host>`, so compose pulls the images and recreates the containers.
7. When the stacks are healthy, delete the old contents of `/var/lib/docker` and `/var/lib/containerd` to free the root drive.

To go back, set `docker_data_root: ""` and repeat the steps. Nothing is copied; do not `rsync` layers (overlay whiteouts, hardlinks and extended attributes copy badly). The old directory stays as unused space, and its root-owned files make the backup exit with errors until you delete it (`sudo rm -r <old docker_data_root>`) or add `- <old docker_data_root>` to `restic_local_extra_rules`.

### Detach a drive

The unit name is the mount path with `/` as `-` (`/mnt/backup` is `mnt-backup`). Replace `sdX` with the device from `lsblk`.

1. Stop whatever uses the drive: running backups (`pgrep -a restic`) and the containers that bind it (`docker compose down` in each project under `/opt/services` that uses it, including `backup-status`). A container keeps its own copy of the mount, which `findmnt` on the host does not show.
2. Stop the automount, then the mount, because the next access to the path undoes an unmount: `sudo systemctl stop mnt-backup.automount mnt-backup.mount`.
3. Check nothing holds it: `findmnt /mnt/backup` and `sudo grep -l sdX1 /proc/*/mountinfo` print nothing. If either prints something, `sudo lsof /dev/sdX1` names the holder.
4. `sync`, then `sudo udisksctl power-off -b /dev/sdX`. Unplug it once the activity light stops.

To mount it again, plug it in and run `sudo systemctl start mnt-backup.automount`, then open the path (`ls /mnt/backup/.`). Recreate the containers that bind it (step 4 of [Adding, replacing or retiring a drive](#adding-replacing-or-retiring-a-drive)). To attach it to another host, remove its `drives` entry and its fstab line first.

### Gitea runner registration

The runner keeps its registration in `gitea_runner_data_dir` (on the fast drive), a bind mount. A new directory starts empty and registers again with the token from the vault. The old registration then shows as an offline runner in Gitea (Site Administration, Actions, Runners); delete it there.

### Leftover volumes

`docker volume ls` can list volumes from older project names. Check that no container mounts one (`docker ps -a --filter volume=<name>`), then `docker volume rm <name>`. Do not use `docker volume prune -a`: it also removes named volumes of stopped containers, such as `immich_model-cache`.
