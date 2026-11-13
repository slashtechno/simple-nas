# Storage: drive roles

You list drives per host in `host_vars/<host>/vars.yml` (`drives: []` if none). The deploy's `storage` step mounts them and makes the ansible user the owner of each drive's top folder. It runs everywhere, and `storage_enabled: false` skips it on a host that mounts its drives another way.

| Field | Meaning |
|---|---|
| `mount` | The drive's mount point (required) |
| `uuid` | The drive's UUID ([read it](#preparing-a-drive)). No `uuid`: a folder on the root drive ([below](#using-the-root-drive-for-fast-or-primary)) |
| `fstype` | Filesystem, default `ext4` |
| `reserved_percent` | Optional, ext2/3/4 only: the share kept for root (`tune2fs -m`, ext4's default is 5). Left out, the drive is not touched. Needs a `uuid`. `1` is usual on a data drive ([why](#reserved-space)) |
| `options` | Mount options, default `defaults` |
| `roles` | The roles the drive fills. None means only mounted |

| Role | Holds |
|---|---|
| `fast` | A service's own state (`appdata/<service>`: databases, configs, sessions), your Dockge `stacks/` and the restic cache |
| `primary` | Bulk data (`appdata/<service>`: photos, Garage's object blocks, Crafty's worlds) and your files in Copyparty (`shared/`) |
| `backup` | The restic repo, service dumps, logs |

To browse a drive, or one folder of it, in Copyparty: [add a folder](./services.md#add-a-folder-or-a-login) with its `dir`.

One drive can hold several roles. Each role is claimed by at most one drive per host (a duplicate claim or an unknown role fails the deploy). Service paths come from `fast_drive`, `primary_drive` and `backup_drive`, worked out from `drives`. Giving a role its own drive later moves that role's paths, and you copy the data once ([Adding, replacing or retiring a drive](#adding-replacing-or-retiring-a-drive)).

## What lives where

Each service keeps its data in `appdata/<service>`. Services with more than one directory use one subfolder for each, for example `appdata/immich/postgres` and `appdata/immich/photos`. State goes on the `fast` drive. Bulk data goes on the `primary` drive. If one drive has both roles, the two `appdata` folders are the same folder.

Your own files have plain names: `stacks` and `shared`. Mount points below are examples. Yours are the `mount` values. Most paths are settings in `group_vars/all/defaults-data-dirs.yml`. `services_dir` and `docker_data_root` are in `defaults.yml`. The restic cache is in `roles/backup/defaults/main.yml`.

```
/mnt/fast/                      fast drive
├─ appdata/<service>/           fast_appdata_dir: each service's state (databases, configs, sessions)
├─ stacks/<stack>/              your Dockge stacks: a compose.yaml and its data each
└─ restic-cache/                restic's cache
/mnt/primary/                   primary drive
├─ appdata/<service>/           primary_appdata_dir: each service's bulk data (Immich's photos, Garage's blocks, Crafty, pics' photos and trash)
└─ shared/                      your files in Copyparty (a folder each)
/mnt/backup/                    backup drive: restic repository, dumps, logs
/opt/services/<service>/        root drive: the compose.yaml and .env Ansible generates (overwritten each deploy)
/var/lib/docker/                root drive: Docker's images and layers (movable, see "Docker's own storage")
```

## Examples

A host needs a drive for each role its enabled services use. An unclaimed role fails the deploy with a message naming it. A host needs `backup` where `backup_local_enabled` is true ([backups.md](./backups.md)). The root drive (the SD card, USB or NVMe drive the OS boots from) is not listed.

One USB drive for everything (`[fast, primary, backup]`), or for apps and backups (`[fast, backup]`). Immich, Garage, Crafty, pics and Copyparty's folders keep data on the `primary` drive. A host without that role cannot run them. The backup drive needs a `uuid`. A backup on the drive that holds the data is lost with it: fine for replaceable data, and `backup_cloud_enabled: true` adds an offsite copy.

```yaml
drives:
  - { uuid: "1111-AAAA", mount: /mnt/data, roles: [fast, backup] }
```

An SSD for apps and files plus a backup drive:

```yaml
drives:
  - { uuid: "...", mount: /mnt/data,   roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

A three-drive NAS (fast SSD, bulk drive, backup target):

```yaml
drives:
  - { uuid: "...", mount: /mnt/data,   roles: [fast] }
  - { uuid: "...", mount: /mnt/bulk,   roles: [primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

### How a drive is mounted

Each drive mounts through a systemd automount. The first access to the path mounts it. A missing drive makes access fail after 30 seconds instead of letting a container write to the root drive. The reboot after the first deploy arms this.

<details>
<summary>The fstab options and what each does</summary>

The role adds `x-systemd.automount,x-systemd.device-timeout=30s` to each drive's `options`, and `nofail` unless yours already has it.

- **Automount:** at boot systemd puts a placeholder filesystem on the mount point and mounts the real drive on first access. A missing drive makes that access wait up to 30 seconds, then fail with `No such device`. After it returns, the next access mounts it, with no script or udev rule.
- **`nofail`, no idle timeout:** `nofail` keeps a drive that fails to mount from stopping a headless host booting. The role leaves out `x-systemd.idle-timeout` because it would unmount a quiet drive and a running container would keep its dead mount.
- **Armed at boot:** `daemon-reload` generates the units, but only a boot arms them. Until then the drive is a plain mount.
- **`systemctl status`:** `mnt-data.automount` is `active (waiting)` and `mnt-data.mount` inactive until something opens the path. `df` shows the drive only after that.
- **Remount by hand:** `sudo systemctl restart mnt-data.automount`. systemd gives up after five failed mounts within 10 seconds (a broken filesystem does that), leaving a plain folder.
- **Backups:** the scripts run `mountpoint -q <mount>/.` first. The trailing `/.` opens the path, which mounts the drive or fails. Without it `mountpoint` succeeds on the placeholder of a missing drive.

</details>

## Preparing a drive

For a drive new to the host, before it goes in `drives`. Run on the host.

1. **Identify it.** `lsblk -o NAME,SIZE,MODEL,SERIAL,FSTYPE`. Letters such as `sdc` change when you replug drives. Check the model and serial against the drive's label before you wipe it: `sudo smartctl -i -d sat /dev/sdX` (`-d sat` makes it work through a USB adapter). Give every command the `/dev/disk/by-id/...` path, or a letter you just re-checked.
2. **Look before wiping.** A second-hand drive can hold files: `sudo mount -o ro /dev/sdX1 /mnt/check` (`-t ntfs-3g` for NTFS), `sudo ls -la /mnt/check`, `sudo umount /mnt/check`.
3. **Vet a used drive** with SMART and a read-only `badblocks` scan ([Drive damage and wear](#drive-damage-and-wear)).
4. **Partition and format** (this wipes the drive):

   ```bash
   sudo wipefs -a /dev/sdX1                                   # skip if the drive has no partition yet
   sudo parted -s /dev/sdX mklabel gpt mkpart data ext4 1MiB 100%
   sudo mkfs.ext4 -L <label> -m 0 /dev/sdX1
   ```

   `-m 0` drops ext4's 5% root reserve, which a data or backup drive does not need. The backup scripts refuse to run on a full drive ([backups.md](./backups.md#what-runs-automatically)).
5. **Read the UUID** with `sudo blkid /dev/sdX1` (`lsblk` can lag) and put it in the `drives` entry.

## Adding, replacing or retiring a drive

1. Prepare the drive ([above](#preparing-a-drive)). A drive bought as exFAT or NTFS will not mount until formatted ext4. Add or point a `drives` entry at it: a new `uuid`, on the same or a new `mount`, with `roles` updated. If the mount point stays, [detach the old drive](#detach-a-drive) first.
2. `just deploy storage --limit <host>`.
3. Copy the data over, for example `rsync -aHAX` ([what the flags mean](./glossary.md#commands)), with the services using it stopped (a database copied while running is corrupt). If the old drive died, restore from a backup instead ([backups.md](./backups.md#restore-files)).
4. Recreate the containers that use the drive. A container keeps its old mount until you recreate it, and a deploy skips a container whose compose file and image did not change.
   - In each project under `/opt/services` that uses the drive, run `docker compose up -d --force-recreate`.
   - Include `backup-status`, which uses the restic repository.

To retire a drive, remove its entry. The role never removes an fstab line: remove it by hand and `sudo umount` the drive.

A backup drive that drops out and returns: [backups.md](./backups.md#if-the-backup-drive-disconnects).

## Detach a drive

The unit name is the mount path with `/` as `-` (`/mnt/backup` is `mnt-backup`). Replace `sdX` with the device from `lsblk`.

1. Stop whatever uses it: running backups (`pgrep -a restic`) and the containers that bind it (`docker compose down` in each project under `/opt/services` that uses it, including `backup-status`). A container keeps its own copy of the mount, which `findmnt` on the host does not show.
2. Stop the automount, then the mount (the next access undoes an unmount): `sudo systemctl stop mnt-backup.automount mnt-backup.mount`.
3. Check nothing holds it: `findmnt /mnt/backup` and `sudo grep -l sdX1 /proc/*/mountinfo` print nothing. If one does, `sudo lsof /dev/sdX1` names the holder.
4. `sync`, then `sudo udisksctl power-off -b /dev/sdX`. Unplug when the activity light stops.

To mount it again, plug it in, `sudo systemctl start mnt-backup.automount`, open the path (`ls /mnt/backup/.`), and recreate the containers that bind it. To attach it to another host, remove its `drives` entry and fstab line first.

## Move one service's data

Each service's data directories are settings in `group_vars/all/defaults-data-dirs.yml`. You can set any path. Two rules apply. The deploy refuses a data directory that is the same as, or inside, another one (`ansible/check_data_dirs.yml`). A backup or a teardown of the outer folder would take the inner one with it. The local backup must also cover the new path.

1. Set its data directory settings in `host_vars/<host>/vars.yml` to paths under a drive with a role. The default local backup (`restic_local_rules`) covers only the `primary` and `fast` drives.
2. `cd /opt/services/<service> && docker compose down`.
3. `sudo rsync -aHAX <old path>/ <new path>/` ([flags](./glossary.md#commands)).
4. `just deploy <service> --limit <host>` (not `storage`), check it works, then remove the old copy by hand.

## A drive that will not mount

Signs: `systemctl status mnt-<name>.mount` says `probably corrupted filesystem`, and `dmesg | grep EXT4` shows `error loading journal`, usually after the drive dropped off USB mid-write. systemd then gives up the automount, so the mount point is a plain folder and containers write to the root drive. On the host:

1. Stop the containers that use the drive.
2. Check read-only: `sudo e2fsck -fn /dev/disk/by-uuid/<uuid>`.
3. Repair: the same with `-fy`. The repair discards a journal that fails its checksum, losing writes since the last good mount. For worse damage, [restore from backup](./backups.md).
4. Mount: `sudo systemctl reset-failed mnt-<name>.mount mnt-<name>.automount && sudo systemctl restart mnt-<name>.automount`, then `ls <mount>` to check.
5. Recreate the containers (step 4 of [Adding, replacing or retiring a drive](#adding-replacing-or-retiring-a-drive)). What they wrote to the root drive sits under the mount point. Remove it after `umount`.

exFAT has no journal: `fsck.exfat -n /dev/sdX1` (or `diskutil verifyVolume` on a Mac) only reads. `-y` repairs.

## With a drive missing

- **At boot:** the host starts. Opening a path on the missing drive fails with `No such device` after 30 seconds. Containers whose data is on it fail to start, and nothing is written under the mount point.
- **Drive returns:** the next access mounts it. Containers that failed to start or lost their mount stay down until restarted: `just deploy '' --limit <host>` or `docker compose up -d`.
- **Unplugged while running:** systemd unmounts it. If a process still holds it, every access returns an I/O error until `sudo umount -l <mount>` or a reboot.
- **Backup drive only:** services keep running. The backup scripts refuse to run until it is back.

## Reserved space

An ext4 drive keeps a share of its blocks for root. Below that share, programs running as other users (a database in a container) fail with "No space left on device" while `df` still shows free space. On a data drive, set `reserved_percent: 1` on its entry. The deploy applies it at once, with no remount, and `5` puts it back.

<details>
<summary>What the number means and how to read it</summary>

- **The number** is a percentage of the whole drive: 5 keeps about 23 GiB on a 466 GiB filesystem, 1 about 4.7 GiB, 0 nothing.
- **Which value:** a data drive holds no system files, so 1 is enough. A drive holding the system keeps the default. The reserve also leaves root room to clean up after a drive fills.
- **Read it:** `sudo tune2fs -l /dev/disk/by-uuid/<uuid> | grep -i "block count"` (reserved blocks divided by block count).
- A full drive is the problem, not the reserve: a lower reserve gives back only the margin. Free space as well.

</details>

## Using the root drive for fast or primary

A `drives` entry with no `uuid` is a folder on the root drive. Nothing goes in fstab:

```yaml
drives:
  - { mount: /srv/data, roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, roles: [backup] }
```

The `backup` role needs an entry with a `uuid`: a backup on the root drive dies with it. The Immich database also wears out an SD card, and one root drive failure then loses the OS and the data together.

## Plugged-in USB drives (`/drives`)

Set `usb_automount_enabled: true` in the host's `host_vars` (off by default) and any USB drive or card reader you plug in appears in Copyparty under `/drives/<label>` (host path `/run/media/system/<label>`). Apply with `just deploy storage,copyparty`.

- **Read-only** unless `usb_automount_writable: true`. Nothing on it can run (`nosuid,nodev,noexec`). The host checks writable drives first (`fsck -y`, which repairs), and they appear when the check ends.
- **Unmount before unplugging**, or a writable drive can corrupt: `sudo systemctl stop 'run-media-system-<label>.mount'` (`systemctl list-units 'run-media-*'` shows the name), then power off as in [Detach a drive](#detach-a-drive) step 4.
- Copyparty runs as root, so files it creates on ext4 belong to root. exFAT, FAT and NTFS store no owners.
- Drives listed in `drives` never appear here. A wrong `uuid` there means that drive is also mounted a second time. On a desktop OS (Ubuntu Desktop) keep it off: the desktop's own automounter also mounts them.

## Docker's own storage

Docker keeps images, layers and anonymous volumes under `/var/lib/docker` and `/var/lib/containerd` on the root drive unless you move them. **The rule: state lives in bind mounts under a drive role, never in Docker's own storage.** Anything in Docker's storage can then be removed and re-created (images re-pull, `just deploy` recreates containers). New services follow it too.

<details>
<summary>Put Docker's storage on a drive, go back, leftover volumes, runner registration</summary>

Docker 29 stores layers through containerd, and `data-root` does not move those, so you set both together.

1. Add the drive to `drives` and `just deploy storage`.
2. Set `docker_data_root: "/mnt/data/docker-root"` in `host_vars/<host>/vars.yml`.
3. Stop Docker and containerd by hand (`docker.socket` too, or socket activation restarts Docker mid-change): `sudo systemctl stop docker.service docker.socket containerd.service`. A deploy restarts them only when it writes their config, so a run that failed after writing it leaves the old settings running.
4. `just deploy common --limit <host>` writes `data-root` into `/etc/docker/daemon.json` and `root = ".../containerd"` into `/etc/containerd/config.toml`. With the drive missing, Docker and containerd fail to start instead of creating their directories on the root drive.
5. `sudo systemctl start containerd.service docker.service`, then `just deploy '' --limit <host>` so compose pulls the images and recreates the containers.
6. When the stacks are healthy, remove the old contents of `/var/lib/docker` and `/var/lib/containerd`.

To go back, set `docker_data_root: ""` and repeat. Do not `rsync` layers (whiteouts, hardlinks and extended attributes copy badly). The old directory stays as unused space, and its root-owned files make the backup exit with errors until you `sudo rm -r` it or add `- <old docker_data_root>` to `restic_local_extra_rules`.

**Gitea runner registration:** the runner keeps it in `gitea_runner_data_dir` (fast drive). A new directory registers again with the vault token, and the old registration shows as an offline runner in Gitea (Site Administration, Actions, Runners). Remove it there.

**Leftover volumes:** `docker volume ls` can list volumes from older project names. Check no container mounts one (`docker ps -a --filter volume=<name>`), then `docker volume rm <name>`. Never `docker volume prune -a`: it also removes named volumes of stopped containers, such as `immich_model-cache`.

</details>

## Drive damage and wear

Read the counters with `sudo smartctl -A -d sat /dev/disk/by-id/<drive>`, on the whole-disk entry, not `-part1` (`ls -l /dev/disk/by-id/` lists the names). [Scrutiny](./services.md#scrutiny-drive-health) graphs them.

- **Damage:** `Reallocated_Sector_Ct` (5), `Current_Pending_Sector` (197) or `Offline_Uncorrectable` (198) above 0 are sectors the drive could not read. A small, stable count can be kept. A count that keeps rising, new bad blocks after a repair, or a failed `smartctl -t long` mean replace the drive. `UDMA_CRC_Error_Count` (199) points at the cable or USB bridge.
- **Power:** several drives dropping off USB together (`over-current` in `dmesg`) is the usual cause of a corrupt filesystem on a bus-powered host ([If the backup drive disconnects](./backups.md#if-the-backup-drive-disconnects)).
- **Wear (hard drives):** `Load_Cycle_Count` (193) divided by `Power_On_Hours` (9) gives the head-parking rate. About 15 an hour or less is normal, and the maker's datasheet gives the rated total (often 300,000 to 600,000 on a 2.5" drive). If it is high, `hdparm -B 254` stops aggressive parking. Some USB bridges ignore it.

<details>
<summary>Find and repair bad sectors</summary>

1. **Scan read-only** with the drive unmounted: `sudo systemd-run --unit=scan /usr/sbin/badblocks -b 4096 -sv -o /var/tmp/bad.txt /dev/disk/by-id/<drive>`. Never `-w`. It takes hours on a 2 TB drive. `systemd-run` keeps it going when SSH ends. `journalctl -u scan -f` shows progress, and the numbers also land in `/var/tmp/bad.txt`. Each number is a 4 KiB block counted from the start of the whole disk.
2. **Find the files they hit before the repair.** Mount the drive read-only (`sudo mount -o ro /dev/disk/by-id/<drive>-part1 /mnt/check`) and read everything: `sudo find /mnt/check -xdev -type f -exec cat {} + >/dev/null`. An unreadable file prints its path with `Input/output error`. Restore it from backup. A clean pass shows every file can be read. It does not show that its content is right: compare `sha256sum` lists with a second copy and test archives with `7z t` or `unzip -t`.
3. **Overwrite each bad block no file needs.** Unmount the drive first (a block outside every file can still hold filesystem metadata, so run the filesystem check afterwards: `sudo e2fsck -fn /dev/disk/by-uuid/<uuid>` for ext4): `sudo dd if=/dev/zero of=/dev/disk/by-id/<drive> bs=4096 seek=<block> count=1 oflag=direct conv=notrunc`. The drive then repairs or remaps the sector, and what was in the block is gone. Then `smartctl -t long`. It takes hours, and a pass means the whole surface reads.
4. **Keep watching the counters**, and keep nothing on a drive with defects that exists nowhere else ([backups.md](./backups.md)).

</details>

## Checking a drive over USB

A USB-to-SATA bridge hides the drive from the kernel's temperature driver, so read it with `sudo smartctl -d sat -a /dev/sdX` (attribute 194, and Scrutiny reads the same data).

<details>
<summary>Bridge quirks, waking a sleeping drive, temperature</summary>

- **Long self-tests** (`smartctl -t long`) can abort with "Aborted by host" through some bridges. A read-only `badblocks` scan is the alternative.
- **Sleeping drive:** a plain `smartctl -A` spins it up. `smartctl -n standby -A` skips a drive that is asleep.
- **`unsupported field in scsi command`:** the bridge's pass-through is broken. Set a `usb-storage.quirks` kernel option for it, applied at boot (see smartmontools' USB page).
- **Temperature:** check the maker's operating range. A hard drive in a closed enclosure can run near its limit, and a fan lowers it by 10 to 15 °C. To pause a long job such as `badblocks` while it cools, freeze its systemd unit (`systemctl freeze` and `thaw`, and start it with `systemd-run --unit=<name>`). Stopping the unit kills it.

</details>
