# Storage: drive roles

Drives are listed per host, in `host_vars/<host>/vars.yml` (`group_vars/all/vars.yml` sets `drives: []` for hosts that list none). Each entry has `uuid`, `mount`, `fstype`, `options` and, optionally, the `roles:` it fills. One drive can hold several roles. Each role is claimed by at most one drive per host. The storage role runs on every server and its assert fails the deploy on duplicate claims or unknown role names. Hosts in the `nas` group must claim all three roles.

| Role | Holds |
|---|---|
| `fast` | Random-IO data (Docker, Immich database, configs) and caches (restic cache, Copyparty `hist`) |
| `primary` | Bulk data (photos, files) |
| `backup` | The restic repo, service dumps, logs |

Service paths come from `fast_drive`, `primary_drive` and `backup_drive`, worked out from `drives` in `group_vars/all/derived.yml`. A role nobody claimed is an empty string. When roles share a drive nothing changes on disk. Adding a dedicated drive for a role later moves that role's paths to the new mount point, and you move the data there once.

## Examples

A general server with only the microSD needs no `drives` at all. With one USB drive for app data and no roles:

```yaml
drives:
  - { uuid: "1111-AAAA", mount: /mnt/data, fstype: ext4, options: "defaults,nofail" }
```

A one-drive NAS:

```yaml
drives:
  - { uuid: "...", mount: /mnt/t7, fstype: ext4, options: "defaults,nofail",
      roles: [fast, primary, backup] }
```

A three-drive NAS (fast SSD, slow bulk drive, backup target):

```yaml
drives:
  - { uuid: "...", mount: /mnt/t7,     fstype: ext4, options: "defaults,nofail", roles: [fast] }
  - { uuid: "...", mount: /mnt/p10,    fstype: ext4, options: "defaults,nofail", roles: [primary] }
  - { uuid: "...", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

Keep `nofail` on every drive so a missing drive does not stop the Pi booting.

## Using the microSD card as fast or primary storage

An entry with no `uuid` is a plain directory on the root filesystem (the microSD card). The storage role creates it and never touches fstab:

```yaml
drives:
  - { mount: /srv/nas, roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

The `backup` role cannot go on such an entry (the deploy fails): a backup on the card holding the data protects against nothing. Trade-offs of putting data on the card: the Immich database writes constantly and wears a card out, and one card failure then takes the OS and the data together. The same entry works for any host, so a Pi with no extra drive can run on the card until you add one.

## Extra drives (no role)

A drive that fills no role is "extra". Two kinds, both listed under `/drives` in Copyparty and never including a role drive (the backup drive holds unencrypted database dumps, so it must not be browsable):

- **A `drives` entry without `roles:`.** Mounted through fstab like the others. Copyparty binds it at `/drives/<last part of mount>`.
- **Anything plugged in.** With `usb_automount_enabled: true` (on in `group_vars/nas`), a udev rule asks `systemd-mount` to mount every USB filesystem that is not in `drives` and is not the root or boot filesystem. It appears under `/run/media/system/<label>` and in Copyparty as `/drives/usb/<label>`, with no configuration. A camera's SD card in a USB reader just shows up. The rule skips by UUID, so write each `uuid` as `blkid` prints it (FAT UUIDs are upper-case).

Both kinds are **read-only** unless `extra_drives_writable: true` (`group_vars/all/vars.yml`). It sets the `ro` mount option for plugged-in drives, and Copyparty's bind mount and permission for both kinds. Plugged-in drives are made read-only on the host because a Docker `:ro` bind mount does not cover mounts that arrive after the container started (tested). Mounted `nosuid,nodev,noexec`.

An unplugged drive leaves its empty folder until `systemd-tmpfiles` sweeps it (within a day) or the next boot. Unplug without unmounting is what these cards usually get; the mount ends with the device.

To add or replace a drive:
1. Format it and add or point a `drives` entry at it (a new UUID, either on the same mount or a new `mount:` with updated `roles`).
2. `just deploy storage`.
3. Copy the data over, for example `rsync -aHAX`.

To retire a drive, delete its entry. The role only adds fstab lines, so remove the old line from `/etc/fstab` by hand (and `sudo umount` it); nothing is unmounted or deleted for you.

The step-by-step plan for the next drive upgrade is in [plans/drive-migration.md](./plans/drive-migration.md). A backup drive that drops out and comes back is covered in [backups.md](./backups.md#if-the-backup-drive-disconnects).

## Docker's own storage

<a id="dockges-storage-rule"></a>

Docker keeps images, layers and anonymous volumes under `/var/lib/docker` and `/var/lib/containerd`, on the microSD card unless you move them. Docker 29 stores image layers through containerd, and Docker's `data-root` setting does not move those, so both are set together.

**The rule: state lives in bind mounts under a drive role, never in Docker's own storage.** Anything in Docker's storage can then be deleted and re-created (images re-pull, containers are recreated by `just deploy`). New services follow the same rule.

### Put it on a drive

1. Mount the drive (add it to `drives` in the host's `host_vars`) and create nothing by hand.
2. In `host_vars/<host>/vars.yml` set `docker_data_root: "/mnt/t7/docker-root"` (documented in `group_vars/all/vars.yml.example`).
3. Stop everything that holds the old location. `docker.socket` is included because socket activation would restart Docker in the middle of the change:
   ```bash
   sudo systemctl stop docker.service docker.socket containerd.service
   ```
4. Deploy the base roles (`just deploy common --limit <host>`). This writes `data-root` into `/etc/docker/daemon.json`, `root = ".../containerd"` into `/etc/containerd/config.toml`, and a `RequiresMountsFor=` drop-in for both services, so neither starts before the drive is mounted.
5. Start them: `sudo systemctl start containerd.service docker.service`.
6. `just deploy` again so compose pulls the images and recreates the containers.
7. When the stacks are healthy, delete the old `/var/lib/docker` and `/var/lib/containerd` contents to free the microSD.

Going back is the same procedure with `docker_data_root: ""`. Nothing is copied: layers are not moved with `rsync`, because overlay whiteouts, hardlinks and extended attributes are where copies go wrong. A change leaves the old directory behind as unused space.

Run the stop step by hand rather than relying on handlers: Ansible only restarts a service when a task reports a change, so a run that failed after editing the file never restarts it on the next run.

### What was tested

On pi5 (2026-10-23), with a directory on the microSD standing in for a drive: setting `docker_data_root` moved `Docker Root Dir` and containerd's `root`, a pulled image's layers landed under the data root, removing the setting reverted both, and a second deploy changed nothing. **Not yet tested:** that a missing `nofail` drive keeps Docker from starting. Test it after the drive move: reboot pi5 with the drive unplugged; `systemctl is-active docker containerd` must say `inactive`, not run on a directory on the microSD.

### Gitea runner registration

The runner's registration used to be an anonymous Docker volume. It is now a bind mount (`gitea_runner_data_dir`, on the fast drive), so Docker keeps no state of its own. Nothing needs copying when you deploy this on a host that already ran the old runner: the runner starts with an empty directory and registers again with the token from the vault. The old registration then shows as an offline runner in Gitea's admin page (Site Administration, Actions, Runners); delete it there.

### Leftover volumes

`docker volume ls` on the Pi 4 shows volumes from older project names. Check that no container mounts one (`docker ps -a --filter volume=<name>`), then remove it by name with `docker volume rm`. Do not use `docker volume prune -a`: it also removes named volumes whose containers happen to be stopped, such as `immich_model-cache`.
