# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot. Everything else, including containers with data in other folders, runs as before.

## What it protects

A drive that is lost, stolen, sold or sent back for repair, and a thief who has the whole host while it is off: file content is unreadable without the passphrase. Use a long random passphrase from a password manager; it is the weak point, not the 256-bit encryption.

It does not protect:

- a host that is running and unlocked;
- what the ciphertext's shape shows: the number of files and folders, their depth, roughly how long each name is, and every file's size (rounded up to 4 KiB) and modification time. The names themselves are encrypted;
- the root drive. A headless host cannot take a passphrase at boot, so it holds the restic password file and the Tailscale and Cloudflare credentials. A thief with the whole host can open the local and cloud backups, though not a listed folder;
- the backup logs, which list every backed-up path in plain text, and the service dumps ([Dumps and backups](#dumps-and-backups));
- a passphrase typed on a device that records it. After using a borrowed device, run `sudo gocryptfs -passwd <the .gocryptfs folder>` for every folder. That does not re-encrypt the data, so it helps only if nobody copied `gocryptfs.conf`.

## How it works

Each entry in `encrypted_folders` is the absolute path of one folder. gocryptfs keeps the ciphertext in a hidden folder beside it, in the same parent directory (`encrypted_pairs` in `group_vars/all/defaults.yml`):

| Path | What it is |
|---|---|
| `/mnt/data/photos` | The decrypted view, mounted by `unlock.sh`. Services and backups use this path, so no data directory setting changes. |
| `/mnt/data/.photos.gocryptfs` | The encrypted files, on the same filesystem. |

Folders you do not list stay plain.

- **Locked folder.** It is an empty folder marked immutable (`chattr +i`), so a container or a deploy that runs too early fails with "Operation not permitted" instead of filling the drive underneath. `unlock.sh` sets the mark just before the first mount, and only on a filesystem that supports it (ext4, xfs, btrfs); elsewhere it warns and mounts anyway. Root can remove the flag, so it is a safety net against mistakes, not a security boundary.
- **Containers do not wait for the unlock.** One with data in a locked folder fails to start, or sees an empty folder, until `unlock.sh` restarts Docker. That stops every container for up to 10 seconds, including ones with plain data. Software outside Docker that uses a listed folder (a systemd service, a cron job) is not restarted: restart it by hand after the unlock.
- **Docker's own storage** (`docker_data_root`) cannot be in a listed folder, because overlay2 does not run on a FUSE filesystem. The deploy fails if it is. `sshd` and Tailscale run on the host, so you can reach it to unlock.
- **Cipher.** XChaCha20, fixed for every host. It cannot be changed later, and a folder opened on another machine needs gocryptfs 2.2 or later (`brew install gocryptfs macfuse`).

### Which folders to list

A `drives` mount point such as `/mnt/data` does not work: the ciphertext would go to `/mnt/.data.gocryptfs` on the root drive, `init-encrypted-folder.sh` refuses a folder that is not empty (a formatted drive holds `lost+found`), and `unlock.sh` skips a folder that is already a mount point. List the folders that hold data instead. With the default data directories and a drive at `/mnt/data` that claims `fast` and `primary` ([storage.md](./storage.md#examples)):

```yaml
encrypted_folders:
  - /mnt/data/docker   # every service's data directory on the fast drive
  - /mnt/data/stacks   # Dockge stacks
  - /mnt/data/photos   # Immich's photos
  - /mnt/data/files    # Copyparty's files
```

`/mnt/data/fast` and `/mnt/data/collab` also hold data when `copyparty_fast_enabled` and `copyparty_collab_enabled` are on. A service added later with its data under `{{ fast_drive }}/docker` is covered without a change. Anything else on the drive stays plain.

## Dumps and backups

`backup-services.sh` writes the Immich, Gitea and Garage dumps to `service_dumps_dir` (`<backup drive>/service-dumps`, or `/var/lib/backup-work/service-dumps` without a local backup). Nothing encrypts that folder unless you list it, so until then whoever finds the drive reads the Immich database, Gitea's dump and Garage's node key. To list it, add it to `encrypted_folders` and to `restic_local_extra_rules` (a listed folder outside every path in `restic_local_rules` stops the deploy, `roles/backup/tasks/check_coverage.yml`). Both backup scripts then refuse to run while it is locked, like any listed folder.

restic encrypts everything it writes: contents, file names and snapshot metadata. The password is `vault_restic_password`, written to `restic_password_file` on the root drive; with it, everything in the repository is readable, including a listed folder's files, which restic reads through the mount as decrypted files. For that reason the ciphertext folders are left out of every backup (`roles/backup/templates/restic-excludes-services.txt.j2`): saving them too would store everything twice.

## Set up a folder

On a host you are setting up, do this before the service first starts, or it writes plain files into the folder: run `just deploy storage,common --limit <host>`, then steps 1 to 5 for each folder (they share one passphrase), then deploy everything. Step 4 applies only to a folder that already holds data. Back up first and check the backup restores; the move in step 4 deletes the source files as it goes.

1. Add the paths to `encrypted_folders` and run `just deploy encryption,backup --limit <host>`. That installs gocryptfs and the scripts, and teaches the backups to refuse a locked folder and to skip the encrypted files.
2. Stop the service that uses the folder, and keep it stopped until step 5 is done. Rename a folder that already holds data, and create an empty one:

```bash
sudo mv /mnt/data/photos /mnt/data/photos.plain      # skip if the folder does not exist yet
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/data/photos
sudo /opt/services/scripts/unlock.sh
```

The mounted folder's top directory takes the owner and mode of the empty folder it was created from, which is root's when the script creates it. A service running as another user id needs the top directory chowned while the folder is unlocked; a chown while it is locked is lost.

3. `init-encrypted-folder.sh` prints a **master key** once, and only in a terminal (`ssh -t <host> sudo ...`). Put it in your password manager, and copy `gocryptfs.conf` from the `.gocryptfs` folder off the host. Each folder has its own key and file, and without them its data cannot be opened.
4. Move the data in, file by file:

```bash
cd /mnt/data/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt
sudo rsync -aHAX --remove-source-files /mnt/data/photos.plain/ /mnt/data/photos/
cd /mnt/data/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo identical
```

`--remove-source-files` deletes each file once copied, so the drive needs room for about the largest file plus 1% overhead, not a second copy. A power cut at the wrong moment can lose the file being moved. If the move stops half way, run the same `rsync` again.

5. When the lists are identical, remove the leftover folders (`sudo rm -r /mnt/data/photos.plain`) and start the service. From step 1 until `unlock.sh` has mounted the folder, every backup refuses to run and stores nothing, dumps included, so do this in one sitting.

Deleting files does not erase them from the drive. A drive that held plain data may still hold it: re-format it before it leaves your hands. On a new, empty drive, set the folders up first, then copy the old data in.

### Turning it off

For each folder: unlock, copy the files out to a plain folder with `rsync -aHAX`, point the service at it, remove the path from `encrypted_folders`, run `just deploy encryption,backup --limit <host>`, then `sudo umount <folder>`, `sudo chattr -i <folder>` and delete both folders. The role removes the scripts once no folder is left; gocryptfs stays installed.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each locked folder, then restarts Docker. A wrong passphrase stops it at that folder and says which. It stops if a locked folder is not empty (move the files away first) instead of hiding them, and it does nothing on an unlocked host. The passphrase can also arrive on standard input (`printf %s "$PASSPHRASE" | sudo .../unlock.sh`).

After a reboot, services with encrypted data stay down until someone unlocks, and the backups of every drive refuse to run while any listed folder is locked. A failed backup pushes an alert only if `ntfy_server` is set, and an ntfy server on this host is down when Docker is; point `ntfy_server` at another host (or `ntfy_alert_url` at ntfy.sh) to hear about a locked host.

To lock again: stop the containers that use the folder, then `sudo umount <folder>`.

## If gocryptfs.conf is lost

Two ways back, per folder:

- **Master key:** make an empty folder, run `sudo gocryptfs -init -xchacha -masterkey <key> <empty folder>`, then copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. gocryptfs refuses `-init` in a folder that already holds files, which is why the new file is made elsewhere.
- **Backups:** they hold the decrypted files and exclude the `.gocryptfs` folders. Create a new encrypted folder, restore the snapshot to a scratch folder (`restic restore latest --target <scratch>`, [backups.md](./backups.md)), and `rsync -aHAX` the files in. With a local backup the deploy fails if a listed folder is outside every path in `restic_local_rules`, so a folder always has such a backup; a cloud-only host is not checked.
