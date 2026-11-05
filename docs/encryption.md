# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot. Everything else, including containers with data in other folders, runs as before.

## The concepts

- **Plaintext and ciphertext.** Plaintext is your real file. Ciphertext is the same file after encryption: scrambled bytes that mean nothing without the key. The `.gocryptfs` folder holds ciphertext, and the listed folder is a live view of it that is decrypted as you read and encrypted as you write.
- **The master key.** One random 32-byte key does all the encrypting. It is made once, when the folder is created, and never changes. You never type it.
- **The passphrase.** What you type. It is short and guessable compared with 32 random bytes, so it is not the encryption key. It only locks the master key. That is why changing the passphrase is instant: the master key stays the same and is locked again under the new passphrase, so no file is re-encrypted.
- **Salt and scrypt.** gocryptfs turns the passphrase into a lock key with scrypt, a function that is deliberately slow (a fraction of a second per try), so an attacker guessing passphrases pays that for every guess. The salt is a random value made at creation and stored in the conf; it is mixed into the passphrase first, so lock keys cannot be precomputed once and reused against every folder. gocryptfs does both by itself. They are not settings.
- **`gocryptfs.conf`.** A small text file in each `.gocryptfs` folder holding the master key **locked** under the passphrase, the salt and scrypt settings, and the format (the cipher, and how names are encrypted). It is not secret on its own: without the passphrase the key inside stays locked. Without it, though, gocryptfs has no locked key to check your passphrase against and does not know the cipher. The backups keep a copy.
- **The master key printout.** `init-encrypted-folder.sh` prints the same 32 bytes in plain form, once. It is not a second key. The conf holds the key locked; the printout is the key unlocked. Keep it in a password manager, like a password: anyone with it and the ciphertext can read the files without the passphrase.

```
passphrase + salt ──scrypt──▶ lock key
gocryptfs.conf: locked master key ──lock key──▶ master key (kept in RAM only)
.photos.gocryptfs (ciphertext) ◀──master key──▶ /mnt/data/photos (plaintext view)
```

**Unlocking** (`unlock.sh`) runs that diagram once: it asks for the passphrase, reads the conf, derives the lock key and unlocks the master key (a wrong passphrase fails at this step), then mounts the folder so reads decrypt and writes encrypt. **Locking** (`umount`, or a reboot) makes gocryptfs forget the master key from RAM; the disk holds only ciphertext and a conf that needs the passphrase.

