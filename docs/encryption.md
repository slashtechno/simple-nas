# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot. Everything else, including containers with data in other folders, runs as before.

## What it protects

Protects against a drive that is lost, stolen, sold or sent back for repair, and a thief who has the whole host while it is off. File content is unreadable without the passphrase.

Does not protect against:

- someone with the host while it is running and unlocked;
- file names, sizes and modification times, which gocryptfs shows;
- the root drive. A headless host cannot take a passphrase at boot, so the root drive holds the restic password file and the Tailscale and Cloudflare credentials. A thief with the whole host can open the local and the cloud backups, though not an encrypted folder;
- a passphrase typed on a device that records it (see [Unlocking from another device](#unlocking-from-another-device)).

Quantum computers weaken but do not break the 256-bit symmetric encryption gocryptfs and restic use. The weak point is the passphrase: use a long random one from a password manager.

## How it works

In `host_vars/<host>/vars.yml`, list absolute paths of folders on any drive, such as the folder a service already uses (Immich's `immich_upload_location` is `<primary_drive>/photos`). A path no service uses encrypts nothing, and the deploy does not warn:

```yaml
encrypted_folders:
  - /mnt/primary/photos
```

Each listed folder is two folders on the drive:

| Path | What it is |
|---|---|
| `/mnt/primary/photos` | The decrypted view, mounted by `unlock.sh`. Services and backups use this path, so no other setting changes. |
| `/mnt/primary/.photos.gocryptfs` | The encrypted files, next to it. |

Folders you do not list stay plain. While a folder is locked it is an empty folder marked immutable (`chattr +i`), so nothing can be created in it: a container or a deploy that runs too early fails with "Operation not permitted" instead of filling the drive underneath. A file that was already inside stays writable, and root can remove the flag, so this is a safety net against mistakes, not a security boundary.

Containers do not wait for the unlock. Those with data in a plain folder start at boot as usual. A container with data in a locked folder fails to start, or sees an empty folder, until `unlock.sh` restarts Docker. Docker's own storage (`docker_data_root`) cannot be in an encrypted folder: overlay2 does not run on a FUSE filesystem, and a deploy fails if it is. `sshd` and Tailscale run on the host, not in Docker, so you can reach the host to unlock it.

## Set up a folder

On a host you are setting up, do this before the service first starts, or it writes plain files into the folder: deploy with `--tags storage,common,encryption`, run the commands in step 2 (and step 4 only if the folder already holds data), then deploy everything.

Back up first and check the backup restores; the move in step 4 deletes the source files as it goes.

1. Add the path to `encrypted_folders` and run `just deploy encryption,backup --limit <host>`. That installs gocryptfs and two scripts, and teaches the backups to refuse a locked folder and to skip the encrypted files (they would be stored twice).
2. Stop the service that uses the folder, and keep it stopped until step 5 is done. Rename a folder that already holds data, and create an empty one:

```bash
sudo mv /mnt/primary/photos /mnt/primary/photos.plain      # skip if the folder does not exist yet
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/primary/photos
sudo /opt/services/scripts/unlock.sh
```

3. `init-encrypted-folder.sh` prints a **master key** once, and only when it runs in a terminal (`ssh -t <host> sudo ...`). Put it in your password manager, and copy `gocryptfs.conf` from the `.gocryptfs` folder off the host. Without that file the data cannot be opened. The script picks the cipher for this CPU and it cannot be changed later. On a host without AES instructions (Raspberry Pi 4) that is XChaCha20, which needs gocryptfs 2.2 or later on any other machine that opens the folder, such as a Mac (`brew install gocryptfs macfuse`). Use the same passphrase for every folder; `unlock.sh` asks once.
4. Move the data in, file by file:

```bash
cd /mnt/primary/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt
sudo rsync -aHAX --remove-source-files /mnt/primary/photos.plain/ /mnt/primary/photos/
cd /mnt/primary/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo identical
```

`--remove-source-files` deletes each file once it is copied, so the drive needs room for roughly the largest file plus about 1% overhead, not a second copy. (A sparse file takes its full size.) Take a backup and check that it restores first ([backups.md](./backups.md)): a power cut at the wrong moment can lose the file being moved. If the move stops half way, run the same `rsync` again.

5. When the lists are identical, remove the leftover empty folders (`sudo rm -r /mnt/primary/photos.plain`) and start the service. From step 1 until `unlock.sh` has mounted the folder, every backup (local and cloud) refuses to run and stores nothing, dumps included, so do steps 1 to 5 in one sitting.

Deleting files does not erase them from the drive. A drive that held plain data may still hold it: re-format it before it leaves your hands. A new, empty drive needs none of this: set the folders up first, then copy the old data in.

### Turning it off

Unlock, copy the files out to a plain folder with `rsync -aHAX`, point the service at it, remove the path from `encrypted_folders`, deploy `encryption,backup`, then `sudo umount <folder>`, `sudo chattr -i <folder>` and delete both folders. The role removes the two scripts; gocryptfs stays installed.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each folder that is locked and restarts Docker, so containers see the files; containers started without a restart policy are not started again. A wrong passphrase stops it at that folder, and it says which one; Docker is restarted if an earlier folder had already been mounted. It never uses `-nonempty`, and it stops if a locked folder is not empty (move the files away first) instead of hiding them. Run on an unlocked host it does nothing.

After a reboot, services with encrypted data stay down until someone unlocks, and the backups of every drive refuse to run while any listed folder is locked. A failed backup pushes an alert only if `ntfy_alert_url` is set, and an ntfy server on this host is down when Docker is; point it at one elsewhere (or ntfy.sh) to hear about a locked host. Otherwise the failure is only in the log (`logger -t backup`). The restart stops every container for up to 10 seconds, including ones with plain data.

To lock again: stop the containers that use the folder, then `sudo umount <folder>`.

### Unlocking from another device

`unlock.sh` also reads the passphrase from standard input (`printf %s "$PASSPHRASE" | sudo unlock.sh`), so anything that can run a command on the host can unlock it, not only a person at a terminal. That is the hook for the unlock page in [TODO.md](../TODO.md).

Unlocking works from any device that can SSH to the host. A borrowed device may record what you type. Afterwards change the passphrase with `sudo gocryptfs -passwd <the .gocryptfs folder>`. That does not re-encrypt the data, so it helps only if nobody copied `gocryptfs.conf`. Full protection means a new gocryptfs folder and a copy of the files into it.

## If gocryptfs.conf is lost

Two ways back:

- **Master key:** make an empty folder, run `gocryptfs -init -masterkey <key> <empty folder>` with the same options the folder was created with, and copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. gocryptfs refuses `-init` in a folder that already holds files, which is why the new file is made elsewhere. `init-encrypted-folder.sh` adds `-xchacha` on a CPU with no AES (a Raspberry Pi 4); add it too. With the wrong options the mount succeeds but every read fails with an input/output error.
- **Backups:** they hold the decrypted files and exclude the `.gocryptfs` folders. Create a new encrypted folder, restore the snapshot to a scratch folder (`restic restore latest --target <scratch>`, [backups.md](./backups.md)), and `rsync -aHAX` the files in. The deploy fails if an encrypted folder is outside every path in `restic_local_rules`, so a folder always has such a backup.
