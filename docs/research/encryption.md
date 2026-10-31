# Encryption at rest (research notes)

> **Status: research notes. Nothing here is implemented, and this file is not kept in step with the code.** Treat it as a record of decisions and open questions, not as documentation of how the repo works.

## Threat model

Protects against: a drive that is lost, stolen, sold, discarded or sent back for repair while powered off. Without the passphrase the drive is unreadable, file names and sizes included.

Does not protect against: someone who has the host while it is running and unlocked, someone who has the whole host and the owner's passphrase, or the root drive being read (see [Limits](#limits)).

Anything beyond this (unlocking from a stranger's device while travelling, attackers guessing passphrases online) is out of scope. Each such feature needs a separate service to run and maintain.

## Decision

LUKS on each data drive, unlocked by hand over SSH after a reboot.

- **LUKS, not gocryptfs.** It is the standard Linux tool (`cryptsetup`), and it hides file names and sizes. The cost is that a drive is formatted as LUKS and then ext4 inside it, so existing data is copied in once. [plans/drive-migration.md](../../plans/drive-migration.md) already formats every new drive, so the new drives are formatted as LUKS at that step and nothing is copied twice.
- **One passphrase for all drives**, kept in the owner's password manager and in a printed copy somewhere safe. A lost passphrase means lost data; there is no recovery.
- **The `backup` drive is encrypted like the others.** The restic repository keeps its own restic password as well. That covers `service-dumps/` and the logs without a separate mechanism.
- **No automatic unlock** (no keyfile on the root drive, no Tang, no stored secret). A host that unlocks itself gives the thief what they need.
- **Unlock is one script on the host**, run over SSH or Tailscale after a reboot: it asks for the passphrase once, runs `cryptsetup open` for each drive, and then starts the services.

## Limits

- The root drive is not encrypted. It holds the restic password file, the Tailscale and Cloudflare credentials, and Docker's images. If the whole host is stolen, the thief can open the cloud backup repository but not the local drives. Encrypting the root drive means typing a passphrase at boot, which a headless host cannot do; accept this or keep these secrets off the host.
- A host with no `backup` drive keeps service dumps in `/var/lib/backup-work` on the root drive, unencrypted.
- After a reboot, nothing runs until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then; the cron lines already log the failure with `logger -t backup` (through `alert.sh`).

## Open questions

- Starting the services only after the unlock. Docker data lives under `{{ fast_drive }}/docker` (`immich_db_data_location`, `gitea_data_dir`, `copyparty_config_dir`, `garage_data_dir`), so a container that starts early sees an empty directory, and Postgres runs `initdb` on it. The plain fix is to leave Docker disabled at boot and have the unlock script start it.
- How the automount options in [storage.md](../storage.md#how-a-drive-is-mounted) combine with a `/dev/mapper/<name>` device in fstab. Test on a host.
- Speed. The Pi 4 may lack ARM crypto extensions, so AES may not keep up with the direct link's 117 MB/s ([networking.md](../networking.md#direct-ethernet-link)). Run `cryptsetup benchmark` on the host before committing; `xchacha20,aes-adiantum-plain64` is the fallback for CPUs without AES instructions.

## Order of work

1. Run `cryptsetup benchmark` on the NAS host.
2. Format one new drive as LUKS during the drive migration and mount it by hand, to settle the automount question.
3. Add the unlock script and the Docker start order.
4. Describe the unlock step in [backups.md](../backups.md) and [storage.md](../storage.md).
