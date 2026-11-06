# Next steps: verify, harden, make the code teachable

> **Status: active plan. Delete this file when the phases are done; git history keeps it.** It records decisions, not conventions: the rules are in AGENTS.md and the code.

Goal: a CS or homelab newcomer can run the setup, and can read, change, remove and add behaviour in the code that drives it. Reliability of backups comes first. Each step keeps the AGENTS.md rules (opt-in switch, one place per default, a comment on every setting, `just check` passes, no playbook run against a host by an agent).

## Phase 0: prove what exists

- [x] `just preview --limit pi4` passes (8 changes: Dockge and Caddy compose, backup scripts and exclude list, the check job moves to Saturday 5 AM). It found a real bug the render test missed (the dump-script check failed on entries without `dump_required`); fixed and tested.
- [x] pi4: common, backup, tinyauth, caddy, dozzle and the watchdog deployed one tag at a time (storage, network and encryption not run: no change in the preview). Deploying showed that the Caddy deploy rebuilds the image and takes 20+ minutes on a loaded Pi 4.
- [x] pi4: the first manual `backup-restic-local.sh` run succeeded (`restic_command_timeout` is 23 hours).
- [x] pinas: tinyauth, dozzle, scrutiny, caddy and homepage deployed with `--limit pinas`; Copyparty untouched (an upload was running). `storage` and `backup` run there too (the T7 and the 6 TB IronWolf).
- [ ] dietvostro last (real containers, never restart Docker there).
- [ ] Test the ntfy alert with a deliberate failure (no host runs ntfy yet; `alert.sh` logging to the journal is checked on pi4).
- [ ] Merge the stack into `main` only after pi4 is good.

## Phase 1: drives

