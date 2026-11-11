# Next steps: verify and finish

> **Status: active plan. Delete this file when every box is ticked; git history keeps it.** It records open work and decisions, not conventions: the rules are in AGENTS.md and the code.

Goal: someone who is not a full-time sysadmin can run the setup and read, change, remove and add behaviour in the code. Backup reliability comes first.

## Open

- [ ] Deploy the remaining hosts one tag at a time, the one with real containers last (never restart Docker there). Merge the opt-in stack into `main` only after the first host is good.
- [ ] Test `alert.sh` and a pics alert with a deliberate failure.
- [ ] The remaining drive steps (the new drive and the fast/primary split): [drive-migration.md](./drive-migration.md).
- [ ] Backup status page: built and tested, not checked on a host whose backup drive is attached. A failure before a script's status setup (a mount guard) leaves the previous file, which turns stale within 36 hours (9 days for the weekly jobs).
- [ ] Message I see, file that prints it: a short list is worth adding if a real owner asks.
- [ ] A person who has never used Ansible reads the docs once and reports where they stall.
- [ ] Tinyauth, unchecked: forwarded headers without `TINYAUTH_AUTH_TRUSTEDPROXIES` (only IP rules and the Tailscale login need it); several `caddy_private_domains`; two-factor enrolment and a GitHub login ([auth-reference.md](../docs/auth-reference.md) is written from the docs and source, not tested).
- [ ] Built, not deployed (deploy when no upload is running, then check the first login of each by hand): Copyparty sign-in through Tinyauth (`copyparty_sso_enabled`), Gitea and Immich sign-in through Tinyauth (`gitea_sso_enabled`, `immich_sso_enabled`), Dockge's own login switched off behind Tinyauth (`dockge_port: ""`).
- [ ] Crafty: stay behind Tinyauth with a second, easy-to-type Crafty password (today) or `own_login: true` (one login). Revisit when upstream ships OpenID Connect (issue 762).

## Decided

- Backup schedules stay on cron: a job is one readable task with its alert text inline. Timers need six unit files, a handler and a generic `OnFailure` alert, for one gain (catching up a missed run) that the status page already shows as stale. If a missed offsite backup ever costs something, add a timer for the cloud job only.
- Each host runs its own Tinyauth; the same `vault_tinyauth_users` in the group vault gives every host the same logins, and a host vault overrides it. A shared instance is not built.
- Tinyauth fits a homelab, not setups needing roles and fine-grained permissions; the session cookie covers one parent domain, so protected names live under one private domain. Authentik was judged too heavy (Postgres, Redis, workers).
- Published ports stay on purpose (apps, git, WebDAV, push and game clients need them); a derived "no port when Caddy is on" would silently unplug them. `backup_status_port` is `""` by default (the dashboard has no login of its own).
- Drive alerts come from Scrutiny's notifications, not smartd ([services.md](../docs/services.md#scrutiny-drive-health)).
- Drive detach and mount stay documented in [storage.md](../docs/storage.md); a script only if the manual steps turn out to be a frequent task.
- Not doing: Cockpit, Renovate, Uptime Kuma, Healthchecks, resticprofile, Backrest, the Cloudflare module, SOPS.
