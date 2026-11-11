# Encryption at rest

Optional. List folders in `encrypted_folders` and [gocryptfs](https://nuetzlich.net/gocryptfs/) stores their files encrypted. You unlock them by hand after each boot. Everything else runs as before. A full walk-through on a new host: [quick-start.md](./quick-start.md).

| I want to | Go to |
|---|---|
| Unlock after a reboot | [Unlocking](#unlocking) |
| Unlock from a browser | [unlock-page/README.md](../unlock-page/README.md) |
| Recover after losing `gocryptfs.conf` | [If gocryptfs.conf is lost](#if-gocryptfsconf-is-lost) |
| Know what happens to containers | [Containers and locked folders](#containers-and-locked-folders) |
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
- A wrong passphrase stops it. A folder it cannot unlock (never set up, not empty: move the files away first) is reported, and the others still unlock.
- From your computer: `just unlock <host>`, and `just encryption-status <host>` for the status below.
- `sudo .../unlock.sh --status` shows each folder as unlocked, locked, or without encrypted files (never set up, or its drive is not mounted). It also lists the containers that wait for a locked folder. It changes nothing.
- The passphrase can come from standard input: `printf %s "$PASSPHRASE" | sudo .../unlock.sh`.
- Until you unlock, services that use an encrypted folder see it empty or do not start ([containers](#containers-and-locked-folders)), and **no backup runs**. What still works depends on where its data is: see [Keep these out of a listed folder](#which-folders-to-list).
- To lock again: stop the containers that use the folder (`docker ps` and the compose file show them), then `sudo umount <folder>`.

<details>
<summary>Unlock or create a folder by hand, without the scripts</summary>

`setup-encrypted-folder.sh` and `unlock.sh` run these commands and add checks: they pick the cipher for you and move existing files in. A listed folder that stays locked still stops both backups.

Create (in a terminal: the passphrase prompt and the one-time master key need one):

```bash
sudo mkdir -p /mnt/data/photos                    # must be empty
sudo mkdir /mnt/data/.photos.gocryptfs            # the encrypted files, beside the folder
sudo chown --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs
sudo chmod --reference=/mnt/data/photos /mnt/data/.photos.gocryptfs
sudo gocryptfs -init -xchacha /mnt/data/.photos.gocryptfs   # drop -xchacha if `grep -w aes /proc/cpuinfo` prints anything
```

`--reference=FILE` copies the owner or mode of FILE, so the mounted folder gets the owner you gave the plain one.

Unlock:

```bash
sudo chown <ansible user> /mnt/data/.photos.gocryptfs/gocryptfs.conf    # gocryptfs makes it root-only; the backups run as this user
sudo chattr +i /mnt/data/photos                                         # optional: nothing can be written into the empty folder while locked
sudo gocryptfs -allow_other /mnt/data/.photos.gocryptfs /mnt/data/photos # asks for the passphrase; -allow_other lets containers read it
sudo docker restart <the containers that use the folder>
```

Lock again with `sudo umount /mnt/data/photos`.

</details>

## Containers and locked folders

Docker, SSH and Tailscale live on the root drive, so they run while folders are locked. A container sees what is at its mount when it starts.

| Container | While locked | After you unlock |
|---|---|---|
| Mounts the locked folder, or one above it | Starts and sees it empty; writes fail with "Operation not permitted" | Restarted |
| Mounts a folder inside it (`appdata/<service>`) | Never starts: Docker cannot create the folder (state `created`) | Started |
| Mounts no listed folder, including your own `docker run` | Runs normally | Not touched |
| Stopped on purpose | Stays stopped | Stays stopped |

`00-containers.sh` (in `after-unlock.d`) does the restarting, whatever a container's restart policy, and prints each name. `unlock.sh --status` lists the waiting containers without changing anything.

**Docker's own storage** (`docker_data_root`: images, layers, logs, named volumes) cannot be in a listed folder: overlay2 does not run on FUSE, and the deploy fails if you try. It holds public images and whatever a container writes outside a bind mount. The repo keeps service data in bind mounts (its one named volume is Immich's public model cache), so listing the data folders covers it. For a service of your own, use a bind mount for private data.

## If gocryptfs.conf is lost

Per folder, easiest first:

1. **From a backup:** `restic restore latest --target <scratch> --include <the .gocryptfs folder>/gocryptfs.conf` ([backups.md](./backups.md)), put it back in the `.gocryptfs` folder, unlock as usual. It needs the passphrase, not the master key.
2. **From the master key:** in an empty folder run `sudo gocryptfs -init -masterkey <key> <empty folder>`. Give it the **same cipher option** the folder was created with. `setup-encrypted-folder.sh` prints it (`-xchacha` or none) next to the master key, so you saved it with the key. Do not guess from today's CPU: the script chose it from the CPU that created the folder, which may not be the CPU you use now. Copy the `gocryptfs.conf` it writes into the `.gocryptfs` folder. With the wrong option the mount succeeds but every read fails with an input/output error.
3. **Whole `.gocryptfs` folder gone:** the encrypted files are gone, so there is nothing left to unlock. The backups hold your files in plain form (restic encrypts them with `vault_restic_password`), so restore from there:
   1. [Set up a new encrypted folder](#set-up-a-folder) at the same path. It gets a new master key. Save it.
   2. Restore the latest snapshot to a scratch folder: `restic restore latest --target <scratch>`.
   3. Copy the files in: `sudo rsync -aHAX <scratch>/<path of the folder>/ <the folder>/` ([flags](./storage.md#copying-data-with-rsync)).

   This works only if the backup includes the folder. On a host with a local backup the deploy checks that every listed folder is in it, so it always does. On a host with only a cloud backup nothing checks: look in `restic_cloud_rules` and `restic_cloud_extra_rules` ([backups.md](./backups.md#what-is-backed-up-where)).

<details>
<summary>Not sure which cipher option was used</summary>

Try each on a scratch mount: `gocryptfs -ro [-xchacha] -masterkey=stdin <the .gocryptfs folder> <empty folder>`, key on stdin. The wrong option lists the file names but `sha256sum` on a file fails with an input/output error. The right one reads it. Unmount with `fusermount -u`.

</details>

## What it protects

| Protects | Does not protect |
|---|---|
| A drive lost, stolen, sold or repaired. A thief with the whole host while it is off | A host that is running and unlocked |
| File contents and names | The number, depth, size (to 4 KiB) and modification time of files |
| | The root drive: it holds the restic password and the Tailscale and Cloudflare logins, so a thief with the whole host can open the backups |
| | Backup logs (they list every path) and service dumps, unless you list the dumps folder ([below](#dumps-and-backups)) |

Use a long random passphrase from a password manager. It is the weak point, not the 256-bit cipher.

**After typing the passphrase on a device you do not trust:** run `sudo gocryptfs -passwd <the .gocryptfs folder>` for every folder. Then run `sudo /opt/services/scripts/unlock.sh` (it gives the rewritten `gocryptfs.conf` to the ansible user so backups can read it). Then run a backup (older snapshots hold the old passphrase). This does not re-encrypt data, so it helps only if nobody copied the conf.

## Set up a folder

Do this **before the service first starts**, or it writes plain files into the folder. Run a backup first if the folder already holds data. Once you list a folder, both backups refuse to run until you unlock it.

1. Add the paths to `encrypted_folders` ([which folders](#which-folders-to-list)) and run `just deploy encryption,backup --limit <host>`.
2. Stop the containers that use the folder (`docker stop <name>`). The script lists any that are still running.
3. Run the script for each folder, in a terminal (`ssh -t <host>`). It asks for the passphrase and shows the master key only in a terminal:

   ```bash
   sudo /opt/services/scripts/setup-encrypted-folder.sh /mnt/data/photos
   ```

   The script does these steps. Each one checks what is already done, so after a lost connection run the same command again.
   - It takes checksums of the existing files, and renames the folder to `photos.plain`.
   - It creates the encrypted files and mounts the folder. The folder keeps the owner and mode of the old one.
   - It moves the files in, compares checksums, and removes `photos.plain` when they match. It needs room for the largest file plus 1%, not a second copy.
4. **Save the master key and the cipher option** the script printed in your password manager. A copy of each `gocryptfs.conf` off the host is cheap insurance.
5. Start the containers. Until a folder is unlocked, every backup refuses to run, so do steps 3 to 5 in one sitting.

On a new host, do `just deploy storage,common --limit <host>` first, deploy everything after the last folder, and use one passphrase for all folders.

If the script reports a checksum mismatch it deletes nothing, but the files are then split between `photos` and `photos.plain`: look in both, then run the script again. A power cut can lose the one file being moved.

A service that runs as another user needs the folder's owner changed **while unlocked**. A change while locked is lost.

Removing files does not wipe them from a drive: re-format a drive that held plain data before it leaves your hands.

### Which folders to list

List the folders that hold data, not a drive's mount point. `/mnt/data` would put the ciphertext on the root drive, and a formatted drive is not empty because of `lost+found`. With the default paths and one drive at `/mnt/data` holding `fast` and `primary` ([layout: storage.md](./storage.md#what-lives-where)):

```yaml
encrypted_folders:
  - /mnt/data/appdata  # the databases and configs of every service this repo deploys
  - /mnt/data/stacks   # Dockge stacks
  - /mnt/data/photos   # Immich's photos
  - /mnt/data/files    # Copyparty's files
  - /mnt/data/apps     # pics' photos and trash, if pics is on
```

- A listed folder must not sit inside another. The deploy fails if one does.
- The deploy also fails for a folder that is, or holds, something you need to log in and unlock: `scripts_dir`, your home folder, `/etc`, `/usr`, `/boot`, `/root`, `/var/lib` or `docker_data_root`.
- `appdata` includes every database, Immich's Postgres too. Databases write often, so they are the slowest thing to encrypt: try your real workload first.
- `fast` and `collab` hold data when `copyparty_fast_enabled` and `copyparty_collab_enabled` are on.
- The defaults cover a service added later with its data under `{{ fast_drive }}/appdata`. Anything else stays plain.

**Keep these out of a listed folder** if you need them while the host is locked. The deploy does not stop you: it cannot know what you need.

| Data | Setting | If it is in a listed folder |
|---|---|---|
| ntfy | `ntfy_data_dir` | No alerts from this host until you unlock. Use an ntfy on another host (`ntfy_alert_url`), or keep this one's data in a plain folder such as `/mnt/apps/ntfy`. |
| Caddy | `caddy_data_dir` | No web access to any service until you unlock. |
| Tinyauth | `tinyauth_data_dir` | No Tinyauth login until you unlock. |
| An unlock page on this host | the page's own folder | The page cannot start, so you cannot unlock with it. |

The defaults put all three under `{{ fast_drive }}/appdata`, so listing `appdata` locks them. To keep one plain, set its `*_data_dir` to a folder you do not list. This is true with or without Tinyauth: with Tinyauth off, only the other rows apply. The page: [unlock-page/README.md](../unlock-page/README.md#where-to-run-it).

`vault_ntfy_token` goes to whatever server `ntfy_alert_url` names, so it suits an ntfy you run, not ntfy.sh.

### Turning it off

The same checksum move as in step 3, in the other direction. Stop the services that use the folder first.

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

If it stops half way, run the same `rsync` again ([flags](./storage.md#copying-data-with-rsync)). When the lists match:

1. Remove the path from `encrypted_folders` and run `just deploy encryption,backup --limit <host>`.
2. `sudo umount /mnt/data/photos && sudo chattr -i /mnt/data/photos`
3. `sudo rm -r /mnt/data/photos /mnt/data/.photos.gocryptfs && sudo mv /mnt/data/photos.plain /mnt/data/photos`, then start the service.

The role removes the scripts when no folder remains. gocryptfs stays installed. You can drop the old ciphertext, master key and passphrase for that folder.

`teardown.yml` (or `--tags encryption`) removes the scripts and the empty after-unlock folder, and never touches encrypted folders or your scripts. `-e remove_data=true` on a service whose data folder is, or holds, a listed folder stops before it removes anything: turn encryption off for it first.

## Dumps and backups

- **Dumps:** `backup-services.sh` writes the Immich, Gitea and Garage dumps to `service_dumps_dir` (`<backup drive>/service-dumps`, or on the root drive for a host with no local backup). Nothing encrypts it unless you list it, so until then anyone holding that drive can read Immich's database, Gitea's dump and Garage's node key. To list it, add it to `encrypted_folders` and `restic_local_extra_rules` ([backups.md](./backups.md#what-is-backed-up-where) checks that every listed folder appears in a rule).
- **Backups:** both scripts refuse to run while any listed folder stays locked. restic reads the folder through the mount (decrypted) and encrypts it with `vault_restic_password`. Every backup leaves out the ciphertext (it would be stored twice), but keeps each folder's `gocryptfs.conf`, so it restores with the data.
- **Check after the first backup:** `restic ls latest | grep gocryptfs.conf` prints one line per listed folder ([backups.md](./backups.md)).

## How it works

Each listed folder is a live decrypted view. The ciphertext sits beside it in a hidden `.<name>.gocryptfs` folder on the same drive.

<details>
<summary>Folders, scripts and cipher (what to know before changing anything)</summary>

Each entry in `encrypted_folders` is the path of one folder. The ciphertext sits beside it in a hidden folder (`encrypted_pairs` in `group_vars/all/derived.yml`). `/mnt/data/photos` is the decrypted view that `unlock.sh` mounts (services and backups use this path, so no data setting changes). `/mnt/data/.photos.gocryptfs` holds the encrypted files on the same filesystem.

- **Locked folder:** empty and marked immutable (`chattr +i`). A container or deploy that runs too early fails with "Operation not permitted" instead of filling the drive. It needs ext4, xfs or btrfs (elsewhere `unlock.sh` warns and mounts anyway). Root can remove the flag: a safety net, not a security boundary.
- **After-unlock scripts:** `unlock.sh` runs every `<name>.sh` in `after-unlock.d` (`encryption_hooks_dir`) as root, in name order, and gives each the folders it just mounted as arguments. `00-containers.sh` ([above](#containers-and-locked-folders)) comes first. Add your own to start other software. A failing script does not stop the others. The unlock then exits with an error.
- **Cipher:** AES-GCM when the CPU has AES instructions, XChaCha20 when not (a Raspberry Pi 4). Both are 256-bit. gocryptfs sets it at creation and records it in the conf, so a folder opens on any CPU. Another machine needs gocryptfs 2.2+ for XChaCha20 (on a Mac: gocryptfs and macFUSE). `grep -c XChaCha20Poly1305 <the .gocryptfs folder>/gocryptfs.conf` prints 1 for XChaCha20.

</details>

<details>
<summary>How the keys work (plaintext, master key, passphrase, <code>gocryptfs.conf</code>)</summary>

- **Plaintext / ciphertext.** Plaintext is your real file. Ciphertext is the scrambled version on disk. The `.gocryptfs` folder holds ciphertext. The listed folder is a live view of it, decrypted as you read and encrypted as you write.
- **Master key.** One random 32-byte key does all the encrypting. gocryptfs makes it once, and it never changes. You never type it.
- **Passphrase.** What you type. It only *locks* the master key, so changing it is instant: nothing is re-encrypted.
- **Salt and scrypt.** gocryptfs turns the passphrase into the lock key with scrypt, which is deliberately slow, so each guess costs an attacker time. The salt stops an attacker from precomputing lock keys. Both are automatic.
- **`gocryptfs.conf`.** In each `.gocryptfs` folder: the master key locked under the passphrase, plus the salt, scrypt settings and cipher. It is not secret alone, but without it nothing opens. The backups keep a copy.
- **Master key printout.** `setup-encrypted-folder.sh` prints the master key once. Keep it in a password manager: with it and the ciphertext, anyone can read the files.

```
passphrase + salt ──scrypt──▶ lock key
gocryptfs.conf: locked master key ──lock key──▶ master key (kept in RAM only)
.photos.gocryptfs (ciphertext) ◀──master key──▶ /mnt/data/photos (plaintext view)
```

Unlocking runs that once and mounts the folder. A wrong passphrase fails at the lock-key step. Locking (`umount`, or a reboot) drops the master key from RAM.

</details>
