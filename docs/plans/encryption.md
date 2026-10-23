# Encryption-at-rest plan (not started)

Transparent encryption for the `fast` and `primary` drives (`/mnt/t7` today) and the plaintext parts of the `backup` drive. Nothing is implemented. The decisions below are settled; the open questions and the order of work are at the end.

## Goal

Protect file content and personal data if a drive is lost, stolen or discarded. Metadata (file names, directory structure, sizes, mtimes) is out of scope.

Requirement: unlockable from any device, including one you do not own, without needing your phone.

## Decisions made

- **gocryptfs**, not LUKS. Encrypts files on the existing ext4, so the drives are not reformatted and no full-disk unlock at boot is needed. Recoverable from a Mac via `brew install gocryptfs macfuse`, no VM needed.
- **Don't encrypt `restic-repo` on the backup drive.** restic already encrypts it with its own password; a second layer would tie two recovery paths to one key.
- **Do encrypt `service-dumps/` on the backup drive.** `backup-services.sh` writes plaintext database dumps there before restic reads them.
- **No automatic unlock (no Tang, no keyfile on the SD card, no polling with a stored secret).** A host that unlocks itself holds what it needs to unlock at rest, and theft hands that to the attacker.
- **Two-tier unlock, by context:**
  - **Day-to-day (own devices):** passkey (WebAuthn/FIDO2) — phishing resistant, private key never leaves the device, synced across own devices via platform keychain.
  - **Break-glass (no trusted device, e.g. travel):** a single human-memorable one-time word (e.g. "chicken"), rotated by hand from a trusted device after each use. A keylogger learns nothing reusable because the word is one-time; throttling (below) handles guessing.
- **No hard lockout on failed attempts.** A hard lockout lets anyone lock you out by failing on purpose. Use exponential backoff per source (IP or fingerprint) plus alerting.
- **Releaser service is separate from the NAS.** A small serverless app holds the hashed one-time word and the gocryptfs passphrase, and releases the passphrase to the host only after a valid word or passkey assertion. The host keeps the passphrase in memory only, while mounted.
  - Pick: **Vercel function + Upstash Redis** for state (burned/used words, backoff counters). Cloudflare Workers' free tier allows 10 ms CPU per request, too little for a bcrypt or argon2 hash.
  - Ruled out: static client-side decryption (staticrypt style). The ciphertext is copyable, so an attacker can guess offline without limit; backoff and burn-after-use need a server to mediate each attempt.
  - Store the word hashed (bcrypt or argon2).
  - The hosting account is the root of trust for the whole scheme; it needs passkey or hardware-key 2FA.
- Delivery to the Pi: push via a webhook through the existing Cloudflare Tunnel once a code/passkey validates, rather than the host polling on a timer.

## Open questions

- Exact backoff curve and alert channel (email? push? which service?).
- Whether passkey verification also runs through the same releaser service, or is handled separately (e.g. an authenticated page gated by browser-native WebAuthn, no server-side passkey verification needed if it's just gating a button that hits the releaser).
- Boot-ordering fix: `immich_db_data_location`, `gitea_data_dir`, `copyparty_config_dir`, `garage_data_dir` (vars.yml) all live under `{{ fast_drive }}/docker`, which would sit under the gocryptfs mount. Compose auto-start must wait for the unlock, or Postgres runs `initdb` on an empty directory.
- Benchmark `gocryptfs -init -xchacha` against the default AES mode on the NAS host before committing. The Pi 4 SoC likely lacks ARM crypto extensions, so AES there may not keep up with the direct link's 117 MB/s (docs/services.md#direct-ethernet-link).
- Known tradeoff: after a reboot nobody unlocks, the 2 AM and Sunday 4 AM backups fail until unlocked; the cron lines already log the failure with `logger -t nas-backup`.

## Order of work

1. Benchmark gocryptfs AES against XChaCha20 over the direct link.
2. Stand up the releaser (Vercel/Upstash or Workers/KV) with the one-time word flow + backoff, no passkey yet — get the core unlock loop working end to end against a test directory.
3. Move the `fast` and `primary` drives and `service-dumps` to gocryptfs; change the `storage` and `backup` roles to mount after unlock instead of at boot.
4. Fix Docker Compose boot ordering so services start only after mount.
5. Add passkey path for day-to-day unlock from own devices.
6. Update `docs/backups.md` and `docs/storage.md` to document the new unlock flow and the reboot-then-no-backup-until-unlocked tradeoff.
