# Encryption at rest

Optional. `encryption_enabled: true` and the `encrypted_folders` setting put chosen folders under [gocryptfs](https://nuetzlich.net/gocryptfs/). The `encryption` role installs gocryptfs and an `unlock.sh` script. You create each folder once by hand and unlock after every boot.

## What it protects

Protects against: a drive that is lost, stolen, sold or sent back for repair, and a thief who has the whole host while it is powered off. File content is unreadable without the passphrase.

Does not protect against:

- someone with the host while it is running and unlocked;
- file names, sizes and modification times (gocryptfs shows the folder structure);
- a passphrase typed on a device that records it (see [Unlocking from a device you do not own](#unlocking-from-a-device-you-do-not-own));
- the root drive: a headless host cannot take a passphrase at boot. It holds the restic password file and the Tailscale and Cloudflare credentials, so a thief with the whole host can open the cloud backup but not the encrypted folders.

Quantum computers: gocryptfs and restic use 256-bit symmetric encryption, which a quantum computer weakens but does not break. The weak point is the passphrase, so use a long random one from a password manager. SSH and Tailscale use public-key exchange; recent OpenSSH uses a hybrid post-quantum key exchange by default (check the version on each host).

## How it works

gocryptfs encrypts file by file on an ordinary ext4 drive, so there is no container format to recover, and a Mac can open the drive (`brew install gocryptfs macfuse`). Two folders are involved:

- `cipher_dir`: the encrypted files. This is the folder to keep safe and the one a drive copy contains.
- `mount`: where the decrypted files appear. Services and backups use this path.

Set them per host in `host_vars/<host>/vars.yml` ([setting and example](../ansible/group_vars/all/defaults.yml)):

```yaml
encryption_enabled: true
encrypted_folders:
  - { cipher_dir: /mnt/primary/.encrypted, mount: /mnt/primary/data }
```

With encryption on:

- Docker does not start at boot. `unlock.sh` mounts the folders, checks each one, then starts Docker. Every container waits for the unlock, including ones that use no encrypted folder, because one exception is a way for a database to start on an empty folder.
- `sshd` and Tailscale run on the host, not in Docker, so you can reach the host to unlock it.
- The backup scripts refuse to run while a folder is locked (see [Backups](#backups)).
- Docker's own storage (`docker_data_root`) stays on a plain drive: overlay2 does not run on a FUSE filesystem.
- A service's data directory goes under a `mount` path by setting its `*_data_dir` variable there ([storage.md](./storage.md#move-one-services-data)).

## Create a folder

Do this once per folder, on the host, before the first deploy puts data there:

```bash
sudo mkdir -p /mnt/primary/.encrypted /mnt/primary/data
sudo gocryptfs -init -xchacha /mnt/primary/.encrypted     # see "Cipher" below
sudo gocryptfs -allow_other /mnt/primary/.encrypted /mnt/primary/data
sudo touch /mnt/primary/data/.mounted
```

`-init` prints the **master key** once. Put it in your password manager and on paper. Then copy `gocryptfs.conf` from the `cipher_dir` somewhere off the host. Either one recreates a lost config (`gocryptfs -init -masterkey ...`, see the gocryptfs wiki, "Recreate gocryptfs.conf using masterkey"); with neither, a lost `gocryptfs.conf` means lost data. `gocryptfs.diriv` has no documented recovery, so the whole `cipher_dir` is part of what you keep safe.

`.mounted` is the file `unlock.sh` and the backups look for. It exists only inside the decrypted view, so its absence means the folder is locked.

Never mount with `-nonempty`. Without it, a mount over a folder that something wrote into fails loudly ("directory not empty") instead of hiding those files.

### Cipher

The cipher is fixed at `-init`; choose it for the CPU that mounts the drive. `gocryptfs -speed` 2.5.1 measured:

| Host | AES-GCM | XChaCha20 | Use |
|---|---|---|---|
| Pi 4 (no AES instructions) | 44 MB/s | 162 MB/s | `-init -xchacha` |
| Pi 5 (has them) | about 1170 MB/s | 507 MB/s | `-init` (default) |

On x86-64, which has AES instructions, use the default. A drive moved between hosts keeps its cipher. XChaCha20 needs gocryptfs 2.2 or later on every machine that opens the drive, the Mac included.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each folder, stops with an error if a folder has no `.mounted` file, then starts Docker. A wrong passphrase stops it before Docker starts. Running it again on an unlocked host does nothing harmful.

After a reboot nothing runs until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then, and log the failure with `logger -t backup`. ntfy runs in Docker, so it is down too and cannot tell you the host is locked.

`just deploy` of a service needs Docker, so unlock first.

### Unlocking from a device you do not own

Unlocking works from any device that can SSH to the host. A borrowed device may record what you type. After using one, change the passphrase with `sudo gocryptfs -passwd <cipher_dir>`, which does not re-encrypt the data. This only helps if nobody has copied `gocryptfs.conf` from the drive: someone with that file and the old passphrase can still open the data. Full protection means creating a new gocryptfs folder and copying the files in.

## Services and encrypted folders

- **Services from this repo** need nothing extra. Docker is off until `unlock.sh` has mounted every folder, so a container never starts on a locked folder; its `restart: unless-stopped` brings it up when Docker starts. A deploy checks that every folder is unlocked first and stops with a message if one is not, even when you deploy a single service with `--tags`.
- **Locking again** (a lost drive about to be unplugged, or a borrowed device): `sudo systemctl stop docker docker.socket`, then `sudo umount <mount>` for each folder. Unmounting fails while a container still holds the folder open.
- **Moving a service into an encrypted folder:** set its `*_data_dir` (or `immich_upload_location` and similar) to a path under `mount`; [Migrate](#migrate-to-or-from-encryption) has the full steps. A service whose data directory is outside every `mount` stays unencrypted; nothing checks this, because you may want some data plain.

### Services you run yourself

Services that this repo does not manage can still use its unlock, backup and mount checks.

- **In Docker** (your own compose files, or stacks made in Dockge): put their data under a `mount` path and give them `restart: unless-stopped`. They start when Docker starts after the unlock.
- **Outside Docker** (a systemd unit on the host): list the unit in `unlock_start_units` and leave it disabled at boot (`sudo systemctl disable <unit>`), or it starts on an empty folder. `unlock.sh` starts it after Docker.
- **Backups:** add their paths to `restic_local_rules` ([backups.md](./backups.md#choosing-what-is-backed-up)). The locked-folder check covers every entry in `encrypted_folders`, whatever the path. This repo's coverage check only knows its own services. A live database needs a dump script, installed by hand as `<name>.sh` in `service_dump_scripts_dir` ([backups.md](./backups.md)), because no role of yours installs it.
- **Only some features:** leave every service flag off and set just `encryption_enabled`, `encrypted_folders` and `backup_local_enabled`.

## Migrate to or from encryption

Both directions copy the data, check the copy, then switch the path. Plan for the downtime; do one service or folder at a time.

### Plain to encrypted

1. [Create the folder](#create-a-folder) on the same drive and mount it. Add `encryption_enabled` and `encrypted_folders` to `vars.yml`.
2. Stop the service: `docker compose -f /opt/services/<name>/docker-compose.yml down`.
3. Copy: `sudo rsync -aHAX /mnt/primary/immich/ /mnt/primary/data/immich/`. Compare with `sudo rsync -aHAXn --checksum --itemize-changes /mnt/primary/immich/ /mnt/primary/data/immich/`: it should print nothing.
4. Point the service's data setting at the new path in `vars.yml` and run `just deploy <name> --limit <host>`. Start with a deploy of `common` and `encryption` once, so Docker stops starting at boot.
5. Check the service works. Take a backup (`sudo /opt/services/scripts/backup-restic-local.sh`) so the new paths are in a snapshot.
6. Delete the old plain folder. Deleting does not erase it from the drive: a drive that held plain data still holds it. If the drive may leave your hands, `blkdiscard` it (SSD) or overwrite it, and re-format before use.

Old restic snapshots keep the old paths; they are restic-encrypted and age out under the retention rules.

### Encrypted to plain

1. Unlock. Stop the service as above.
2. Copy out: `sudo rsync -aHAX /mnt/primary/data/immich/ /mnt/primary/immich/` and compare as above.
3. Point the data setting back at the plain path. When no folder is left, remove `encrypted_folders` and set `encryption_enabled: false`.
4. `just deploy common,<name> --limit <host>`. Docker starts at boot again; run `sudo systemctl enable docker.socket` once, which the encryption role had disabled.
5. Check, back up, then `sudo umount` the folder and delete the `cipher_dir` and the folder it was mounted on.

## Backups

- restic backs up the decrypted files through the mount. The repository is encrypted by restic with its own password, and a restore needs no gocryptfs.
- The restic repository on the `backup` drive is not inside a gocryptfs folder: a second layer would tie two recovery paths to one key. To encrypt service dumps and logs on that drive, add it to `encrypted_folders` like any other.
- The backup scripts check, for every entry in `encrypted_folders`, that `mount` is a mount point containing `.mounted`. The drive itself is mounted even while the folder is locked, so the ordinary drive check would pass and restic would save an empty folder.
- A host with no `backup` drive keeps service dumps in `/var/lib/backup-work` on the root drive, unencrypted.

## Tested

On a Pi 4 with a scratch folder (removed afterwards):

- `unlock.sh` refuses when the mount has no `.mounted`, fails on a wrong passphrase, and succeeds with the right one.
- A container running as another user id reads the files with `-allow_other` and gets "Permission denied" without it.
- SQLite in WAL mode survived six `kill -9`s during writes with `integrity_check` ok each time; `gocryptfs -fsck` reported no problems.
- Mounting over a folder with a file in it fails with exit code 10 ("directory not empty").

Not tested: Postgres on a gocryptfs mount (Immich's database), automount behaviour with the folder behind it, and the rest of the recovery drill below. Run the drill on a scratch folder before real data goes in.

## Recovery drill

1. Init, mount, write files, unmount, run `gocryptfs -fsck`.
2. Delete `gocryptfs.conf`, recreate it from the master key, remount and read the files.
3. Change the passphrase with `-passwd` and check the old one fails.
4. Mount the same folder on a Mac and read the files.
5. Delete one `gocryptfs.diriv` and see what is lost.
6. Leave the folder unmounted and run a backup script: it must refuse.
7. Restore a restic snapshot to a clean folder and compare checksums.
8. If a database goes on the mount: `kill -9` Postgres a few times under load and check it recovers.
