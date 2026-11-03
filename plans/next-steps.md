# Next steps: verify, harden, make the code teachable

> **Status: active plan. Delete this file when the phases are done; git history keeps it.** It records decisions, not conventions: the rules are in AGENTS.md and the code.

Goal: a CS or homelab newcomer can run the setup, and can read, change, remove and add behaviour in the code that drives it. Reliability of backups comes first. Each step keeps the AGENTS.md rules (opt-in switch, one place per default, a comment on every setting, `just check` passes, no playbook run against a host by an agent).

## Phase 0: prove what exists

Nothing from `audit-cleanup` → `service-registry` → `setup-recipe` has run on a host.

- [x] `just preview --limit pi4` passes (8 changes: Dockge and Caddy compose, backup scripts and exclude list, the check job moves to Saturday 5 AM). It found a real bug the render test missed (the dump-script check failed on entries without `dump_required`); fixed and tested.
- [ ] Deploy one part at a time to pi4: common, network, storage, caddy, homepage, backup (encryption only if used). Fix what it shows, each fix a small commit with a render-test line that would have caught it.
- [ ] Same on pinas; dietvostro last (real containers, never restart Docker there).
- [ ] Test the ntfy alert with a deliberate failure.
- [ ] Merge the stack into `main` only after pi4 is good.

## Phase 1: drives

- [x] The 500 GB drive is out and the 6 TB IronWolf is in.
- [ ] Read the IronWolf's long SMART test when it finishes (`smartctl -a`).
- [ ] smartd: a rendered `/etc/smartd.conf` and a short script that posts to ntfy, behind a default-off switch. First check `smartctl -a` works through the actual USB enclosures (many bridges need `-d sat`). If SMART does not pass through, drop this item.
- [x] Connectivity watchdog (built, not deployed) (opt-in role, switch `connectivity_watchdog_enabled`, default off). pi4 once stayed on wifi with a valid address and working ping while every TCP and DNS lookup failed, so it dropped off Tailscale until `nmcli con down` and `up` fixed it (2026-11-02, cause unknown). Nothing emitted an event, so only an active probe can notice. Design (both Pi reviews agree on the first three):
  - Probe: a TCP connect to port 443 of 1.1.1.1 and 8.8.8.8 (bash `/dev/tcp` in `timeout`); healthy if either connects. Not ICMP (it passed during the fault), not DNS, not Tailscale health (flaps on control-plane trouble).
  - Act only after 3 failed probes in a row, at most once per 30 minutes, then reconnect the NetworkManager connection on the default-route interface (`nmcli con down`, `up`; covers wifi and Ethernet and never the direct link, which has no gateway). Stop acting after about 3 hours so a real outage cannot loop; resume on the first success. Never reboot. Hosts without NetworkManager only probe and log.
  - Log every step with `logger -t connectivity`; send one ntfy alert once the probe succeeds again (ntfy is unreachable mid-outage).
  - Run it from `cron` like the backups (one scheduling mechanism in the repo), every 2 minutes as root, with its counters in `/run` so a reboot resets them. The reviews proposed a systemd timer; cron keeps one readable task and no unit files.
  - Needs `alert.sh` and `ntfy_server`/`ntfy_alert_url` outside the backup role, because the watchdog must work with backups off: move `alert.sh` to `common` and the ntfy settings to `group_vars/all/defaults.yml` (cross-role settings live there), as one small commit before the watchdog. `alert.sh` gets an optional tag/title argument, default `backup`.
  - Render test: both probe addresses present, no `reboot`, no hard-coded interface name, the alert default still renders as before.
  - Built (role `connectivity_watchdog`, docs/networking.md); deploy to pi4 after Phase 0, with a manual dry run of the `nmcli` commands first.
- Drive detach and mount stay documented in `docs/storage.md`; a script only if the manual steps turn out to be a frequent task.

## Phase 2: a proper backup status page

The page keeps both halves: job status and snapshot browsing. The job-status half currently reads our log text (`=== Complete:`), so rewording an echo line breaks it silently.

- Option A (chosen direction, to be confirmed against the code): each backup script also writes a small status file (job, start, end, result, snapshot count), and the page reads that file. The log stays for humans. A test renders the scripts and checks they write every field the page reads.
- Option C would leave the log scraping as it is.
- Decide the status file's location and format before building; the page shows an error, never "ok", when the file is missing or malformed.

## Phase 3: make the code teachable

A fresh agent is not a newcomer: it explores the repo and guesses. To get closer, give it only the `docs/` pages and the file tree (no search, no git history), and have it answer in writing which files it would open and what it would change, before it touches anything. Treat its confusion as a signal, not a verdict; the owner reads the same docs once.

- [ ] Write the task list: change the backup time; turn off one service and remove its data safely; add a service from a Docker image; remove one behaviour (the offsite notice); explain what `just deploy caddy` does.
- [ ] Scrutinise every existing doc: wrong or stale statements, jargon without a one-line meaning (link `docs/ansible-terms.md`), steps that skip a command, and the same example repeated in several places.
- [ ] Add a short `docs/how-it-works.md` only if the task list shows the gap (from `just deploy` to a changed host; how a setting flows from defaults to host variables).
- [ ] Comment the Jinja a newcomer cannot read, with an example value: `enabled_service_keys`, `backup_service_dirs`, `ntfy_alert_url`, the conditional strings in `services.yml`. Replace with plain tasks wherever the clever form has no current need.
- [ ] List every setting with its use count; inline the ones used once and never overridden (configuration fatigue).
- Done when the task list completes with no question the docs cannot answer.

## Phase 4: single sign-on with Tinyauth

Wanted: "proper" login in front of everything that can take it, from Gitea to an ad-hoc app such as SilverBullet, and covering Scrutiny and Dozzle. Authentik was judged too heavy (Postgres, Redis, workers; about 1.2 GB RAM reported).

- [ ] Verify before building: Tinyauth's docs say it is not for production (read that page), the Caddy label form with our numbered `caddy_N` labels, and behaviour with several `caddy_private_domains` (one cookie domain per instance).
- [ ] Design with two modes per service in `services.yml`: browser-only apps behind forward-auth (`auth: true` becomes one Caddy label); apps that have their own OIDC login (Gitea, Immich) use Tinyauth as the OIDC provider, with clients rendered from the vault. Apps with non-browser clients (git, WebDAV, mobile apps, S3, ntfy tokens) never sit behind forward-auth.
- [ ] Ad-hoc apps in Dockge opt in with one label.
- [ ] Scrutiny and Dozzle: opt-in roles added behind Tinyauth, if wanted after smartd.
- Not doing: Cockpit, Renovate, Uptime Kuma, Healthchecks, resticprofile, Backrest, the Cloudflare module, SOPS.

## Decided

- Backup schedules stay on cron. Both Pi reviews: a job is one readable task with its alert text inline; timers need six unit files, a handler and a generic `OnFailure` alert, for one gain (catching up a missed run) that the status page already shows as stale. If a missed offsite backup ever costs something, add a timer for the cloud job only.
