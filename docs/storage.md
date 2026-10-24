# Storage: drive roles

Drives are listed per host, in `host_vars/<host>/vars.yml`; a host that lists none has `drives: []`. Each entry has `uuid`, `mount`, `fstype` and `options`, and optionally `roles:`, the roles it fills. A drive with no `roles` is only mounted. One drive can hold several roles. Each role is claimed by at most one drive per host; the deploy fails on a duplicate claim or an unknown role name. Which roles a host needs is under [Examples](#examples). Find a drive's UUID on the host with `lsblk -o NAME,SIZE,FSTYPE,UUID,MOUNTPOINTS`.

| Role | Holds |
|---|---|
| `fast` | Random-IO data (Docker, Immich database, configs) and caches (restic cache, Copyparty `hist`) |
| `primary` | Bulk data (photos, files) |
| `backup` | The restic repo, service dumps, logs |

Service paths come from `fast_drive`, `primary_drive` and `backup_drive`, worked out from `drives` in `group_vars/all/defaults.yml`. Using a role that no entry claims fails the deploy with a message naming the role. Giving a role its own drive later moves that role's paths to the new mount point, and you copy the data there once.

## Examples

The rule is the same on every host: a drive claims roles, and service paths follow the roles. A host needs a drive for each role its enabled services use. An unclaimed role fails the deploy with a message naming it, and only on a host that enables the service that needs it.

- `fast`: Dockge's stacks and data, Caddy's data, and the data of Immich's database, Gitea, pics, Homebridge, Garage, Crafty and ntfy.
- `primary`: Immich's photos and Copyparty's files and collab folder.
- `backup`: needed where `backup_local_enabled` is true ([backups.md](./backups.md)).

Docker's own storage (images, layers) is separate: it stays on the root drive unless `docker_data_root` is set; see [Docker's own storage](#dockers-own-storage).

A host that keeps its apps on the root drive (a folder, nothing mounted):

```yaml
drives:
  - { mount: /srv/apps, roles: [fast] }
```

A host with one USB drive for apps and backups. The backup drive must have a `uuid`:

```yaml
drives:
  - { uuid: "1111-AAAA", mount: /mnt/data, fstype: ext4, options: "defaults,nofail", roles: [fast, backup] }
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

Keep `nofail` on every drive so a missing drive does not stop the host booting.

## Using the root drive for fast or primary

A `drives` entry with no `uuid` is a folder on the root drive (the drive the OS boots from: an SD card, USB or NVMe drive). It is created, and nothing goes in fstab:

```yaml
drives:
  - { mount: /srv/data, roles: [fast, primary] }
  - { uuid: "...", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

The `backup` role needs an entry with a `uuid`, or the deploy fails: a backup on the root drive dies with it. Other downsides: the Immich database wears out an SD card, and one root drive failure loses the OS and the data together.

## Plugged-in USB drives (`/drives`)

Set `usb_automount_enabled: true` in the host's `host_vars` (off by default) and any USB drive or card reader you plug in appears in Copyparty under `/drives/<label>`. A camera's SD card in a reader works. The host mounts it at `/run/media/system/<label>`.

- It is read-only. To change or delete files on it, set `usb_automount_writable: true`.
- Programs on it cannot be run (mounted `nosuid,nodev,noexec`).
- Drives listed in `drives` never appear here. A wrong `uuid` there means that drive is also mounted a second time.
- After unplugging, its empty folder stays until the next reboot or up to a day. Unplugging a writable drive without unmounting can corrupt it.
- Re-deploy to apply: `just deploy storage,copyparty`.

## Adding, replacing or retiring a drive

To add or replace a drive:
1. Format it and add or point a `drives` entry at it (a new `uuid`, on the same `mount` or a new one, with `roles` updated). If the mount point stays the same, unmount the old drive first (`sudo umount <mount>`) so the new one can take its place.
2. `just deploy storage`.
3. Copy the data over, for example `rsync -aHAX`.

To retire a drive, delete its entry. The role adds or updates fstab lines and never removes one, so remove the old line from `/etc/fstab` by hand (and `sudo umount` it); nothing is unmounted or deleted for you.

The step-by-step plan for the next drive upgrade is in [plans/drive-migration.md](./plans/drive-migration.md). A backup drive that drops out and comes back is covered in [backups.md](./backups.md#if-the-backup-drive-disconnects).

## Move one service's data

Each service's data directory is one variable (the list is in `ansible/group_vars/all/defaults.yml`, under "Data directories"). To move a service to another drive:

1. Set its variable in `host_vars/<host>/vars.yml` to a path under a drive that has a role. The default local backup (`restic_local_rules`) covers only the `primary` and `fast` drives.
2. Stop the service: `cd /opt/services/<service> && docker compose down`.
3. Copy the data: `rsync -aHAX <old path>/ <new path>/`.
4. `just deploy <service>`, then check it works. Delete the old copy by hand.

## Docker's own storage

<a id="dockges-storage-rule"></a>

Docker keeps images, layers and anonymous volumes under `/var/lib/docker` and `/var/lib/containerd`, on the root drive unless you move them. Docker 29 stores image layers through containerd, and Docker's `data-root` setting does not move those, so both are set together.

**The rule: state lives in bind mounts under a drive role, never in Docker's own storage.** Anything in Docker's storage can then be deleted and re-created (images re-pull, containers are recreated by `just deploy`). New services follow the same rule.

### Put it on a drive

1. Add the drive to `drives` in the host's `host_vars` and deploy it (`just deploy storage`).
2. In `host_vars/<host>/vars.yml` set `docker_data_root: "/mnt/t7/docker-root"` (see `ansible/group_vars/all/defaults.yml`).
3. Stop Docker and containerd by hand (`docker.socket` too, or socket activation restarts Docker mid-change):
   ```bash
   sudo systemctl stop docker.service docker.socket containerd.service
   ```
4. `just deploy common --limit <host>`. This writes `data-root` into `/etc/docker/daemon.json`, `root = ".../containerd"` into `/etc/containerd/config.toml`, and a `RequiresMountsFor=` drop-in for both services, so neither starts before the drive is mounted.
5. `sudo systemctl start containerd.service docker.service`.
6. `just deploy '' --limit <host>`, so compose pulls the images and recreates the containers.
7. When the stacks are healthy, delete the old contents of `/var/lib/docker` and `/var/lib/containerd` to free the root drive.

To go back, set `docker_data_root: ""` and repeat the steps. Nothing is copied; do not `rsync` layers (overlay whiteouts, hardlinks and extended attributes copy badly). The old directory stays as unused space.

Stop the services by hand: Ansible restarts a service only when a task reports a change, so a run that failed after editing the file does not restart it on the next run.

### Check after a reboot with the drive unplugged

With `docker_data_root` on a `nofail` drive, a missing drive keeps Docker from starting: `systemctl is-active docker containerd` says `inactive`, and neither runs from a directory on the root drive.

### Gitea runner registration

The runner keeps its registration in `gitea_runner_data_dir` (on the fast drive), a bind mount. A new directory starts empty and registers again with the token from the vault. The old registration then shows as an offline runner in Gitea (Site Administration, Actions, Runners); delete it there.

### Leftover volumes

`docker volume ls` can list volumes from older project names. Check that no container mounts one (`docker ps -a --filter volume=<name>`), then `docker volume rm <name>`. Do not use `docker volume prune -a`: it also removes named volumes of stopped containers, such as `immich_model-cache`.