- [ ] The remaining drive steps (the P10 and the fast/primary split) are in [drive-migration.md](./drive-migration.md).
- [ ] smartd: a rendered `/etc/smartd.conf` and a short script that posts to ntfy, behind a default-off switch. First check `smartctl -a` works through the actual USB enclosures (many bridges need `-d sat`). If SMART does not pass through, drop this item.
- [x] Connectivity watchdog: built and deployed on pi4 ([networking.md](../docs/networking.md#connectivity-watchdog)). A real outage has not occurred, so its reconnect branch is untested.
- Drive detach and mount stay documented in `docs/storage.md`; a script only if the manual steps turn out to be a frequent task.

## Phase 2: a proper backup status page

- [x] Built, not deployed: each backup script writes `<backup_logs_dir>/restic-<local|cloud|check>.status.json` when a run starts (`failed`, no finish time) and when it exits (the real result, from an `EXIT` trap), via the macro `roles/backup/templates/status-report.j2`. The page reads only those files; a missing, malformed or too old file is an error, never ok, and a fresh unfinished file shows "running". Logs are for people. The test (`tests/test_backup_status.py`) covers missing, stale, malformed, failed, running and unmounted; the macro was run in bash for exit 0, a failing exit, a failing pipeline and a killed run.
- Checked on pinas hardware? No: the card needs the backup role on a host with `backup_status_enabled`; pinas waits on its backup drive. Known limit: the local card no longer checks that a `daily` snapshot exists, and a failure before the status setup (a mount guard) leaves the previous file, which turns stale within 36 hours (9 days for the weekly jobs).
- [x] On pi4: `backup-restic-local.sh` ran once after deploy.

## Phase 3: make the code teachable

A fresh agent is not a newcomer: it explores the repo and guesses. The check gives it only the `docs/` pages and the file tree and has it write which files it would open and what it would change.

- [x] Task list run through a constrained reader (change the backup time; turn off a service and remove its data; add a service; remove the offsite notice; explain `just deploy caddy`; detach the backup drive). Its unanswered questions are fixed in the docs: where the schedules live, `just teardown`, what teardown leaves behind, example registry entries, the Caddy prerequisite, the default repo path.
- [x] Every doc audited against the code by a second reader; stale claims, missing commands and undefined terms fixed.
- [x] Computed settings have example values. Settings used once and never overridden were reviewed (`crafty_mc_ports`, `crafty_memory_limit`, `direct_link_peer_ip`, `docker_log_opts`) and kept: each is a knob an owner may reasonably turn.
- [ ] Open: the reader could not tell which message comes from which file ("the offsite notice"); a short "message I see → file that prints it" list is worth adding if a real owner asks.
- A human who has never used Ansible should still read the docs once and report where they stalled.

## Phase 4: single sign-on with Tinyauth

Wanted: "proper" login in front of everything that can take it. Authentik was judged too heavy (Postgres, Redis, workers).

Verified: Tinyauth's About page says it is for homelabs and sharing with family and friends, not for production needing roles and fine-grained permissions. v5.2.0 (2026-09-07); the docs use the floating `v5` tag, we pin the patch. It is an OpenID-certified provider since v5.1.0 (Core and Discovery only). The session cookie covers one parent domain, so it protects names under one private domain.

- [x] Role `tinyauth`, deployed on pi4 and pinas: every web service with a Caddy name is behind the login unless its `services.yml` entry has `own_login: true` (Immich, Gitea, Copyparty, ntfy, Tinyauth); protected names are served under the first private domain only; apps in Dockge opt in with one label; `tinyauth_environment` takes any other `TINYAUTH_*` setting; users are shared through the group vault. Checked on pi4: anonymous browser 302 to the login, other clients 401, a session passes with `Remote-User/Name/Email`, the generated Caddyfile has the snippet and the import, a throwaway whoami stack opted in with the one label.
- [ ] Still unchecked: forwarded headers without `TINYAUTH_AUTH_TRUSTEDPROXIES` (only IP rules and the Tailscale login need it); several `caddy_private_domains` with Tinyauth; the 2FA enrolment and a GitHub OAuth login ([auth-reference.md](../docs/auth-reference.md) is written from the docs and source, not tested).
- [ ] Copyparty. It has no OIDC, only header login: `idp-h-usr: remote-user`, `idp-h-grp: remote-groups`, plus `idp-h-key` (a header name that must be present, so the published port cannot forge identity). Design from the research:
  - Three lanes: the browser name behind Tinyauth (Caddy adds the secret header there only); share links on a second name with no forward-auth (`shr-site`); WebDAV, rclone, mobile and SFTP on the published port with Copyparty's own passwords (`auth-ord: idp,pw`).
  - Tinyauth sends `Remote-Groups` only for LDAP and OAuth logins, so Copyparty groups do not work with local Tinyauth users; give each Tinyauth user a matching Copyparty account name in `accs`.
  - The public tunnel on a host that sends a Cloudflare hostname straight to Copyparty bypasses Caddy, so SSO protects nothing there.
  - Built (`copyparty_sso_enabled`, default off), not deployed: deploy to pinas only when no upload is running.
- [x] Gitea and Immich sign in through Tinyauth's OIDC server (`gitea_sso_enabled`, `immich_sso_enabled`, default off; client secrets in the vault). Caddy gives the login name a network alias so containers reach it without leaving Docker. Built and render-tested, not deployed: deploy to pinas (Gitea and Immich restart) after the Copyparty upload ends, and check the first login of each by hand.
- [x] One login: Dockge's own login is switched off in its database when Tinyauth is in front and `dockge_port` is `""` (written with the container stopped, back on when Tinyauth is off). Not deployed. Crafty has no off switch or header trust (upstream issue 762 asks for OIDC), so it keeps a second login; revisit when upstream ships OIDC.
- [ ] Closed by default: `backup_status_port` is `""` (the dashboard has no login; an assert stops a host with neither Tinyauth nor a port). Other ports stay published on purpose: apps, git, WebDAV, push and game clients need them, and a derived "no port when Caddy is on" would silently unplug them. Tinyauth stays opt-in so Caddy works without it. pi4 sets `dockge_port: ""`; not deployed.
- [ ] Crafty: the owner decides between staying behind Tinyauth with a second, easy-to-type Crafty password (today) or `own_login: true` (one login, Crafty's own). Revisit when upstream OIDC (issue 762) ships.
- Decided: each host runs its own Tinyauth; the same `vault_tinyauth_users` in the group vault gives every host the same logins, and a host vault overrides it. A shared single Tinyauth instance is not built.
- [x] Dozzle (behind Tinyauth, no published port) and Scrutiny (devices read from `smartctl --scan` at deploy time) are roles, deployed on pinas; Dozzle also on pi4. Scrutiny on pinas sees the T7 and the IronWolf (57 °C during the read scan). Scrutiny on pi4 not deployed: no `smartmontools` there and its USB sticks are unlikely to report SMART.
- Not doing: Cockpit, Renovate, Uptime Kuma, Healthchecks, resticprofile, Backrest, the Cloudflare module, SOPS.

## Decided

- Backup schedules stay on cron. Both Pi reviews: a job is one readable task with its alert text inline; timers need six unit files, a handler and a generic `OnFailure` alert, for one gain (catching up a missed run) that the status page already shows as stale. If a missed offsite backup ever costs something, add a timer for the cloud job only.
