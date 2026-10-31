# Encryption at rest (research notes)

> **Status: research notes. Nothing here is implemented, and this file is not kept in step with the code.** Treat it as a record of decisions and open questions, not as documentation of how the repo works.

## Threat model

Protects against: a drive that is lost, stolen, sold, discarded or sent back for repair, and a thief who has the whole host while it is powered off. File content is unreadable without the passphrase.

Does not protect against: someone with the host while it is running and unlocked, file names, sizes and modification times (gocryptfs shows the folder structure), or a passphrase typed on a device that records it (see [Unlocking](#unlocking)).

## Decisions

- **gocryptfs, not LUKS.** It encrypts files on an ordinary ext4 drive, so there is no LUKS container to recover, and a Mac can open the drive (`brew install gocryptfs macfuse`). LUKS needs a Linux machine to recover and hides file names, which is not worth that here. The new drives from the [drive migration](../../plans/drive-migration.md) are formatted as ext4 either way; the encrypted folder is created on them.
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
- A host with no `backup` drive keeps service dumps in `/var/lib/backup-work` on the root drive, unencrypted.
- After a reboot nothing runs until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then; the cron lines already log the failure with `logger -t backup` (through `alert.sh`).

## Open questions

- The backup scripts check `mountpoint -q <data drive>/.` ([storage.md](../storage.md#how-a-drive-is-mounted)). With gocryptfs the ext4 drive is mounted even while the plaintext is locked, so the check passes and restic would save an empty folder. The check must look at the plaintext mounts.
- Nothing tells you the host is locked after a reboot; ntfy runs in Docker, so it is down too. A small systemd unit at boot could send a "locked" message to an external service.
- Whether the automount options in [storage.md](../storage.md#how-a-drive-is-mounted) work when the folder behind the mount is a gocryptfs mount.
- How to reach the host from a device that is not on your tailnet. Tailscale can be logged in on a borrowed device for the session, or SSH can be exposed another way; pick one when this is built.
- Speed. The Pi 4 may lack ARM crypto extensions, so AES may not keep up with the direct link's 117 MB/s ([networking.md](../networking.md#direct-ethernet-link)). Compare `gocryptfs -init -xchacha` with the default on the host first.

## Order of work

1. Benchmark gocryptfs AES against XChaCha20 on the NAS host.
2. Put one new drive's data folder under gocryptfs during the drive migration, mount it by hand, and settle the automount question.
3. Write `unlock.sh` and stop Docker starting at boot.
4. Describe the unlock step in [backups.md](../backups.md) and [storage.md](../storage.md).
