# Storage: drive roles

Drives are listed per host, in `host_vars/<host>/vars.yml` (`group_vars/all/vars.yml` sets `drives: []` for hosts that list none). Each entry has `uuid`, `mount`, `fstype` and `options`, and optionally `roles:`, the roles it fills. One drive can hold several roles. Each role is claimed by at most one drive per host; the deploy fails on a duplicate claim or an unknown role name. Hosts in the `nas` group must claim all three roles.

| Role | Holds |
|---|---|
| `fast` | Random-IO data (Docker, Immich database, configs) and caches (restic cache, Copyparty `hist`) |
| `primary` | Bulk data (photos, files) |
| `backup` | The restic repo, service dumps, logs |

Service paths come from `fast_drive`, `primary_drive` and `backup_drive`, worked out from `drives` in `group_vars/all/derived.yml`. A role nobody claimed is an empty string. Giving a role its own drive later moves that role's paths to the new mount point, and you copy the data there once.

## Examples

A general server that uses only its microSD card needs no `drives` entry. A general server with one USB drive for app data and no roles:

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

## Using the microSD card for fast or primary

A `drives` entry with no `uuid` is a folder on the microSD card; nothing goes in fstab:

```yaml
drives:
  - { mount: /srv/nas, roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

The `backup` role needs an entry with a `uuid`, or the deploy fails. Downsides of the card: the Immich database wears it out, and one card failure loses the OS and the data together.

## Plugged-in USB drives (`/drives`)

Set `usb_automount_enabled: true` (on in `group_vars/nas`, off elsewhere) and any USB drive or card reader you plug in appears in Copyparty under `/drives/<label>`. A camera's SD card in a reader works. The host mounts it at `/run/media/system/<label>`.

- It is read-only. To change or delete files on it, set `usb_automount_writable: true`.
- Programs on it cannot be run.
- Drives listed in `drives` never appear here. A wrong `uuid` there means that drive is also mounted a second time.
- After unplugging, its empty folder stays until the next reboot or up to a day. Unplugging a writable drive without unmounting can corrupt it.
- Re-deploy to apply: `just deploy storage,copyparty`.

## Adding, replacing or retiring a drive

To add or replace a drive:
1. Format it and add or point a `drives` entry at it (a new `uuid`, on the same `mount` or a new one, with `roles` updated).
2. `just deploy storage`.
3. Copy the data over, for example `rsync -aHAX`.

To retire a drive, delete its entry. The role only adds fstab lines, so remove the old line from `/etc/fstab` by hand (and `sudo umount` it); nothing is unmounted or deleted for you.

The step-by-step plan for the next drive upgrade is in [plans/drive-migration.md](./plans/drive-migration.md). A backup drive that drops out and comes back is covered in [backups.md](./backups.md#if-the-backup-drive-disconnects).

## Docker's own storage

<a id="dockges-storage-rule"></a>

Docker keeps images, layers and anonymous volumes under `/var/lib/docker` and `/var/lib/containerd`, on the microSD card unless you move them. Docker 29 stores image layers through containerd, and Docker's `data-root` setting does not move those, so both are set together.

**The rule: state lives in bind mounts under a drive role, never in Docker's own storage.** Anything in Docker's storage can then be deleted and re-created (images re-pull, containers are recreated by `just deploy`). New services follow the same rule.

### Put it on a drive

1. Add the drive to `drives` in the host's `host_vars` and deploy it (`just deploy storage`).
2. In `host_vars/<host>/vars.yml` set `docker_data_root: "/mnt/t7/docker-root"` (see `group_vars/all/vars.yml.example`).
3. Stop Docker and containerd by hand (`docker.socket` too, or socket activation restarts Docker mid-change):
   ```bash
   sudo systemctl stop docker.service docker.socket containerd.service
   ```
4. `just deploy common --limit <host>`. This writes `data-root` into `/etc/docker/daemon.json`, `root = ".../containerd"` into `/etc/containerd/config.toml`, and a `RequiresMountsFor=` drop-in for both services, so neither starts before the drive is mounted.
5. `sudo systemctl start containerd.service docker.service`.
6. `just deploy --limit <host>`, so compose pulls the images and recreates the containers.
7. When the stacks are healthy, delete the old contents of `/var/lib/docker` and `/var/lib/containerd` to free the microSD.

To go back, set `docker_data_root: ""` and repeat the steps. Nothing is copied; do not `rsync` layers (overlay whiteouts, hardlinks and extended attributes copy badly). The old directory stays as unused space.

Stop the services by hand: Ansible restarts a service only when a task reports a change, so a run that failed after editing the file does not restart it on the next run.

### Check after a reboot with the drive unplugged

With `docker_data_root` on a `nofail` drive, a missing drive keeps Docker from starting: `systemctl is-active docker containerd` says `inactive`, and neither runs from a directory on the microSD.

### Gitea runner registration

The runner keeps its registration in `gitea_runner_data_dir` (on the fast drive), a bind mount. A new directory starts empty and registers again with the token from the vault. The old registration then shows as an offline runner in Gitea (Site Administration, Actions, Runners); delete it there.

### Leftover volumes

`docker volume ls` can list volumes from older project names. Check that no container mounts one (`docker ps -a --filter volume=<name>`), then `docker volume rm <name>`. Do not use `docker volume prune -a`: it also removes named volumes of stopped containers, such as `immich_model-cache`.
