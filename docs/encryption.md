# Encryption at rest

Optional. List folders in `encrypted_folders` and [gocryptfs](https://nuetzlich.net/gocryptfs/) stores their files encrypted. You unlock them by hand after each boot. A full walk-through on a new host: [quick-start.md](./quick-start.md).

| I want to | Go to |
|---|---|
| Unlock after a reboot, or lock again | [Unlocking](#unlocking) |
| Unlock or lock from a browser | [Unlock page](#unlock-page) |
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
- A wrong passphrase stops it. It reports a folder it cannot unlock (never set up, or not empty: move the files away first). The other folders still unlock.
- From your computer: `just unlock <host>`, `just lock <host>` and `just encryption-status <host>` for the status below.
- `sudo .../unlock.sh --status` shows each folder as unlocked, locked, or without encrypted files (never set up, or its drive is not mounted). It also lists the containers that wait for a locked folder. It changes nothing.
- The passphrase can come from standard input: `printf %s "$PASSPHRASE" | sudo .../unlock.sh`.
- Until you unlock, services that use an encrypted folder see it empty or do not start ([containers](#containers-and-locked-folders)), and **no backup runs**. What still works depends on where its data is: see [Keep these out of a listed folder](#which-folders-to-list).
- To lock again: `just lock <host>`, or `sudo /opt/services/scripts/unlock.sh --lock` on the host. It stops the containers that use a folder, unmounts every folder, and reports a folder that is busy (`fuser -vm <folder>` shows what holds it). The next unlock starts the containers it stopped, which an unlock leaves alone otherwise.

<details>
<summary>Unlock or create a folder by hand, without the scripts</summary>

`setup-encrypted-folder.sh` and `unlock.sh` run these commands and add checks: they pick the cipher for you and move existing files in.

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
| Stopped by a lock | Stays stopped | Started |

`00-containers.sh` (in `after-unlock.d`) does the restarting, whatever a container's restart policy, and prints each name. `unlock.sh --status` lists the waiting containers without changing anything.

**Docker's own storage** (`docker_data_root`: images, layers, logs, named volumes) cannot be in a listed folder, because overlay2 does not run on FUSE. The deploy fails if you try. It holds public images and whatever a container writes outside a bind mount. The repo keeps service data in bind mounts (its one named volume is Immich's public model cache). So listing the data folders covers it. For a service of your own, use a bind mount for private data.

## If gocryptfs.conf is lost

Per folder, easiest first:

1. **From a backup:** `restic restore latest --target <scratch> --include <the .gocryptfs folder>/gocryptfs.conf` ([backups.md](./backups.md)), put it back in the `.gocryptfs` folder, unlock as usual. It needs the passphrase, not the master key.
2. **From the master key:** in an empty folder run `sudo gocryptfs -init -masterkey <key> <empty folder>`. Use the settings the folder was created with. `setup-encrypted-folder.sh` printed them (`gocryptfs -info`) next to the master key. If they show `XChaCha20Poly1305`, add `-xchacha`. If not, add no option, because AES-GCM is the gocryptfs default. Do not guess from today's CPU. The script chose the cipher from the CPU that created the folder. Copy the `gocryptfs.conf` that the command writes into the `.gocryptfs` folder. With the wrong option the mount works, but every read fails with an input/output error.
3. **Whole `.gocryptfs` folder gone:** the encrypted files are gone, so there is nothing left to unlock. The backups hold your files in plain form (restic encrypts them with `vault_restic_password`), so restore from there:
   1. [Set up a new encrypted folder](#set-up-a-folder) at the same path. It gets a new master key. Save it.
   2. Restore the latest snapshot to a scratch folder: `restic restore latest --target <scratch>`.
   3. Copy the files in: `sudo rsync -aHAX <scratch>/<path of the folder>/ <the folder>/` ([flags](./glossary.md#commands)).

   This works only if the backup includes the folder. On a host with a local backup the deploy checks that every listed folder is in it, so it always does. On a host with only a cloud backup nothing checks: look in `restic_cloud_rules` and `restic_cloud_extra_rules` ([backups.md](./backups.md#what-is-backed-up-where)).

<details>
<summary>Not sure which cipher option was used</summary>

Try each on a scratch mount:

```bash
gocryptfs -ro -xchacha -masterkey=stdin <the .gocryptfs folder> <empty folder>   # then paste the master key and press Enter
```

- `-ro` opens it read-only, so a wrong guess cannot change anything. `-masterkey=stdin` takes the key from the keyboard, so it is not saved in your shell history.
- Drop `-xchacha` to try the other option. The wrong option still lists the file names, but reading a file fails (`sha256sum <a file>` prints an input/output error). The right one reads it.
- Unmount with `fusermount -u <empty folder>`.

</details>

## What it protects

| Protects | Does not protect |
|---|---|
| A drive lost, stolen, sold or repaired. A thief with the whole host while it is off | A host that is running and unlocked |
| File contents and names | The number, depth, size (to 4 KiB) and modification time of files |
| | The root drive: it holds the restic password and the Tailscale and Cloudflare logins, so a thief with the whole host can open the backups |
| | The passphrase, on a host that runs the [unlock page](#unlock-page): it is on the root drive too, so a thief with the whole host can unlock |
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
4. **Save the master key and the settings** the script printed in your password manager. A copy of each `gocryptfs.conf` off the host is cheap insurance.
5. Start the containers. Do steps 3 to 5 in one sitting.

On a new host, do `just deploy storage,common --limit <host>` first, deploy everything after the last folder. Use one passphrase for all folders: `unlock.sh` asks once and tries it on each.

If the script reports a checksum mismatch, it deletes nothing. The files are then split between `photos` and `photos.plain`. Look in both. Then run the script again. A power cut can lose the one file being moved.

A service that runs as another user needs the folder's owner changed **while unlocked**. A change while locked is lost.

Removing files does not wipe them from a drive: re-format a drive that held plain data before it leaves your hands.

### Which folders to list

List the folders that hold data, not a drive's mount point. `/mnt/data` would put the ciphertext on the root drive, and a formatted drive is not empty because of `lost+found`. With the default paths and one drive at `/mnt/data` holding `fast` and `primary` ([layout: storage.md](./storage.md#what-lives-where)):

```yaml
encrypted_folders:
  - /mnt/data/appdata  # `fast_appdata_dir` and `primary_appdata_dir`: every service's data, the compose files stay on the root drive
  - /mnt/data/stacks   # Dockge stacks
  - /mnt/data/files    # Copyparty's files
  - /mnt/data/collab   # Copyparty's /collab, if you use it
  - /mnt/data/scratch  # Copyparty's /scratch, if you use it
```

- A listed folder must not sit inside another. The deploy fails if one does.
- The deploy also fails for a folder that is, or holds, something you need to log in and unlock: `scripts_dir`, your home folder, `/etc`, `/usr`, `/boot`, `/root`, `/var/lib` or `docker_data_root`.
- `appdata` includes every database, Immich's Postgres too. Writes are the slow part of encryption, and databases write often. On one Raspberry Pi 4 with a USB stick, files written through the mount ran at 3 to 5 MB/s and reads at about 65 MB/s. The same stick without encryption wrote at 7 to 39 MB/s and read at 126 MB/s. Try your real workload before you list a folder that takes many writes.
- List `collab` and `scratch` only if you use them. They hold data when `copyparty_collab_enabled` or `copyparty_scratch_enabled` is on.
- The defaults cover a service added later with its data under `fast_appdata_dir` or `primary_appdata_dir`. Anything else stays plain.
- With the fast and primary roles on two drives, list `appdata` on each (two entries).

**Keep these out of a listed folder** if you need them while the host is locked:

| Data | Setting | If it is in a listed folder |
|---|---|---|
| ntfy | `ntfy_data_dir` | No alerts from this host until you unlock. The deploy does not stop you: it cannot know what you need. Use an ntfy on another host (`ntfy_alert_url`), or keep this folder plain. |
| Caddy | `caddy_data_dir` | No web access to any service until you unlock. The deploy refuses it on a host with the [unlock page](#unlock-page). |
| Tinyauth | `tinyauth_data_dir` | No Tinyauth login until you unlock. The deploy refuses it on a host with the unlock page. |

The defaults put all three under `fast_appdata_dir` (`<fast drive>/appdata`), so listing it locks them. To keep one plain, set its `*_data_dir` to a folder you do not list, for example `/mnt/data/plain/ntfy`. Move the folder there before the deploy, while the service is stopped.

### Turning it off

1. Stop the containers that use the folder (`docker stop <name>`; the script lists any still running).
2. Run the script in a terminal (`ssh -t <host>`). It unlocks the folder, moves the files out, compares checksums, and puts them back in the folder as plain files:

   ```bash
   sudo /opt/services/scripts/remove-encrypted-folder.sh /mnt/data/photos
   ```

   After a lost connection, run the same command again. If a checksum differs it deletes nothing. It keeps the encrypted files.
3. Remove the path from `encrypted_folders` and run `just deploy encryption,backup --limit <host>`. Start the containers.
4. When everything works, delete the encrypted files: `sudo rm -r /mnt/data/.photos.gocryptfs`.

The role removes the scripts when no folder remains, and gocryptfs stays installed. `teardown.yml` (or `--tags encryption`) removes the scripts and the empty after-unlock folder, and never touches encrypted folders or your scripts. `-e remove_data=true` stops before it removes anything when the service's data folder is, or holds, a listed folder. Turn encryption off for that folder first.

## Unlock page

A web page on the host that shows, unlocks and locks its encrypted folders from a browser. The `unlock_page` role deploys it (`unlock_page_enabled: true` in the host's `vars.yml`). It sits behind the Tinyauth login at `https://<unlock_page_subdomain>.<domain>`. `just unlock` and `just lock` over SSH work without it.

Set it up once:

1. Put the gocryptfs passphrase in the vault as `vault_encryption_passphrase`. It is the one you type into `setup-encrypted-folder.sh`.
2. List the folders to encrypt ([which folders](#which-folders-to-list)). Keep `caddy_data_dir` and `tinyauth_data_dir` outside every listed folder: the deploy refuses a listed folder that holds either, or the page's own folder.
3. Run `just deploy encryption,unlock_page --limit <host>`. Each host runs its own page.
4. Check it: `docker exec unlock-page python3 app.py check` prints the host's status and exits 1 if the page cannot reach the host.

**Outside the tailnet:** the page, like every Tinyauth site, opens only where the private names resolve, which is on the tailnet. To reach it through Cloudflare, publish the page and the login under the private domain: [Reach a protected service from outside the tailnet](./auth-reference.md#reach-a-protected-service-from-outside-the-tailnet), with `unlock` in place of `dockge`. Cloudflared, Caddy and Tinyauth live on the root drive, so they run while the folders are locked. Keep the Tinyauth login in front of it and give every user a `totp` secret: the page can unlock and stop your services.

**Unlock** unlocks the folders and starts the containers that wait for them. **Lock** asks first, then stops those containers and unmounts the folders, as `unlock.sh --lock` does. The page shows the status of each folder.

<details>
<summary>How it works, and what a thief can do</summary>

The page is a container with no key and no passphrase. It connects to a socket (`/run/unlock-page/unlock.sock`, mode 0600, so only root can use it) and sends one word: `unlock`, `lock` or `status`. systemd starts `unlock-page-request.sh` as root for each connection. The script compares the word with those three strings and runs one fixed command for each. The passphrase is in `<scripts_dir>/unlock-passphrase` (root only), and `unlock` reads it from there.

- Nothing from the connection is run, expanded or put in a command line. The script reads at most 16 characters of one line, and anything but the three words gets "unknown request". `tests/test_unlock_page.py` sends the script shell syntax, long input and extra lines.
- `unlock.sh` also accepts only no argument, `--status` and `--lock`.
- The page's container mounts the socket's folder read-only.
- The page refuses a POST whose `Origin` is another site, so a page on another site cannot press Lock for you.

Someone who gets past Tinyauth can unlock and lock the folders. The worst of that is stopped services. Nobody can log in, read files or see the passphrase through the page. Anyone who holds the whole host, switched off, can read the passphrase file: see [What it protects](#what-it-protects).

Turn the page off with `teardown.yml --tags unlock_page` (the socket, the script and the passphrase file) and `-e only=unlock_page` (the container).

</details>

## Dumps and backups

- **Dumps:** `backup-services.sh` writes the Immich, Gitea and Garage dumps to `service_dumps_dir`. That is `<backup drive>/service-dumps`, or the root drive on a host with no local backup. Nothing encrypts it unless you list it. Until then, anyone who holds that drive can read Immich's database, Gitea's dump and Garage's node key. To list it, add it to `encrypted_folders` and `restic_local_extra_rules` ([backups.md](./backups.md#what-is-backed-up-where) checks that every listed folder appears in a rule).
- **Backups:** both scripts refuse to run while any listed folder stays locked. restic reads the folder through the mount (decrypted) and encrypts it with `vault_restic_password`. Every backup leaves out the ciphertext (it would be stored twice), but keeps each folder's `gocryptfs.conf`, so it restores with the data.
- **Check after the first backup:** `restic ls latest | grep gocryptfs.conf` prints one line per listed folder ([backups.md](./backups.md)).

## How it works

Each listed folder is a live decrypted view. The ciphertext sits beside it in a hidden `.<name>.gocryptfs` folder on the same drive.

<details>
<summary>Folders, scripts and cipher (what to know before changing anything)</summary>

Each entry in `encrypted_folders` is the path of one folder. The ciphertext sits beside it in a hidden folder (`encrypted_pairs` in `group_vars/all/derived.yml`). `/mnt/data/photos` is the decrypted view that `unlock.sh` mounts (services and backups use this path, so no data setting changes). `/mnt/data/.photos.gocryptfs` holds the encrypted files on the same filesystem.

- **Locked folder:** empty and marked immutable (`chattr +i`). A container or deploy that runs too early fails with "Operation not permitted" instead of filling the drive. It needs ext4, xfs or btrfs (elsewhere `unlock.sh` warns and mounts anyway). Root can remove the flag: a safety net, not a security boundary.
- **After-unlock scripts:** `unlock.sh` runs every `<name>.sh` in `after-unlock.d` (`encryption_hooks_dir`) as root, in name order. It gives each script the folders it just mounted as arguments. `00-containers.sh` ([above](#containers-and-locked-folders)) comes first. Add your own to start other software. A failing script does not stop the others. The unlock then exits with an error.
- **Cipher:** AES-GCM when the CPU has AES instructions, XChaCha20 when not (a Raspberry Pi 4). Both are 256-bit. gocryptfs sets it at creation and records it in the conf, so a folder opens on any CPU and a later change of the gocryptfs default does not affect it. AES-GCM has no option of its own: it is what gocryptfs uses when you choose nothing. The setup script checks that the new folder has the cipher named here, and stops if it does not. Another machine needs gocryptfs 2.2+ for XChaCha20 (on a Mac: gocryptfs and macFUSE). `gocryptfs -info <the .gocryptfs folder>` shows the cipher.

</details>

<details>
<summary>How the keys work (plaintext, master key, passphrase, <code>gocryptfs.conf</code>)</summary>

- **Plaintext / ciphertext.** Plaintext is your real file. Ciphertext is the scrambled version on disk. The `.gocryptfs` folder holds ciphertext. The listed folder is a live view of it, decrypted as you read and encrypted as you write.
- **Master key.** One random 32-byte key does all the encrypting. gocryptfs makes it once, and it never changes. You never type it.
- **Passphrase.** What you type. It only *locks* the master key, so changing it is instant: nothing is re-encrypted.
- **Salt and scrypt.** gocryptfs turns the passphrase into the lock key with scrypt. scrypt is slow on purpose, so each guess costs an attacker time. The salt stops an attacker from precomputing lock keys. Both are automatic.
- **`gocryptfs.conf`.** In each `.gocryptfs` folder: the master key locked under the passphrase, plus the salt, scrypt settings and cipher. It is not secret alone, but without it nothing opens. The backups keep a copy.
- **Master key printout.** `setup-encrypted-folder.sh` prints the master key once. Keep it in a password manager: with it and the ciphertext, anyone can read the files.

```
passphrase + salt ──scrypt──▶ lock key
gocryptfs.conf: locked master key ──lock key──▶ master key (kept in RAM only)
.photos.gocryptfs (ciphertext) ◀──master key──▶ /mnt/data/photos (plaintext view)
```

Unlocking runs that once and mounts the folder. A wrong passphrase fails at the lock-key step. Locking (`umount`, or a reboot) drops the master key from RAM.

</details>
