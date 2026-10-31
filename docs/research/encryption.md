# Encryption at rest (research notes)

> **Status: research notes. Nothing here is implemented, and this file is not kept in step with the code.** Treat it as a record of decisions and open questions, not as documentation of how the repo works.

## Threat model

Protects against: a drive that is lost, stolen, sold, discarded or sent back for repair, and a thief who has the whole host while it is powered off. File content is unreadable without the passphrase.

Does not protect against: someone with the host while it is running and unlocked, file names, sizes and modification times (gocryptfs shows the folder structure), or a passphrase typed on a device that records it (see [Unlocking](#unlocking)).

Quantum computers: the drives and the restic repositories use 256-bit symmetric encryption (gocryptfs, restic), which a quantum computer weakens but does not break. The weak point is the passphrase, so use a long random one. Public-key links (SSH, Tailscale) are the part that is exposed to record-now-decrypt-later; recent OpenSSH uses a hybrid post-quantum key exchange by default (verify the version on each host).

## Decisions

- **gocryptfs, not LUKS.** It encrypts files on an ordinary ext4 drive, so there is no LUKS container to recover, and a Mac can open the drive (`brew install gocryptfs macfuse`). LUKS needs a Linux machine to recover and hides file names, which is not worth that here. The new drives from the [drive migration](../../plans/drive-migration.md) are formatted as ext4 either way; the encrypted folder is created on them.
- **Create it with `gocryptfs -init -xchacha`, default file names, and never mount with `-nonempty`.** The Pi 4's CPU has no AES instructions (check: `grep -o -w aes /proc/cpuinfo` prints nothing), and a 2021 benchmark on a Pi 4 measured about 21 MB/s for the default AES-GCM against about 118 MB/s for XChaCha20 (re-run `gocryptfs -speed` on the host). XChaCha needs gocryptfs 2.2 or later on every machine that opens the drive, the Mac included. Without `-nonempty`, a mount over a folder that something wrote into fails loudly instead of hiding those files.
- **The master key and `gocryptfs.conf` are kept off the host.** `-init` prints the master key once: store it in the password manager and on paper. Copy `gocryptfs.conf` off the host too. Either one recreates a lost config (gocryptfs wiki: "Recreate gocryptfs.conf using masterkey"). A lost `gocryptfs.diriv` has no documented recovery, so the raw ciphertext folder is part of what you keep safe.
- **Services and backups check that the plaintext is really mounted.** `mountpoint -q` plus a `.mounted` file inside the plaintext folder, in `unlock.sh` before Docker starts and in the backup scripts before restic runs. Otherwise restic saves a snapshot of an empty folder.
- **restic backs up the plaintext through the mount.** The repository is encrypted by restic anyway, and a restore needs no gocryptfs.
- **The restic repository on the `backup` drive stays unencrypted by gocryptfs.** restic already encrypts it with its own password, and a second layer ties two recovery paths to one key. `service-dumps/` and the logs on that drive sit in a gocryptfs folder next to it.
- **No automatic unlock.** No keyfile on the root drive, no Tang, no stored passphrase. A host that unlocks itself hands the thief what they need.
- **Mount layout.** The ciphertext folder sits on the ext4 drive, and the plaintext is mounted over the path services use (for example `/mnt/t7/docker`). Docker's own storage (`docker_data_root`) stays on plain ext4: overlay2 does not run on a FUSE filesystem (verify on the host).
- **One rule for Docker: it does not start at boot.** The unlock script mounts the plaintext folders, then starts Docker. Every container waits for the unlock, including ones with no encrypted volumes. The alternative is deciding stack by stack which ones need the plaintext, and each exception is a way for Postgres to run `initdb` on an empty folder.
- **Whatever is needed to unlock must not need unlocking.** That is `sshd` and Tailscale, both on the host, not in Docker.

## Unlocking

SSH to the host, run `unlock.sh`, type the passphrase. This works from any device, including one you do not own.

A device you do not own may record what you type. After using one, change the passphrase with `gocryptfs -passwd`, which does not re-encrypt the data. This only helps if nobody has already copied `gocryptfs.conf` from the drive: someone with that file and the old passphrase can still open the data. Full protection means creating a new gocryptfs folder and copying the files in.

## Limits

- The root drive is not encrypted: a headless host cannot take a passphrase at boot. It holds the restic password file and the Tailscale and Cloudflare credentials, so a thief with the whole host can open the cloud backup but not the local drives.
- A host with no `backup` drive keeps service dumps in `/var/lib/backup-work` on the root drive, unencrypted. Streaming each dump straight into restic (`restic backup --stdin`) would leave no plaintext dump on disk; see the open question below.
- After a reboot nothing runs until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then; the cron lines already log the failure with `logger -t backup` (through `alert.sh`).

## Open questions

- The backup scripts check `mountpoint -q <data drive>/.` ([storage.md](../storage.md#how-a-drive-is-mounted)). With gocryptfs the ext4 drive is mounted even while the plaintext is locked, so the check passes and restic would save an empty folder. The check must look at the plaintext mounts.
- Nothing tells you the host is locked after a reboot; ntfy runs in Docker, so it is down too. A small systemd unit at boot could send a "locked" message to an external service.
- Whether the automount options in [storage.md](../storage.md#how-a-drive-is-mounted) work when the folder behind the mount is a gocryptfs mount.
- How to reach the host from a device that is not on your tailnet. Tailscale can be logged in on a borrowed device for the session, or SSH can be exposed another way; pick one when this is built.
- Postgres and SQLite on a FUSE mount. No report either way was found. Immich's database could stay on plain ext4 and reach the backup through its dump, at the cost of an unencrypted database; or it moves onto the mount after the recovery drill below passes.

- Service dumps. They exist only so restic can read them. Streaming each into restic removes the plaintext file, the keep-3 rotation and `service_dumps_dir`. The cost: a dump that fails halfway can still be saved as the newest snapshot (today the `.tmp` and rename stop that), a restore needs the restic repository instead of a plain file on the backup drive, and the restore steps in [backups.md](../backups.md) have not been run yet. Decide after the restore drill in [TODO.md](../../TODO.md).

## Recovery drill

Run on a scratch folder before real data goes in:

1. Init, mount, write files, unmount, run `gocryptfs -fsck`.
2. Delete `gocryptfs.conf`, recreate it from the master key, remount and read the files.
3. Change the passphrase with `-passwd` and check the old one fails.
4. Mount the same folder on the Mac and read the files.
5. Delete one `gocryptfs.diriv` and see what is lost.
6. Leave the folder unmounted and check that Docker, the backup scripts and the unlock script all refuse to continue.
7. Restore a restic snapshot to a clean folder and compare checksums.
8. If a database goes on the mount: `kill -9` Postgres a few times under load and check it recovers.

## Order of work

1. Run `gocryptfs -speed` on the NAS host.
2. Run the recovery drill above, then put one new drive's data folder under gocryptfs during the drive migration, mount it by hand, and settle the automount question.
3. Write `unlock.sh` and stop Docker starting at boot.
4. Describe the unlock step in [backups.md](../backups.md) and [storage.md](../storage.md).