**Recovery** follows from this. Lost passphrase: nothing opens the conf, and only the master key printout still works. Lost conf: restore it from a backup, or make a new one from the master key printout, which writes a fresh conf holding the same key under a passphrase you choose ([If gocryptfs.conf is lost](#if-gocryptfsconf-is-lost)).

## What it protects

A drive that is lost, stolen, sold or sent back for repair, and a thief who has the whole host while it is off: file content is unreadable without the passphrase. Use a long random passphrase from a password manager; it is the weak point, not the 256-bit encryption.

It does not protect:

- a host that is running and unlocked;
- what the ciphertext's shape shows: the number of files and folders, their depth, roughly how long each name is, and every file's size (rounded up to 4 KiB) and modification time. The names themselves are encrypted;
- the root drive. A headless host cannot take a passphrase at boot, so it holds the restic password file and the Tailscale and Cloudflare credentials. A thief with the whole host can open the local and cloud backups, though not a listed folder;
- the backup logs, which list every backed-up path in plain text, and the service dumps ([Dumps and backups](#dumps-and-backups));
- a passphrase typed on a device that records it. After using a borrowed device, change the passphrase of every folder with `sudo gocryptfs -passwd <the .gocryptfs folder>` (gocryptfs's change-passphrase command), then run `sudo unlock.sh` (it gives the rewritten `gocryptfs.conf` to the ansible user, so the backups can still read it), then run a backup: older snapshots hold the conf with the old passphrase, and a backup is what stores the new one. That does not re-encrypt the data, so it helps only if nobody copied `gocryptfs.conf`.

## How it works

Each entry in `encrypted_folders` is the absolute path of one folder. gocryptfs keeps the ciphertext in a hidden folder beside it, in the same parent directory (`encrypted_pairs` in `group_vars/all/derived.yml`):

| Path | What it is |
|---|---|
| `/mnt/data/photos` | The decrypted view, mounted by `unlock.sh`. Services and backups use this path, so no data directory setting changes. |
| `/mnt/data/.photos.gocryptfs` | The encrypted files, on the same filesystem. |

Folders you do not list stay plain.

- **Locked folder.** It is an empty folder marked immutable (`chattr +i`), so a container or a deploy that runs too early fails with "Operation not permitted" instead of filling the drive underneath. `unlock.sh` sets the mark just before the first mount, and only on a filesystem that supports it (ext4, xfs, btrfs); elsewhere it warns and mounts anyway. Root can remove the flag, so it is a safety net against mistakes, not a security boundary.
- **Containers do not wait for the unlock.** One with data in a locked folder fails to start, or sees an empty folder, until `unlock.sh` restarts Docker (its `00-docker.sh` script). That stops every container for up to 10 seconds, including ones with plain data.
- **After-unlock scripts.** After mounting, `unlock.sh` runs every `<name>.sh` in `after-unlock.d` (`encryption_hooks_dir`, in `scripts_dir`) as root, in name order. The deploy installs `00-docker.sh` there and never touches your own. For other software that uses a listed folder (a systemd service, a supervisor program, a cron job), add a script with its restart command, for example `systemctl restart myapp`. A script that fails does not stop the others, and the unlock then exits with an error.
- **Docker's own storage** (`docker_data_root`) cannot be in a listed folder, because overlay2 does not run on a FUSE filesystem. The deploy fails if it is. `sshd` and Tailscale run on the host, so you can reach it to unlock.
- **Cipher.** `init-encrypted-folder.sh` picks it for the CPU: AES-GCM (gocryptfs's default, fastest) when the CPU has AES instructions, XChaCha20 when it has none (a Raspberry Pi 4). Both use 256-bit keys. The choice cannot be changed later, but it is recorded in the folder's `gocryptfs.conf`, so a folder opens on any CPU: an AES-GCM folder on a CPU without AES instructions is only slower. XChaCha20 needs gocryptfs 2.2 or later on any other machine that opens the folder (`brew install gocryptfs` and `brew install --cask macfuse`). To see which a folder uses: `grep -c XChaCha20Poly1305 <the .gocryptfs folder>/gocryptfs.conf` prints 1 for XChaCha20 and 0 for AES-GCM.

### Which folders to list

A `drives` mount point such as `/mnt/data` does not work: the ciphertext would go to `/mnt/.data.gocryptfs` on the root drive, `init-encrypted-folder.sh` refuses a folder that is not empty (a formatted drive holds `lost+found`), and `unlock.sh` skips a folder that is already a mount point. List the folders that hold data instead. With the default data directories and a drive at `/mnt/data` that claims `fast` and `primary` ([storage.md](./storage.md#examples)):

```yaml
encrypted_folders:
  - /mnt/data/docker   # every service's data directory on the fast drive
  - /mnt/data/stacks   # Dockge stacks
  - /mnt/data/photos   # Immich's photos
  - /mnt/data/files    # Copyparty's files
  - /mnt/data/apps     # pics' photos and trash (pics_photos_dir, pics_trash_dir), if pics is on
```

Listing `/mnt/data/docker` encrypts every service's database too, including Immich's Postgres (`immich_db_data_location`), which holds file names, dates, locations and face data. Databases make many small writes and every one passes through the encryption, so they are the slowest thing to encrypt. Try it with your real workload before moving data in. The folder is then locked after every boot, and Immich stays down until `unlock.sh` runs.

`/mnt/data/fast` and `/mnt/data/collab` also hold data when `copyparty_fast_enabled` and `copyparty_collab_enabled` are on. A service added later with its data under `{{ fast_drive }}/docker` is covered without a change. Anything else on the drive stays plain.

## Dumps and backups

`backup-services.sh` writes the Immich, Gitea and Garage dumps to `service_dumps_dir` (`<backup drive>/service-dumps`, or `/var/lib/backup-work/service-dumps` without a local backup). Nothing encrypts that folder unless you list it, so until then whoever finds the drive reads the Immich database, Gitea's dump and Garage's node key. To list it, add it to `encrypted_folders` and to `restic_local_extra_rules` (a listed folder outside every path in `restic_local_rules` stops the deploy, `roles/backup/tasks/check_coverage.yml`). Both backup scripts then refuse to run while it is locked, like any listed folder.

restic encrypts everything it writes: contents, file names and snapshot metadata. The password is `vault_restic_password`, written to `restic_password_file` on the root drive; with it, everything in the repository is readable, including a listed folder's files, which restic reads through the mount as decrypted files. For that reason the ciphertext is left out of every backup (`roles/backup/templates/restic-excludes-services.txt.j2`): saving it too would store everything twice. Each folder's `gocryptfs.conf` is the exception: it is kept in every backup that covers the folder, so it can be restored with the data.

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

3. `init-encrypted-folder.sh` prints a **master key** once, and only in a terminal (`ssh -t <host> sudo ...`). Put it in your password manager. If the script is interrupted after it creates the `.gocryptfs` folder, that folder is left empty and the next run refuses to continue: remove it with `sudo rmdir <the .gocryptfs folder>` and run the script again. Each folder has its own `gocryptfs.conf` in its `.gocryptfs` folder, and without it and the passphrase (or the master key) its encrypted files cannot be opened; the backups keep a copy (below), and a copy off the host is cheap insurance for a host with no backup.
4. Move the data in, file by file:

```bash
cd /mnt/data/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt
sudo rsync -aHAX --remove-source-files /mnt/data/photos.plain/ /mnt/data/photos/
cd /mnt/data/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo identical
```

`--remove-source-files` deletes each file once copied, so the drive needs room for about the largest file plus 1% overhead, not a second copy. A power cut at the wrong moment can lose the file being moved. If the move stops half way, run the same `rsync` again.

5. When the lists are identical, remove the leftover folders (`sudo rm -r /mnt/data/photos.plain`) and start the service. From step 1 until `unlock.sh` has mounted the folder, every backup refuses to run and stores nothing, dumps included, so do this in one sitting.

After the first backup, check that it holds the conf: `restic ls latest | grep gocryptfs.conf` (with a local backup, using the repository from [backups.md](./backups.md)) should print one line per listed folder.

Deleting files does not erase them from the drive. A drive that held plain data may still hold it: re-format it before it leaves your hands. On a new, empty drive, set the folders up first, then copy the old data in.

### Turning it off

For each folder: unlock, copy the files out to a plain folder with `rsync -aHAX`, point the service at it, remove the path from `encrypted_folders`, run `just deploy encryption,backup --limit <host>`, then `sudo umount <folder>`, `sudo chattr -i <folder>` and delete both folders. The role removes the scripts once no folder is left; gocryptfs stays installed. `teardown.yml` (also `--tags encryption`) removes the scripts and, when it is empty, the after-unlock directory; it never touches encrypted folders or your own after-unlock scripts. `-e remove_data=true` on a service whose data directory is a listed folder fails whether the folder is locked or not (unlocked, it deletes the files and then cannot remove the mount point; locked, the folder is immutable): turn encryption off for that folder first.

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

It mounts each locked folder, then runs the scripts in `after-unlock.d`; containers started without a restart policy are not started again. A wrong passphrase stops it at that folder and says which; the scripts still run if an earlier folder had been mounted. It stops if a locked folder is not empty (move the files away first) instead of hiding them, and it does nothing on an unlocked host. The passphrase can also arrive on standard input (`printf %s "$PASSPHRASE" | sudo .../unlock.sh`).

After a reboot, services with encrypted data stay down until someone unlocks, and the backups of every drive refuse to run while any listed folder is locked. A failed backup pushes an alert only if `ntfy_alert_url` is set, and an ntfy server on this host is down when Docker is; point `ntfy_alert_url` at another host's ntfy (or at ntfy.sh) to hear about a locked host.

To lock again: stop the containers that use the folder, then `sudo umount <folder>`.

### Doing it by hand

The scripts are thin: they run these gocryptfs commands and add checks. You can run the commands yourself (for a folder in `encrypted_folders`, so the backups still guard and skip it correctly).

<details>
<summary>Create a folder without <code>init-encrypted-folder.sh</code></summary>

```bash
sudo mkdir -p /mnt/data/photos                        # must be empty
sudo mkdir /mnt/data/.photos.gocryptfs                # the encrypted files, beside the folder
sudo chown --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs    # the mounted folder shows this owner and mode
sudo chmod --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs
sudo gocryptfs -init -xchacha /mnt/data/.photos.gocryptfs             # drop -xchacha if `grep -w aes /proc/cpuinfo` prints something
```

Run it in a terminal: the passphrase prompt and the one-time master key need one. The script adds the refusal to overwrite an existing folder and picks the cipher for the CPU.

</details>

<details>
<summary>Unlock without <code>unlock.sh</code></summary>

```bash
sudo chown <ansible user> /mnt/data/.photos.gocryptfs/gocryptfs.conf    # so the backups can read it (gocryptfs makes it root-only)
sudo chattr +i /mnt/data/photos                                         # optional: while locked, nothing can write into the empty folder
sudo gocryptfs -allow_other /mnt/data/.photos.gocryptfs /mnt/data/photos # asks for the passphrase; -allow_other lets containers read it
sudo systemctl restart docker                                           # or restart the containers that use the folder
```

Lock again with `sudo umount /mnt/data/photos`. The script does the same for every folder with one passphrase prompt, refuses a folder that is not empty, and runs your `after-unlock.d` scripts.

</details>

## If gocryptfs.conf is lost

Per folder, in order of ease:

- **Backups:** restore the conf: `restic restore latest --target <scratch> --include <the .gocryptfs folder>/gocryptfs.conf` ([backups.md](./backups.md)), put it back in the `.gocryptfs` folder, and unlock as usual. It needs the passphrase, not the master key, and the cipher is inside it.
- **Master key:** make an empty folder, run `sudo gocryptfs -init -masterkey <key> <empty folder>` with the same cipher option the folder was created with (`-xchacha` for a folder made on a CPU without AES instructions, such as a Pi 4; none for one made on a CPU with them, such as a Pi 5 or an x64 PC. The `grep` above cannot help here, because the conf is what was lost), then copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. gocryptfs refuses `-init` in a folder that already holds files, which is why the new file is made elsewhere. `init-encrypted-folder.sh` adds `-xchacha` on a CPU with no AES (a Raspberry Pi 4); add it too. With the wrong option the mount succeeds but every read fails with an input/output error.
- **Files only:** if the whole `.gocryptfs` folder is gone, the backups still hold the decrypted files. Create a new encrypted folder, restore the snapshot to a scratch folder (`restic restore latest --target <scratch>`, [backups.md](./backups.md)), and `rsync -aHAX` the files in. With a local backup the deploy fails if a listed folder is outside every path in `restic_local_rules`, so a folder always has such a backup; a cloud-only host is not checked.
