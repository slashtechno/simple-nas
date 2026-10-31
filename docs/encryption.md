# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot. Everything else, including containers with data in other folders, runs as before.

## What it protects

Protects against a drive that is lost, stolen, sold or sent back for repair, and a thief who has the whole host while it is off. File content is unreadable without the passphrase.

Does not protect against:

- someone with the host while it is running and unlocked;
- file names, sizes and modification times, which gocryptfs shows;
- the root drive. A headless host cannot take a passphrase at boot, so the root drive holds the restic password file and the Tailscale and Cloudflare credentials. A thief with the whole host can open the cloud backup, but not an encrypted folder;
- a passphrase typed on a device that records it (see [Unlocking from another device](#unlocking-from-another-device)).

Quantum computers weaken but do not break the 256-bit symmetric encryption gocryptfs and restic use. The weak point is the passphrase: use a long random one from a password manager.

## How it works

In `host_vars/<host>/vars.yml`, list the folders (any folder on any drive, such as the data folder of one service):

```yaml
encrypted_folders:
  - /mnt/primary/immich
  - /mnt/backup/service-dumps
```

Each folder you list is two folders on the drive:

| Path | What it is |
|---|---|
| `/mnt/primary/immich` | The decrypted view, mounted by `unlock.sh`. Services and backups use this path, so no other setting changes. |
| `/mnt/primary/.immich.gocryptfs` | The encrypted files, next to it. This hidden folder is what you keep safe. |

Folders you do not list stay plain. Encryption is **not in place**: gocryptfs encrypts a file when it is copied into the view, so existing data is moved in ([Moving data in](#moving-data-in)).

While a folder is locked it is an empty folder marked immutable (`chattr +i`, set by `unlock.sh`). Nothing can write into it: a container or a deploy that runs too early fails with "Operation not permitted" instead of filling the drive underneath. The backup scripts refuse to run, like for a drive that is not mounted.

Containers do not wait for the unlock. Those with data in a plain folder start at boot as usual. A container with data in a locked folder fails to start, or sees an empty folder, until `unlock.sh` restarts Docker. Docker's own storage (`docker_data_root`) cannot be in an encrypted folder: overlay2 does not run on a FUSE filesystem. `sshd` and Tailscale run on the host, not in Docker, so you can reach the host to unlock it.

## Set up a folder

1. Add the path to `encrypted_folders` and run `just deploy encryption --limit <host>` (installs gocryptfs and `unlock.sh`).
2. On the host, with the folder empty or not yet existing:

```bash
sudo mkdir -p /mnt/primary/immich
sudo gocryptfs -init -xchacha /mnt/primary/.immich.gocryptfs   # -xchacha on a Pi 4; leave it off on a Pi 5 or x86-64
sudo /opt/services/scripts/unlock.sh
```

`-init` prints the **master key** once. Put it in your password manager and on paper, and copy `gocryptfs.conf` off the host. Either one recreates a lost config (gocryptfs wiki, "Recreate gocryptfs.conf using masterkey"); with neither, a lost `gocryptfs.conf` means lost data. A lost `gocryptfs.diriv` has no documented recovery, so the whole `.gocryptfs` folder is what you keep safe. Use the same passphrase for every folder and `unlock.sh` asks once.

The cipher is fixed at `-init`. `gocryptfs -speed` 2.5.1 measured:

| Host | AES-GCM | XChaCha20 | Use |
|---|---|---|---|
| Pi 4 (no AES instructions) | 44 MB/s | 162 MB/s | `-xchacha` |
| Pi 5 (has them) | about 1170 MB/s | 507 MB/s | default |

On x86-64, which has AES instructions, use the default. A drive moved to another host keeps its cipher. XChaCha20 needs gocryptfs 2.2 or later on every machine that opens the folder, a Mac included (`brew install gocryptfs macfuse`).

### Moving data in

A folder that already holds data: stop its service, rename the folder to `<name>.plain`, set it up as above, then move the files in file by file:

```bash
sudo rsync -aHAX --remove-source-files /mnt/primary/immich.plain/ /mnt/primary/immich/
```

`--remove-source-files` deletes each source file once it is copied, so the drive needs room for roughly the largest file plus about 1% overhead, not a second copy of everything. Before you start:

- take a backup and check it restores ([backups.md](./backups.md));
- save a checksum list (`cd immich.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt`), and after the move run the same in the new folder and `diff` the two lists;
- if the move stops half way, run the same command again: it carries on.

Deleting files does not erase them from the drive. A drive that held plain data may still hold it: re-format or `blkdiscard` it before it leaves your hands. A new, empty drive (the [drive migration](../plans/drive-migration.md) has two) needs none of this: set the folders up first, then copy the old data in.

### Turning it off

Unlock, copy the files to a plain folder (`rsync -aHAX`), point the service at it, remove the path from `encrypted_folders`, deploy `encryption`, `sudo umount` the folder and delete both folders. The role removes `unlock.sh`; nothing else was changed.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each folder and restarts Docker so containers see the files. A wrong passphrase stops it before Docker restarts. It never uses `-nonempty`: if something got into a locked folder anyway, the mount fails instead of hiding it.

After a reboot, services with encrypted data stay down until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then and log the failure with `logger -t backup`. ntfy runs in Docker, so nothing alerts you that the host is locked.

To lock again: `sudo docker stop` the containers that use the folder, then `sudo umount <folder>`.

### Unlocking from another device

Unlocking works from any device that can SSH to the host. A borrowed device may record what you type. Afterwards change the passphrase with `sudo gocryptfs -passwd /mnt/primary/.immich.gocryptfs`. That does not re-encrypt the data, so it helps only if nobody copied `gocryptfs.conf`. Full protection means a new gocryptfs folder and a copy of the files into it.

## Services and backups

- **Services from this repo:** list the folder that holds their data. Their settings stay the same.
- **Your own Docker services:** keep their data in a listed folder, or leave them unencrypted; both work. Give them `restart: unless-stopped`.
- **Your own systemd services** that need a locked folder: disable them at boot (`sudo systemctl disable <unit>`) and start them by hand after `unlock.sh`.
- **Backups** copy the decrypted files through the mount, and skip the `.gocryptfs` folders (they would be stored twice). The restic repository is encrypted by restic with its own password and a restore needs no gocryptfs. To encrypt service dumps, list their folder (`service_dumps_dir`). A host with no `backup` drive keeps dumps in `/var/lib/backup-work` on the root drive, unencrypted.
- Paths of your own services go in `restic_local_rules` ([backups.md](./backups.md#choosing-what-is-backed-up)).

## Tested

On a Pi 4 with a scratch loop-device drive, removed afterwards:

- A wrong passphrase stops `unlock.sh`; the right one mounts; file names on the drive are encrypted; a second run changes nothing.
- A locked folder rejects writes from the host and from containers, and a container whose data is in a subfolder of it fails to start with an error. After the unlock and a Docker restart it runs and reads the files. A container started while locked does not see the files until Docker restarts.
- A mount over a folder with a file in it fails (exit 10).
- A container running as another user id can read the files with `-allow_other` and not without it.
- Moving 701 files (300 MB) into a gocryptfs folder on a drive that was 86% full: a plain `rsync` ran out of space, `--remove-source-files` finished, every checksum matched and `gocryptfs -fsck` found no problems.
- SQLite in WAL mode survived six `kill -9`s during writes with `integrity_check` ok each time.

Not tested: Postgres on a gocryptfs mount (Immich's database), a real deploy of the role, and the rest of the recovery drill below. Run the drill on a scratch folder before real data goes in.

## Recovery drill

1. Init, mount, write files, unmount, run `gocryptfs -fsck`.
2. Delete `gocryptfs.conf`, recreate it from the master key, remount and read the files.
3. Change the passphrase with `-passwd` and check the old one fails.
4. Mount the same folder on a Mac and read the files.
5. Leave the folder locked and run a backup script: it must refuse.
6. Restore a restic snapshot to a clean folder and compare checksums.
7. If a database goes on the mount: `kill -9` Postgres a few times under load and check it recovers.
