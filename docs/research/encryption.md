# Encryption at rest (research notes)

> **Status: research notes. Nothing here is implemented, and this file is not kept in step with the code.** Treat it as a record of decisions and open questions, not as documentation of how the repo works.

## Threat model

Protects against:

- A drive that is lost, stolen, sold, discarded or sent back for repair. File content is unreadable without the passphrase.
- A thief who has the whole host while it is powered off.
- An attacker who finds the remote unlock page. It sits behind Cloudflare Access (a login), so a stranger cannot even try passphrases.
- A keylogger on a device you do not own, for the one-time break-glass passphrase only (see [Unlocking](#unlocking)).

Does not protect against: someone with the host while it is running and unlocked, file names, sizes and modification times (gocryptfs shows the folder structure), or a compromised Cloudflare account.

## Decisions

- **gocryptfs, not LUKS.** It encrypts files on an ordinary ext4 drive, so there is no LUKS container to recover, and a Mac can open the drive (`brew install gocryptfs macfuse`). LUKS needs a Linux machine to recover and hides file names, which is not worth that here. The new drives from the [drive migration](../../plans/drive-migration.md) are formatted as ext4 either way; the encrypted folder is created on them.
- **The restic repository on the `backup` drive stays unencrypted by gocryptfs.** restic already encrypts it with its own password, and a second layer ties two recovery paths to one key. `service-dumps/` and the logs on that drive sit in a gocryptfs folder next to it.
- **No automatic unlock.** No keyfile on the root drive, no Tang, no stored passphrase. A host that unlocks itself hands the thief what they need.
- **One rule for Docker: it does not start at boot.** The unlock script mounts the drives, then starts Docker. Every container waits for the unlock, including ones with no encrypted volumes, and `docker_data_root` may point at an encrypted drive. The alternative is deciding stack by stack which ones need the drives, and each exception is a way for Postgres to run `initdb` on an empty folder.
- **Whatever is needed to unlock must not need unlocking.** That is `sshd` and Tailscale (both on the host, not in Docker), and for the remote path below, a tunnel that does not run in Docker.

## Unlocking

- **Own device:** SSH over Tailscale, run `unlock.sh`, type the passphrase. It lives in a password manager, so a passkey or biometric unlocks the manager and nothing else is needed.
- **Device you do not own:** a Cloudflare Tunnel with Cloudflare Access in front (login by a one-time emailed PIN or a hardware key), pointing at an SSH terminal in the browser or at a one-field unlock page. Cloudflare provides the login, the throttling and the lockout, so none of that is built here, and the passphrase is typed by you, never stored on a server. Check the current Cloudflare docs for browser-rendered SSH before choosing between the two.
- **One-time passphrase for untrusted devices:** gocryptfs reads its key from a config file, and `-config` can point at a second file with a different passphrase for the same data. Keep a break-glass passphrase in a second file, use it on the stranger's device, then delete that file from a trusted device. A keylogger learns a passphrase that no longer works.

## Limits

- The root drive is not encrypted: a headless host cannot take a passphrase at boot. It holds the restic password file and the Tailscale and Cloudflare credentials, so a thief with the whole host can open the cloud backup but not the local drives.
- A host with no `backup` drive keeps service dumps in `/var/lib/backup-work` on the root drive, unencrypted.
- After a reboot nothing runs until someone unlocks. The 02:00 and Sunday 04:00 backups fail until then; the cron lines already log the failure with `logger -t backup` (through `alert.sh`).

## Open questions

- The `cloudflared` role runs the tunnel in Docker, so it is down until the unlock. Moving it to a host service solves the remote-unlock case; a second host-level tunnel for unlock only is the alternative.
- Whether the automount options in [storage.md](../storage.md#how-a-drive-is-mounted) work when the folder behind the mount is a gocryptfs mount.
- Speed. The Pi 4 may lack ARM crypto extensions, so AES may not keep up with the direct link's 117 MB/s ([networking.md](../networking.md#direct-ethernet-link)). Compare `gocryptfs -init -xchacha` with the default on the host first.

## Order of work

1. Benchmark gocryptfs AES against XChaCha20 on the NAS host.
2. Put one new drive's data folder under gocryptfs during the drive migration, mount it by hand, and settle the automount question.
3. Write `unlock.sh` and stop Docker starting at boot.
4. Add the Cloudflare Access path.
5. Describe the unlock step in [backups.md](../backups.md) and [storage.md](../storage.md).
