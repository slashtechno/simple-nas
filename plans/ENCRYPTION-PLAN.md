# Encryption-at-rest plan (not started)

Design notes for adding transparent encryption to `/mnt/t7` (and the plaintext
parts of `/mnt/backup`), captured for picking back up later. Not implemented
yet — no code, no roles, nothing deployed. This is a decision record, not a
task tracker.

## Goal

Protect file content + PII if a drive is lost, stolen, discarded, or
otherwise ends up in someone else's hands. Metadata (filenames' existence,
directory structure, file sizes, mtimes) is explicitly out of scope — only
content confidentiality matters.

Hard requirement: must be unlockable from **any device, anywhere**, including
a machine you don't own or trust (e.g. a public/internet-cafe computer),
without assuming you have your phone on you.

## Decisions made

- **gocryptfs**, not LUKS. Overlay encryption on existing ext4 — no
  reformatting the drives, no boot-time full-disk unlock story to solve.
  Recoverable from a Mac via `brew install gocryptfs macfuse`, no VM needed.
- **Don't encrypt `/mnt/backup/restic-repo`.** It's already self-encrypting
  (restic's own client-side crypto, separate password). Wrapping it in a
  second layer just couples two independent recovery paths into one key for
  no security gain.
- **Do encrypt `/mnt/backup/service-dumps/`.** `backup-services.sh` writes
  plaintext `immich-db-*.sql.gz` / `gitea-dump-*.zip` there before restic ever
  touches them — this is the actual unprotected-PII gap on the backup drive,
  not the repo itself.
- **No fully-automated unlock (no Tang, no keyfile-on-SD, no
  cron-job.org-style polling with a baked-in secret).** Anything that unlocks
  itself without a human present requires the NAS to hold, at rest, whatever
  it needs to complete the unlock — and physical theft hands that to the
  attacker for free. This is a structural limit, not an implementation
  detail; no amount of clever tokens or expiry fixes it if the NAS can act
  alone.
- **Two-tier unlock, by context:**
  - **Day-to-day (own devices):** passkey (WebAuthn/FIDO2) — phishing
    resistant, private key never leaves the device, synced across own
    devices via platform keychain.
  - **Break-glass (no trusted device, e.g. travel):** a single
    human-memorable one-time word (e.g. "chicken"), rotated by hand from a
    trusted device after each use. Safe against a keylogged session
    specifically because it's one-time, not because it's high-entropy —
    entropy only matters against blind remote guessing, which is handled by
    throttling (see below), not by making the word hard to remember.
- **No hard lockout on failed attempts.** A hard lockout is a self-inflicted
  denial-of-service: someone can lock *you* out just by failing on purpose.
  Use **exponential backoff, keyed per source (IP/fingerprint), plus
  alerting** instead — always eventually lets a legitimate attempt through,
  slows brute force to impractical, and notifies on noise without ever fully
  denying access.
- **Releaser service is separate from the NAS.** A small serverless app holds
  the current one-time word (hashed) and the real gocryptfs passphrase;
  releases the passphrase to the Pi only after verifying a submitted
  word/passkey assertion. The Pi itself never holds anything that unlocks
  anything at rest — passphrase lives in memory only, for the duration of the
  mount.
  - Pick: **Vercel function + Upstash Redis** for state (burned/used words,
    backoff counters). Cloudflare Workers is a worse fit for this
    specifically: free-tier Workers get only 10ms **CPU time** per request,
    and a real bcrypt/argon2 hash needs more than that to be meaningful —
    Workers Paid ($5/mo) raises this to 30s+, but Vercel's Node functions
    don't have this ceiling at all, so no reason to pay just to hash a
    password.
  - Ruled out: **portable-secret / staticrypt style static, client-side-only
    decryption** (encrypt once, embed ciphertext in a static HTML file,
    decrypt fully offline in-browser with WebCrypto, no server round-trip).
    These make the ciphertext freely copyable, so an attacker can brute-force
    the password entirely offline, at unlimited speed, with zero visibility
    to us — incompatible with "memorable word + backoff + burn-after-use,"
    which only works because a server mediates every attempt. Fine tools for
    sharing a secret over an untrusted channel or gating a static site from
    casual viewers; wrong shape for resisting a targeted attacker against a
    low-entropy secret.
  - Store the word hashed (bcrypt/argon2), not plaintext, so reading the
    Vercel/Upstash dashboard doesn't hand over the secret directly.
  - **The Vercel/Netlify/Cloudflare account becomes the actual root of
    trust for the whole scheme** — it must have its own passkey/hardware-key
    2FA, since compromising it bypasses everything else here.
- Delivery to the Pi: push via a webhook through the existing Cloudflare
  Tunnel once a code/passkey validates, rather than the Pi polling on a
  timer.

## Open questions / to decide when picking this up

- Exact backoff curve and alert channel (email? push? which service?).
- Whether passkey verification also runs through the same releaser service,
  or is handled separately (e.g. an authenticated page gated by
  browser-native WebAuthn, no server-side passkey verification needed if
  it's just gating a button that hits the releaser).
- Boot-ordering fix: `immich_db_data_location`, `gitea_data_dir`,
  `copyparty_config_dir`, `garage_data_dir` (vars.yml) all live under
  `{{ main_drive }}/docker`, which will sit under the gocryptfs mount.
  Compose auto-start must be disabled/gated so containers don't start (and
  Postgres doesn't `initdb`) against an empty directory before unlock.
- Benchmark `gocryptfs -init -xchacha` vs default AES mode on the Pi 4 before
  committing — the SoC likely lacks ARM crypto extensions, so AES is
  software-only and may not sustain the measured 117MB/s direct-link speed
  (README.md).
- Accept as a known tradeoff: after any reboot with nobody unlocking, the
  2 AM / 4 AM cron backups will no-op until manually unlocked (existing
  `logger` calls in the backup role are the detection path — no new work
  needed there).

## Rough implementation order (when resumed)

1. Benchmark gocryptfs AES vs XChaCha20 on the Pi 4 over the direct link.
2. Stand up the releaser (Vercel/Upstash or Workers/KV) with the one-time
   word flow + backoff, no passkey yet — get the core unlock loop working
   end to end against a test directory.
3. Migrate `/mnt/t7` and `/mnt/backup/service-dumps` to gocryptfs, update the
   `storage`/`backup` Ansible roles to mount post-unlock instead of at boot.
4. Fix Docker Compose boot ordering so services start only after mount.
5. Add passkey path for day-to-day unlock from own devices.
6. Update `BACKUPS.md` / `README.md` to document the new unlock flow and the
   reboot-then-no-backup-until-unlocked tradeoff.
