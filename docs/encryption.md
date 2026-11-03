# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot. Everything else, including containers with data in other folders, runs as before.

## What it protects

Protects the listed folders against a drive that is lost, stolen, sold or sent back for repair, and against a thief who has the whole host while it is off. File content is unreadable without the passphrase.

Does not protect against:

- someone with the host while it is running and unlocked;
- what the ciphertext's shape shows: how many files and folders there are, how deep they sit, roughly how long each name is, and every file's size and modification time (the names themselves are encrypted);
- the backup logs on the backup drive, which list every backed-up path by name in plain text ([Dumps and backups](#dumps-and-backups));
- the root drive. A headless host cannot take a passphrase at boot, so the root drive holds the restic password file and the Tailscale and Cloudflare credentials. A thief with the whole host can open the local and the cloud backups, though not a listed folder;
- the service dumps, which are plaintext on the drive that holds them until the folder is listed ([below](#dumps-and-backups));
- a passphrase typed on a device that records it (see [Unlocking from another device](#unlocking-from-another-device)).

Quantum computers weaken but do not break the 256-bit symmetric encryption gocryptfs and restic use. The weak point is the passphrase: use a long random one from a password manager.

## How it works

Each entry is an absolute path of one folder. gocryptfs keeps the ciphertext in a hidden folder beside it, in the same parent directory (`encrypted_pairs` in `group_vars/all/defaults.yml`):

| Path | What it is |
|---|---|
| `/mnt/data/photos` | The decrypted view, mounted by `unlock.sh`. Services and backups use this path, so no data directory setting changes. |
| `/mnt/data/.photos.gocryptfs` | The encrypted files, next to it, on the same filesystem. |

A listed folder is an ordinary directory on a filesystem: next to another folder on the same drive, or the folder a service already uses (Immich's `immich_upload_location` is `<primary drive>/photos`). Folders you do not list stay plain, and the deploy does not warn.

While a folder is locked it is an empty folder marked immutable (`chattr +i`), so nothing can be created in it: a container or a deploy that runs too early fails with "Operation not permitted" instead of filling the drive underneath. `unlock.sh` sets the mark just before it mounts, so the folder is protected only after its first unlock, and only on a filesystem that supports the mark (ext4, xfs, btrfs); on another one `unlock.sh` warns and mounts anyway. A file that was already inside stays writable, and root can remove the flag, so this is a safety net against mistakes, not a security boundary.

Containers do not wait for the unlock. Those with data in a plain folder start at boot as usual. A container with data in a locked folder fails to start, or sees an empty folder, until `unlock.sh` restarts Docker (its `00-docker.sh` script). Docker's own storage (`docker_data_root`) cannot be in a listed folder: overlay2 does not run on a FUSE filesystem, and a deploy fails if it is. `sshd` and Tailscale run on the host, not in Docker, so you can reach the host to unlock it.

After mounting, `unlock.sh` runs every `<name>.sh` in `after-unlock.d` (in `scripts_dir`) as root, in name order. The deploy installs `00-docker.sh` there; for any other software that uses the folder (a systemd service, a supervisor program, a cron job) add a script with its restart command, for example `systemctl restart myapp`.

## A whole drive cannot be listed

There is no setting that encrypts a drive, and no LUKS: gocryptfs encrypts folders on the drive's existing ext4, so it is not reformatted and a folder can be opened on another machine (`brew install gocryptfs macfuse`).

A `drives` mount point such as `/mnt/data` in `encrypted_folders` does not work, for three reasons taken from the role:

- the ciphertext goes into the parent directory of the path, so it lands in `/mnt/.data.gocryptfs` on the root drive, and the files on `/mnt/data` stay plain;
- `roles/encryption/templates/init-encrypted-folder.sh.j2` refuses a folder that is not empty, and a formatted drive always holds `lost+found`;
- `roles/encryption/templates/unlock.sh.j2` skips a folder that `mountpoint` reports as mounted, which a drive mount point always is, so it would never mount it.

To have everything on a data drive encrypted, list the folders at the top of the drive that hold data. With the default data directories that is four folders, for a drive with `{ uuid: "...", mount: /mnt/data, roles: [fast, primary] }` in `drives` ([storage.md](./storage.md#examples)):

```yaml
encrypted_folders:
  - /mnt/data/docker
  - /mnt/data/stacks
  - /mnt/data/photos
  - /mnt/data/files
```

`/mnt/data/docker` holds every service's data directory on the fast drive, `/mnt/data/stacks` the Dockge stacks, `/mnt/data/photos` Immich's photos and `/mnt/data/files` Copyparty's files. Two more folders have data when their flag is on: `/mnt/data/fast` with `copyparty_fast_enabled` and `/mnt/data/collab` with `copyparty_collab_enabled`. A service you add later keeps its data under `{{ fast_drive }}/docker`, so it is covered without a setting change.

Anything on the drive outside these folders stays plain. After the first unlock, `sudo ls -a /mnt/data` shows the four folders, their `.gocryptfs` folders, and whatever else is on the drive; the rest is not encrypted. One folder for the whole drive (`/mnt/data/encrypted`) also works, but then every data directory setting has to point inside it, and a service switched on later starts outside it.

## Dumps and backups

`backup-services.sh` runs the dump scripts (`immich.sh`, `gitea.sh`, `garage.sh`) and writes their output to `service_dumps_dir`. That is `<backup drive>/service-dumps` with a local backup, and `/var/lib/backup-work/service-dumps` on the root drive without one (`backup_work_dir` in `group_vars/all/defaults.yml`). Nothing encrypts it: until the folder is listed in `encrypted_folders`, the dumps are plaintext, and whoever finds that drive reads the Immich database, Gitea's dump and Garage's node key.

The folder can be listed. With a local backup, a listed folder outside every path in `restic_local_rules` stops the deploy (`roles/backup/tasks/check_coverage.yml`), so the dump folder needs a rule as well:

`encrypted_folders: [/mnt/backup/service-dumps]` and `restic_local_extra_rules: [/mnt/backup/service-dumps]`.

Setting `service_dumps_dir` inside a folder that is listed already works the same way. Either way both backup scripts then refuse to run while the folder is locked, like any other listed folder.

restic encrypts everything it writes into a repository: file contents, file names and snapshot metadata. The password is `vault_restic_password`, written to `restic_password_file` (`/home/<user>/.restic-password`) on the root drive. Without it the repository is unreadable, with it all of it is readable, including the snapshot of a listed folder, which restic reads through the mount as decrypted files.

| Data | On the data drive | On the backup drive | Offsite |
|---|---|---|---|
| Service data (photos, files, configs, live database directories) | Plain, or ciphertext in `.<name>.gocryptfs` when the folder is listed | In `restic-repo`, encrypted by restic | Only the paths in `restic_cloud_rules`, encrypted by restic |
| Service dumps in `service_dumps_dir` | Not there | Plaintext in `service-dumps` unless that folder is listed, plus the copy in `restic-repo` | Encrypted by restic in the cloud repository |
| `restic-repo` | Only when the backup role is on the same drive | Encrypted by restic | Encrypted by restic |

The ciphertext folders are left out of every backup (`roles/backup/templates/restic-excludes-services.txt.j2`): restic stores the decrypted files, so saving the ciphertext too would store everything twice.

## Drive setups

The drive roles are in [storage.md](./storage.md#examples). "Listed folder" means an entry in `encrypted_folders`; its ciphertext is in `.<name>.gocryptfs` beside it, on the same drive. The lock applies to every listed folder on the host, whichever drive it is on.

| Setup | Encrypted | Not encrypted | A thief with the drive or the host gets | After a reboot |
|---|---|---|---|---|
| Root drive only: `drives: [{ mount: /srv/data, roles: [fast, primary] }]`, cloud backup | The listed folders, ciphertext on the root drive | The rest of the root drive: the OS, `/opt/services` with the compose files and credentials, Docker's storage, `/var/lib/backup-work`, the restic password file | The whole host: everything not in a listed folder, and the cloud repository through the password file and the rclone login | `unlock.sh`, then Docker restarts; the cloud backup refuses while a folder is locked |
| Root drive plus one data drive with `fast`, `primary` and `backup` | The listed folders on the data drive; `restic-repo` by restic's own encryption | The rest of the data drive, including `restic-cache`, `service-dumps` and `logs`; the root drive | The data drive alone: `restic-repo` (no password), the plaintext dumps, and the plain files outside the listed folders. The whole host: the repository and every file outside the listed folders | `unlock.sh`, which also mounts the data drive on first access; Docker restarts; the backup refuses while a folder is locked |
| Data drive plus a separate backup drive | The listed folders on the data drive; the local repository on the backup drive | The rest of the data drive; `service-dumps` and `logs` on the backup drive; the root drive | The data drive alone: its files, ciphertext for the listed folders. The backup drive alone: `restic-repo` (no password) and the plaintext dumps. The whole host: both repositories and every file outside the listed folders | The same: `unlock.sh` mounts every listed folder, Docker restarts, the backup refuses while a folder is locked |
| `fast` and `primary` on different drives, plus a backup drive | The listed folders of each drive, ciphertext on the drive that holds each one; both repositories | The rest of each drive; the root drive | One data drive alone: only the folders it holds, ciphertext for the listed ones | The same; `unlock.sh` asks for the passphrase once for all folders |

## Set up a folder

On a host you are setting up, do this before the service first starts, or it writes plain files into the folder: run `just deploy storage,common,encryption --limit <host>`, run the commands in step 2 (and step 4 only if the folder already holds data), then deploy everything. Repeat steps 2 to 5 for each folder; they share one passphrase.

Back up first and check the backup restores; the move in step 4 deletes the source files as it goes.

1. Add the paths to `encrypted_folders` and run `just deploy encryption,backup --limit <host>`. That installs gocryptfs and the scripts, and teaches the backups to refuse a locked folder and to skip the encrypted files (they would be stored twice).
2. Stop the service that uses the folder, and keep it stopped until step 5 is done. Rename a folder that already holds data, and create an empty one:

```bash
sudo mv /mnt/data/photos /mnt/data/photos.plain      # skip if the folder does not exist yet
sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/data/photos
sudo /opt/services/scripts/unlock.sh
```

The mounted folder's top directory takes the owner and mode of that empty folder, while everything inside keeps its own owner, so the folder a role created (owned by the deploy user) stays writable by it. A service running as another user id needs the top directory chowned while the folder is unlocked; a chown while it is locked lands on the hidden folder and changes nothing.

3. `init-encrypted-folder.sh` prints a **master key** once, and only when it runs in a terminal (`ssh -t <host> sudo ...`). Put it in your password manager, and copy `gocryptfs.conf` from the `.gocryptfs` folder off the host; each folder has its own key and file, and without them its data cannot be opened. The script picks the cipher for this CPU and it cannot be changed later. On a host without AES instructions (Raspberry Pi 4) that is XChaCha20, which needs gocryptfs 2.2 or later on any other machine that opens the folder, such as a Mac (`brew install gocryptfs macfuse`).
4. Move the data in, file by file:

```bash
cd /mnt/data/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt
sudo rsync -aHAX --remove-source-files /mnt/data/photos.plain/ /mnt/data/photos/
cd /mnt/data/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo identical
```

`--remove-source-files` deletes each file once it is copied, so the drive needs room for roughly the largest file plus about 1% overhead, not a second copy. (A sparse file takes its full size.) Take a backup and check that it restores first ([backups.md](./backups.md)): a power cut at the wrong moment can lose the file being moved. If the move stops half way, run the same `rsync` again.

5. When the lists are identical, remove the leftover empty folders (`sudo rm -r /mnt/data/photos.plain`) and start the service. From step 1 until `unlock.sh` has mounted the folder, every backup (local and cloud) refuses to run and stores nothing, dumps included, so do this in one sitting.

Deleting files does not erase them from the drive. A drive that held plain data may still hold it: re-format it before it leaves your hands. A new, empty drive needs none of this: set the folders up first, then copy the old data in.

### Turning it off

For each folder: unlock, copy the files out to a plain folder with `rsync -aHAX`, point the service at it, remove the path from `encrypted_folders`, run `just deploy encryption,backup --limit <host>`, then `sudo umount <folder>`, `sudo chattr -i <folder>` and delete both folders. The role removes the scripts it installed once no folder is left; gocryptfs stays installed.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each folder that is locked, then runs the scripts in `after-unlock.d`; containers started without a restart policy are not started again. A wrong passphrase stops it at that folder, and it says which one; the scripts still run if an earlier folder had already been mounted. It never uses `-nonempty`, and it stops if a locked folder is not empty (move the files away first) instead of hiding them. Run on an unlocked host it does nothing.

After a reboot, services with encrypted data stay down until someone unlocks, and the backups of every drive refuse to run while any listed folder is locked. A failed backup pushes an alert only if `ntfy_server` is set, and an ntfy server on this host is down when Docker is; point `ntfy_server` at another host (or `ntfy_alert_url` at ntfy.sh) to hear about a locked host. Otherwise the failure is only in the log (`logger -t backup`). The restart stops every container for up to 10 seconds, including ones with plain data.

To lock again: stop the containers that use the folder, then `sudo umount <folder>`.

### Unlocking from another device

`unlock.sh` also reads the passphrase from standard input (`printf %s "$PASSPHRASE" | sudo unlock.sh`), so anything that can run a command on the host can unlock it, not only a person at a terminal. That is the hook for the unlock page in [TODO.md](../TODO.md).

Unlocking works from any device that can SSH to the host. A borrowed device may record what you type. Afterwards change the passphrase of every folder with `sudo gocryptfs -passwd <the .gocryptfs folder>`. That does not re-encrypt the data, so it helps only if nobody copied `gocryptfs.conf`. Full protection means new gocryptfs folders and a copy of the files into them.

## If gocryptfs.conf is lost

Two ways back, per folder:

- **Master key:** make an empty folder, run `gocryptfs -init -masterkey <key> <empty folder>` with the same options the folder was created with, and copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. gocryptfs refuses `-init` in a folder that already holds files, which is why the new file is made elsewhere. `init-encrypted-folder.sh` adds `-xchacha` on a CPU with no AES (a Raspberry Pi 4); add it too. With the wrong options the mount succeeds but every read fails with an input/output error.
- **Backups:** they hold the decrypted files and exclude the `.gocryptfs` folders. Create a new encrypted folder, restore the snapshot to a scratch folder (`restic restore latest --target <scratch>`, [backups.md](./backups.md)), and `rsync -aHAX` the files in. With a local backup, the deploy fails if a listed folder is outside every path in `restic_local_rules`, so a folder always has such a backup; a cloud-only host is not checked.
