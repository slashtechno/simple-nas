# Encryption at rest

Optional. List folders in `encrypted_folders` and their files are stored encrypted with [gocryptfs](https://nuetzlich.net/gocryptfs/). You unlock them by hand after each boot; everything else runs as before. A full walk-through on a new host: [quick-start.md](./quick-start.md).

| I want to | Go to |
|---|---|
| Unlock after a reboot | [Unlocking](#unlocking) |
| Recover after losing `gocryptfs.conf` | [If gocryptfs.conf is lost](#if-gocryptfsconf-is-lost) |
| Encrypt a folder | [Set up a folder](#set-up-a-folder) |
| Stop encrypting a folder | [Turning it off](#turning-it-off) |
| Know what is and is not protected | [What it protects](#what-it-protects) |
| Check backups still work | [Dumps and backups](#dumps-and-backups) |

## Unlocking

After every boot:

```bash
ssh <host>
sudo /opt/services/scripts/unlock.sh      # asks for the passphrase once
```

- It mounts each locked folder, then runs the scripts in `after-unlock.d`. It does nothing on an unlocked host.
- A wrong passphrase stops it at that folder and says which. A locked folder that is not empty stops it too (move the files away first).
- The passphrase can come from standard input: `printf %s "$PASSPHRASE" | sudo .../unlock.sh`.
- Until you unlock, encrypted services stay down and **no backup runs**. Set `ntfy_alert_url` to another host's ntfy (or ntfy.sh) to hear about a locked host; an ntfy on this host is down with Docker.
- To lock again: stop the containers that use the folder, then `sudo umount <folder>`.

<details>
<summary>Unlock or create a folder by hand, without the scripts</summary>

The scripts run a few gocryptfs commands and add checks. For a folder in `encrypted_folders` the backups still guard and skip it while it is locked.

Create (in a terminal: the passphrase prompt and the one-time master key need one):

```bash
sudo mkdir -p /mnt/data/photos                    # must be empty
sudo mkdir /mnt/data/.photos.gocryptfs            # the encrypted files, beside the folder
sudo chown --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs
sudo chmod --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs
sudo gocryptfs -init -xchacha /mnt/data/.photos.gocryptfs   # drop -xchacha if `grep -w aes /proc/cpuinfo` prints anything
```

`--reference=FILE` copies the owner or mode of FILE, so the mounted folder gets the owner you gave the plain one. The script also refuses to overwrite an existing folder and picks the cipher for you.

Unlock:

```bash
sudo chown <ansible user> /mnt/data/.photos.gocryptfs/gocryptfs.conf    # gocryptfs makes it root-only; the backups run as this user
sudo chattr +i /mnt/data/photos                                         # optional: nothing can be written into the empty folder while locked
sudo gocryptfs -allow_other /mnt/data/.photos.gocryptfs /mnt/data/photos # asks for the passphrase; -allow_other lets containers read it
sudo systemctl restart docker                                           # or restart just the containers that use the folder
```

Lock again with `sudo umount /mnt/data/photos`.

</details>

## If gocryptfs.conf is lost

Per folder, easiest first:

1. **From a backup:** `restic restore latest --target <scratch> --include <the .gocryptfs folder>/gocryptfs.conf` ([backups.md](./backups.md)), put it back in the `.gocryptfs` folder, unlock as usual. It needs the passphrase, not the master key.
2. **From the master key:** in an empty folder run `sudo gocryptfs -init -masterkey <key> <empty folder>` with the **same cipher option** the folder was created with (`-xchacha` if made on a CPU without AES such as a Pi 4; none otherwise). Copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. With the wrong option the mount succeeds but every read fails with an input/output error.
3. **Files only:** if the whole `.gocryptfs` folder is gone, the backups still hold the decrypted files. Create a new encrypted folder, restore the snapshot to a scratch folder (`restic restore latest --target <scratch>`) and `rsync -aHAX` the files in. A host with a local backup is always covered ([backups.md](./backups.md#what-is-backed-up-where)); a cloud-only host is not checked.

<details>
<summary>Not sure which cipher option was used</summary>

Try each on a scratch mount: `gocryptfs -ro [-xchacha] -masterkey=stdin <the .gocryptfs folder> <empty folder>`, key on stdin. The wrong option lists the file names but `sha256sum` on a file fails with an input/output error; the right one reads it. Unmount with `fusermount -u`.

</details>

## What it protects

| Protects | Does not protect |
|---|---|
| A lost, stolen, sold or repaired drive; a thief with the whole host while it is off | A host that is running and unlocked |
| File contents and names | The number, depth, size (to 4 KiB) and modification time of files |
| | The root drive: it holds the restic password and the Tailscale and Cloudflare logins, so a thief with the whole host can open the backups |
| | Backup logs (they list every path) and service dumps, unless you list the dumps folder ([below](#dumps-and-backups)) |

Use a long random passphrase from a password manager; it is the weak point, not the 256-bit cipher.

**After typing the passphrase on a device you do not trust:** run `sudo gocryptfs -passwd <the .gocryptfs folder>` for every folder, then `sudo unlock.sh` (it gives the rewritten `gocryptfs.conf` to the ansible user so backups can read it), then run a backup (older snapshots hold the old passphrase). This does not re-encrypt data, so it helps only if nobody copied the conf.

## Set up a folder

Do this **before the service first starts**, or it writes plain files into the folder. On a new host: `just deploy storage,common --limit <host>`, then steps 1 to 5 for each folder (one shared passphrase), then deploy everything. If the folder already holds data, run a backup first: once the path is listed, both backups refuse to run until it is unlocked, and step 4 deletes the source files as it goes.

1. Add the paths to `encrypted_folders` ([which folders](#which-folders-to-list)) and run `just deploy encryption,backup --limit <host>`.
2. Stop the service that uses the folder until step 5. Rename a folder that holds data, then create the encrypted one, in a terminal (it prints the master key only there; from your computer use `ssh -t <host> sudo ...`):

   ```bash
   sudo mv /mnt/data/photos /mnt/data/photos.plain      # skip if the folder does not exist yet
   sudo /opt/services/scripts/init-encrypted-folder.sh /mnt/data/photos
   sudo /opt/services/scripts/unlock.sh
   ```

3. **Save the master key** in your password manager. If the script is interrupted after creating the `.gocryptfs` folder, remove that empty folder with `sudo rmdir` and run it again. A copy of each `gocryptfs.conf` off the host is cheap insurance.
4. Move the data in, with a checksum comparison:

   ```bash
   cd /mnt/data/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt
   sudo rsync -aHAX --remove-source-files /mnt/data/photos.plain/ /mnt/data/photos/
   cd /mnt/data/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
   diff /tmp/before.txt /tmp/after.txt && echo identical
   ```

   You need room for the largest file plus 1%, not a second copy. Re-run the same `rsync` if it stops half way; a power cut can lose the file being moved.
5. When the lists match, `sudo rm -r /mnt/data/photos.plain` and start the service. Until `unlock.sh` has mounted the folder every backup refuses to run, so do this in one sitting.

The mounted folder's top directory takes the owner and mode of the empty folder it was created from (root's). A service running as another user needs it chowned **while unlocked**; a chown while locked is lost. Deleting files does not erase them from a drive: re-format a drive that held plain data before it leaves your hands.

### Which folders to list

List the folders that hold data, not a drive's mount point (`/mnt/data` would put the ciphertext on the root drive, and a formatted drive is not empty because of `lost+found`). With the default paths and one drive at `/mnt/data` holding `fast` and `primary` ([layout: storage.md](./storage.md#what-lives-where)):

```yaml
encrypted_folders:
  - /mnt/data/appdata  # the databases and configs of every service this repo deploys
  - /mnt/data/stacks   # Dockge stacks
  - /mnt/data/photos   # Immich's photos
  - /mnt/data/files    # Copyparty's files
  - /mnt/data/apps     # pics' photos and trash, if pics is on
```

- A listed folder must not sit inside another; the deploy fails if one does.
- `appdata` includes every database, Immich's Postgres too. Databases write often, so they are the slowest thing to encrypt: try your real workload first.
- `fast` and `collab` hold data when `copyparty_fast_enabled` and `copyparty_collab_enabled` are on.
- A service added later with its data under `{{ fast_drive }}/appdata` is covered automatically. Anything else stays plain.

### Turning it off

The same checksum move as step 4, in the other direction. Stop the services that use the folder first.

<details>
<summary>The commands</summary>

```bash
cd /mnt/data/photos && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/before.txt   # the folder must be unlocked
sudo mkdir /mnt/data/photos.plain
sudo rsync -aHAX --remove-source-files /mnt/data/photos/ /mnt/data/photos.plain/
cd /mnt/data/photos.plain && find . -type f -exec sha256sum {} + | sort -k2 > /tmp/after.txt
diff /tmp/before.txt /tmp/after.txt && echo identical
```

</details>

If it stops half way, run the same `rsync` again. When the lists match:

1. Remove the path from `encrypted_folders` and run `just deploy encryption,backup --limit <host>`.
2. `sudo umount /mnt/data/photos && sudo chattr -i /mnt/data/photos`
3. `sudo rm -r /mnt/data/photos /mnt/data/.photos.gocryptfs && sudo mv /mnt/data/photos.plain /mnt/data/photos`, then start the service.

The role removes the scripts when no folder is left; gocryptfs stays installed. The old ciphertext, master key and passphrase for that folder are no longer needed.

`teardown.yml` (or `--tags encryption`) removes the scripts and the empty after-unlock folder, and never touches encrypted folders or your scripts. `-e remove_data=true` on a service whose data folder is, or holds, a listed folder stops before it deletes anything: turn encryption off for it first.

## Dumps and backups

- **Dumps:** `backup-services.sh` writes the Immich, Gitea and Garage dumps to `service_dumps_dir` (`<backup drive>/service-dumps`). Nothing encrypts it unless you list it, so until then anyone holding the backup drive can read Immich's database, Gitea's dump and Garage's node key. To list it, add it to `encrypted_folders` and `restic_local_extra_rules` ([backups.md](./backups.md#what-is-backed-up-where) checks every listed folder is covered).
- **Backups:** both scripts refuse to run while any listed folder is locked. restic reads the folder through the mount (decrypted) and encrypts it with `vault_restic_password`. The ciphertext is left out of every backup (it would be stored twice), but each folder's `gocryptfs.conf` is kept, so it restores with the data.
- **Check after the first backup:** `restic ls latest | grep gocryptfs.conf` prints one line per listed folder.

## How it works

<details>
<summary>Folders, scripts, cipher and Docker (what to know before changing anything)</summary>

Each entry in `encrypted_folders` is the path of one folder. The ciphertext sits beside it in a hidden folder (`encrypted_pairs` in `group_vars/all/derived.yml`): `/mnt/data/photos` is the decrypted view mounted by `unlock.sh` (services and backups use this path, so no data setting changes), and `/mnt/data/.photos.gocryptfs` holds the encrypted files on the same filesystem.

- **Locked folder:** an empty folder marked immutable (`chattr +i`), so a container or deploy that runs too early fails with "Operation not permitted" instead of filling the drive. It needs ext4, xfs or btrfs (elsewhere `unlock.sh` warns and mounts anyway). Root can remove the flag: a safety net, not a security boundary.
- **Containers do not wait:** one with data in a locked folder fails or sees an empty folder until `unlock.sh` restarts Docker, which stops every container while it restarts.
- **After-unlock scripts:** `unlock.sh` runs every `<name>.sh` in `after-unlock.d` (`encryption_hooks_dir`) as root, in name order. Add your own to start other software. A failing script does not stop the others; the unlock then exits with an error.
- **Docker's storage** (`docker_data_root`) cannot be in a listed folder (overlay2 does not run on FUSE); the deploy fails if it is. `sshd` and Tailscale run on the host, so you can still log in to unlock.
- **Cipher:** AES-GCM when the CPU has AES instructions, XChaCha20 when not (a Raspberry Pi 4). Both are 256-bit. It is fixed at creation and recorded in the conf, so a folder opens on any CPU. Another machine needs gocryptfs 2.2+ for XChaCha20 (`brew install gocryptfs` and `brew install --cask macfuse`). `grep -c XChaCha20Poly1305 <the .gocryptfs folder>/gocryptfs.conf` prints 1 for XChaCha20.

</details>

<details>
<summary>How the keys work (plaintext, master key, passphrase, <code>gocryptfs.conf</code>)</summary>

- **Plaintext / ciphertext.** Plaintext is your real file; ciphertext is the scrambled version on disk. The `.gocryptfs` folder holds ciphertext. The listed folder is a live view of it, decrypted as you read and encrypted as you write.
- **Master key.** One random 32-byte key does all the encrypting. It is made once and never changes. You never type it.
- **Passphrase.** What you type. It only *locks* the master key, so changing it is instant: nothing is re-encrypted.
- **Salt and scrypt.** gocryptfs turns the passphrase into the lock key with scrypt, which is deliberately slow, so each guess costs an attacker time. The salt keeps lock keys from being precomputed. Both are automatic.
- **`gocryptfs.conf`.** In each `.gocryptfs` folder: the master key locked under the passphrase, plus the salt, scrypt settings and cipher. It is not secret alone, but without it nothing opens. The backups keep a copy.
- **Master key printout.** `init-encrypted-folder.sh` prints the master key once. Keep it in a password manager: with it and the ciphertext, anyone can read the files.

```
passphrase + salt ──scrypt──▶ lock key
gocryptfs.conf: locked master key ──lock key──▶ master key (kept in RAM only)
.photos.gocryptfs (ciphertext) ◀──master key──▶ /mnt/data/photos (plaintext view)
```

Unlocking runs that once and mounts the folder; a wrong passphrase fails at the lock-key step. Locking (`umount`, or a reboot) drops the master key from RAM.

</details>
