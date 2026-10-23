# Multi-host plan (NAS + general servers)

Status: planned, nothing implemented. All implementation goes on a branch; only docs go straight to main.

## Goal

Manage the NAS and other always-on machines (a second Pi, later an x64 desktop) from this one repo, declaratively, with plain Ansible. Reliability and the owner maintaining it without an AI agent are equal top priorities (AGENTS.md). Nothing is added as a "temporary" shortcut; where today's code is debt, the refactor removes it.

- **NAS** (pi5, confirmed): fully Ansible-managed. Drives, Immich, Copyparty, backups.
- **General servers** (the Pi 4 afterward, later the x64 box): Ansible sets up the base (SSH, Tailscale, networking where needed, backups of the machine itself, Docker, a container manager and a reverse proxy). The owner runs apps ad-hoc. This fits the existing rule: Ansible owns what it deploys, the owner owns the rest.

## Supported systems

**Debian family only**: Raspberry Pi OS, Debian, and **Ubuntu Server** (decided). An `assert` on `ansible_os_family` in `common` fails an unsupported host at the start with a clear message. Fedora and other RPM distros would add SELinux `:Z` labels on every bind mount, `dnf` package names and `firewalld`; that stays out until there is a Fedora host.

Ubuntu Server specifics to design for, so it works there and not just on Pi OS:

- **Do not install Docker from the installer's snap.** It conflicts with `geerlingguy.docker`. The `common` role asserts that no docker snap is present.
- **Networking is netplan, rendered by systemd-networkd**, not NetworkManager (see Networking).
- **cloud-init** also writes `/etc/netplan/50-cloud-init.yaml`, so the network-config switch applies there too.
- The installer's first user is on password sudo, so the first run uses `-K` as on any new host (see Sudo).
- The direct-link dnsmasq uses `port=0` (DHCP only), so it does not collide with systemd-resolved on port 53. Keep it that way.
- Ubuntu on a Pi needs the Pi's firmware path (`/boot/firmware/config.txt`), and the overclock role runs on Pi hosts only.

Other consequences:

- `ansible.builtin.apt` for packages, with each role's package list in one place.
- Binaries we download (zellij) use static builds that exist for aarch64 and x86_64.
- The remaining amd64 risks are the ARM-only builds (rawpy, Dockerfile ARGs), checked when the x64 box is added.

## Order of work

Each step is a gate: the owner verifies it before the next starts, so a failure has one possible cause. pi5 has nothing on it and the Pi 4 keeps running the NAS until the cutover, so pi5 is a safe place to test the new structure.

1. **Refactor on a branch**, in two parts so a diff has one possible cause:
   - **1a, structural only:** the groups and vars split, `derived.yml`, option renames' mapping, the inventory and play layout. Proof: `--list-tasks` for the Pi 4 is unchanged, `just check` passes, and the owner's `--check --diff` shows nothing.
   - **1b, behavior changes, one commit each, each stating its expected `--check --diff`:** log rotation (`daemon.json` gains `log-opts` and Docker restarts; a one-time recreate follows), the sudoers drop-in (`/etc/sudoers.d/90-ansible` appears), the Gitea runner bind mount (needs the copy step below), the copyparty option renames, pinned `cloudflared`, `tailscale_enabled: true` with `tailscale_up_skip` and `state: present`, the network role's profile-name variable. The owner checks `--check --diff` per commit.
2. **pi5 joins `servers` only**, getting the base roles. The owner deploys and checks SSH, sudo, Tailscale, networking, zellij.
3. **Cloudflared and rclone come from the vault while still on the Pi 4** (below), so the cutover copies no files. pi5 can run the same tunnel alongside the Pi 4 before the Pi 4 stops, which makes the cutover close to zero downtime.
4. **Cutover:** pi5 moves into `nas`, the Pi 4 leaves it, the drives move ([checklist](#cutover-from-the-pi-4-to-pi5)).
   - **4b, after cutover:** the Docker data-root tests (below), because they need a real drive and every drive is on the Pi 4 until now. `docker_data_root` ships unset in 1b.
5. **Later:** per-host backups, the Pi 4 as a general server, the ad-hoc platform, then the x64 box.

## Ansible shape

Only standard Ansible features, no wrapper of our own.

- **Inventory:** hosts are named after hardware (`pi4`, `pi5`, later `desktop`). Groups are named after function: `nas` and `servers_general`, both under a parent group `servers`. Changing which machine is the NAS is a one-line move.
- **Settings:**
  - `group_vars/all/`: timezone, SSH public keys, base flags.
  - `group_vars/nas/`: drives, services, restic (stays where it is).
  - `host_vars/<host>/`: wifi, direct link, overclock, per-host `_enabled` overrides, per-host secrets in `vault.yml`.
- **Vault:** several encrypted files, one per scope (`all`, `nas`, each host), all with the same password. `ansible/README.md` setup changes accordingly.
- **`site.yml`:** one play for `hosts: servers` (common, tailscale, network, base roles) and one for `hosts: nas` (storage, services, backup). The existing `<name>_enabled` flags keep doing per-service opt-in.
- **Access:** set `ansible_host` to the Tailscale (MagicDNS) name so Ansible reaches a Pi on any network. `pi5.local` stops resolving on a phone hotspot.

Things that break if the files are split carelessly:

| Item | Problem | Fix |
|---|---|---|
| `pre_tasks` vault assert | Checks `vault_restic_password`, which only the NAS has | Move into the `nas` play |
| `tests/render.yml` | Renders templates with the example vars and diffs `vars.yml` against `vars.yml.example` | Update it for `all`/`nas`/`host_vars`; part of the refactor |
| `network` role | Both blocks use `nmcli state: present` on `"Wired connection 1"`, and one runs on every deploy even with `direct_link_enabled: false`. On pi5 (profile `netplan-eth0`) that creates a stray profile | The role stops touching profiles it did not create; see Networking |

### Sudo

Pi OS no longer ships passwordless sudo, and pi5 asks for a password. Ubuntu Server's installer also leaves its first user on password sudo (only cloud images such as the Pi's Ubuntu image start with passwordless sudo). The Pi 4 is passwordless today.

Decision (owner's preference): **one managed sudoers drop-in, applied once with the password.** A task in `common` writes `/etc/sudoers.d/90-ansible` (`{{ ansible_user }} ALL=(ALL) NOPASSWD:ALL`, mode `0440`, `validate: visudo -cf %s`). The first run on a new host uses `-K` (`--ask-become-pass`) and types the password once; later runs need nothing. It is the same on Pi OS, Debian and Ubuntu, there is no password in the vault, and the task is idempotent, so a host that already has passwordless sudo reports no change. Trade-off: anyone holding the SSH key is root. That was already true of the Pi 4, and the key is the only way in. The `ansible_become_password` vault alternative is dropped.

Checked: the shipped scripts and cron jobs never call `sudo` (only messages mention it; `copyparty-funnel.sh` is run by hand).

### Tailscale

- `tailscale_enabled: false # tmp since already deployed` is removed. Tailscale is on for every server.
- The `artis3n.tailscale.machine` role defaults to `state: latest`, which would upgrade Tailscale on the live NAS during the first deploy. Pass `state: present` and update deliberately.
- It fails with an empty `tailscale_authkey` unless `tailscale_up_skip: true` is set (read in the installed role). We do not use a reusable key: join each host by hand once with `sudo tailscale up` and set `tailscale_up_skip: true` in its `host_vars`. A one-off key in that host's vault, deleted after the first run, also works. Nothing in this repo reads the role's facts (grep: none), so skipping them is safe.
- **Disable key expiry for each server in the Tailscale admin console.** Keys expire after 180 days by default, and a headless Pi then locks you out.

## Networking

Full runbook: [../networking.md](../networking.md). Design decisions:

**cloud-init vs Ansible.** cloud-init (Raspberry Pi Imager, Ubuntu) configures a machine once, at first boot. Ansible re-applies the repo's state every run. Imager only makes the Pi reachable (user, hostname, SSH key, first wifi). After that, Ansible owns networking, through one file per host in `host_vars`. A base role writes `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` (`network: {config: disabled}`, cloud-init's documented switch) wherever `/etc/cloud` exists, so cloud-init cannot rewrite it later.

**netplan is the leading option for the one tool**, because it is the only layer present on both Pi OS trixie (rendering to NetworkManager; `netplan.io` is installed on pi5) and Ubuntu Server (rendering to systemd-networkd). Ansible would render one `/etc/netplan/60-ansible.yaml` from `host_vars` and apply it with `netplan try`, which reverts automatically if the connection is not confirmed. That would replace the hand-built revert timer.

**It is not decided until a spike passes on pi5.** pi5 is empty, so the owner can run it by hand. Risks: Imager's `90-NM-*.yaml` files, generated by NetworkManager's netplan integration, may produce duplicate profiles next to an Ansible-written file (the stray-profile problem again), and `netplan try` may not roll back when the renderer is NetworkManager. Pass criteria:

1. After applying an Ansible-style netplan file, `nmcli con show` lists exactly one profile per interface or SSID.
2. `netplan try` rolls back when the confirmation is not given.

If either fails, fall back to `nmcli` on NetworkManager hosts (profile names become per-host variables, fixing the stray profile) and no network role on wired Ubuntu boxes. No multi-backend abstraction either way.

**Fallback behavior** (also in `networking.md`): NetworkManager's `autoconnect-priority` picks among profiles in range and knows nothing about internet reachability; autoconnect never replaces an already-active profile, so a Pi on a hotspot probably stays there. There is no switch-back automation yet. The recovery is `nmcli con up <home>` over Tailscale or the direct link.

The direct Ethernet link is a static profile with no gateway, up whenever the cable is in.

## Cloudflared: tokens from the vault, no credentials file

Today's role creates a **locally managed** tunnel (`config_src: local`). Cloudflare returns the tunnel secret only at creation, so the credentials JSON is the only copy. On a host without it, `create_tunnel.sh` finds the existing tunnel by name and stops with an error. Copying the file is a workaround for that design, and the API token and account ID in the vault are not enough to recover it.

**Redesign: a remotely managed tunnel.**

- Ansible creates the tunnel once (`POST .../cfd_tunnel` with `config_src: cloudflare`), sets ingress with `PUT .../cfd_tunnel/{id}/configurations`, and fetches the token any time with `GET .../cfd_tunnel/{id}/token`, using `ansible.builtin.uri`. DNS records use `community.general.cloudflare_dns` (checked: it supports `proxied` CNAMEs).
- The container is the stock `cloudflare/cloudflared` image running `tunnel run --token-file` (`--token-file` needs cloudflared 2025.4.0 or later). `versions.yml` has `cloudflared_image: cloudflare/cloudflared:latest` today, which also breaks the pinning rule in AGENTS.md; the refactor pins a version (2026.10.3 was the latest release on 2026-10-23) and the pin is confirmed with `cloudflared tunnel run --help`. The token sits in a `0600` file on the host.
- These API calls run with `delegate_to: localhost`, so the broad `CF_API_TOKEN` never lands on a server. Today it is rendered into a 0640 compose file. The owner's API token needs Tunnel Write and DNS Edit.
- **Removed:** `create_tunnel.sh`, both Dockerfiles, the init container, and the dead "migrate credentials from old location" task. That is roughly 200 lines of shell and a build step replaced by documented API calls.
- Tunnel names become per host.
- **Keep what `create_tunnel.sh` does today for DNS**, as Ansible tasks: a record that points at the wrong tunnel is deleted and recreated, and records still pointing at this tunnel for hostnames no longer in `cloudflared_ingress` are **reported, never deleted** (read from the script, `create_tunnel.sh` lines ~225-270). An orphan report that only warns is not cleanup, so the open question is whether to delete orphans automatically; the plan keeps today's report-only behavior unless the owner says otherwise.
- The old tunnel is deleted through the API at the migration, so no orphan tunnel is left behind.

**Migration of the existing tunnel.** Not documented in what I found. The owner checks the Zero Trust dashboard for a migrate option on the existing tunnel. If it exists, the tunnel ID and CNAMEs survive. If not, a new tunnel is created at step 3, Ansible repoints the CNAMEs, and there is a brief public outage while DNS moves. pi5 runs the new tunnel alongside the Pi 4 first.

### Public hostnames for ad-hoc apps

Owner decision: **no Cloudflare Access, no wildcard.** Tunnels are only for what must be reached outside Tailscale. Everything else is reached over Tailscale, which already authenticates every device.

- **Default for ad-hoc apps: tailnet only.** Reach them at `http://<host>:<port>` over MagicDNS, or through Caddy if a name is wanted. Nothing is published.
- **To publish one app:** add a `hostname` and `service` entry to that host's `cloudflared_ingress`, exactly as the NAS does today, and deploy. The reconcile tasks create the DNS record and report orphans. It is a one-line repo change and nothing is done in the Cloudflare UI.
- **Why not a wildcard:** a wildcard to Caddy makes every labeled container public the moment it starts. Many self-hosted apps have weak or no login, and without Access nothing sits in front of them. Explicit entries keep "public" a deliberate act.
- A wildcard (and Access, on a separate domain) stays a later option if the one-line entry becomes annoying; nothing here blocks it.

## rclone and offsite backends

Owner's actual need: **Google Drive now, SFTP maybe later. Not S3 or B2.** restic reaches SFTP natively (`sftp:user@host:/path`, checked in its docs) and Google Drive only through rclone. The design is therefore two cases, with no layer for backends nobody uses:

```yaml
# Google Drive (today)
restic_cloud_repository: "rclone:gdrive-nas:/pi-nas-backups"

# SFTP (later, if wanted): private key in the vault, host key pinned in known_hosts
restic_cloud_repository: "sftp:backup@host:/srv/restic"
```

- `restic_cloud_repository` stays the one switch; the URL scheme picks the backend. If S3 or B2 is ever wanted, restic takes their URL here too, plus the credentials as environment variables. That is added when there is a use, not before (AGENTS.md: no abstraction without a current use). The earlier `restic_cloud_env` idea is dropped for that reason.
- **Tested here:** restic accepts `-o rclone.args=...` on a non-rclone repository (throwaway local repo), so the existing option does not break SFTP.
- The `rclone listremotes` probe and the `gdrive-nas` check in the backup role apply only to `rclone:` repositories.
- **A configured repository whose init fails must fail the deploy.** Today a missing `gdrive-nas` remote silently skips cloud init.
- **Google Drive remote from the vault:** run `rclone authorize "drive"` on the Mac, put the token in the vault, and have Ansible write `rclone.conf` only when absent (`force: false`), since rclone writes refreshed tokens back. Verified in Google's OAuth documentation: a refresh token expires after **7 days when the OAuth consent screen is External and its publishing status is "Testing"**, and also after 6 months unused or when revoked. So publish the app to Production (or the backup silently stops after a week).
- **SFTP:** the private key lives in the vault and the server's host key is pinned in `known_hosts`, or the first cron run fails on the host-key prompt.
- The dashboard only receives `restic_cloud_repository`, so it needs no change (checked with grep).

## Per-host backups

The same restic pattern on every host; only the inputs change: what to back up, where, and whether there is an offsite copy. Those move to `host_vars`, not the NAS-only drive roles.

- Pi microSD to a 128GB USB drive: restic backs up files (`/etc`, `/opt`, home), not a bootable image. A bootable clone is a different tool (`rpi-clone`).
- x64 256GB SSD to its 512GB SSD: same pattern.
- A second drive in the same machine covers drive failure, not theft or fire. Only the NAS has an offsite copy.
- Not yet checked: how much of the `backup` role depends on `nas_drives`.

## Base roles

Small, each on a standard module:

- SSH authorized keys: `ansible.posix.authorized_key`.
- **Ghostty terminfo:** pi5's `ncurses-term` has no `xterm-ghostty`. Copy it from the Mac (`infocmp -x xterm-ghostty`) and compile with `tic -x`.
- **Zellij** (full build, decided): not in Debian trixie's apt (checked on pi5). Use the static musl release (aarch64 and x86_64; v0.45.1 today), pinned in `versions.yml` with its sha256 and installed to `/usr/local/bin` with `get_url` and `unarchive`.
- Wifi and the cloud-init switch (Networking).
- Optional overclock (`arm_freq` in `/boot/firmware/config.txt`), off by default, Pi hosts only. Not on the NAS: its limits are IO and network, and an unstable clock risks data.

## Configuration conventions

The owner asked that every option, its default and its meaning be easy to find and hard to get out of sync. Checked against Ansible's documentation and this repo:

**Where an option lives** (one place per option, as AGENTS.md already says):

| Kind | File | Edited by |
|---|---|---|
| Setting private to one role | `roles/<name>/defaults/main.yml` | Overridden in `vars.yml` or `host_vars` only when needed |
| Setting shared across roles or `teardown.yml` | `group_vars/<scope>/vars.yml` and its `.example` | Owner |
| Per-host setting (wifi, drives, data root) | `host_vars/<host>/vars.yml` and an example | Owner |
| Secrets | `vault.yml` files and examples | Owner |
| Image and tool versions | `group_vars/nas/versions.yml` | Owner (`just tags`) |
| **Derived values** (`nas_drive_mounts`, `fast_drive`, `main_drive`, `backup_drive`) | a tracked `group_vars/nas/derived.yml` | **Nobody**: Jinja logic does not belong in the file the owner copies and edits |

**One comment shape for every option**, in defaults files and example files alike, modeled on the restic comments already in `vars.yml.example`:

```yaml
# What it does, in one sentence.
# Allowed: <values or a type>. Default: <value>.   (only when not obvious)
# CAUTION: <the consequence of changing it later>.  (only where one exists)
crafty_memory_limit: 3g
```

**Defaults appear once.** Current drift to fix in the refactor: `tailscale_args`, `tailscale_funnel_enabled` and `tailscale_funnel_port` are set in both `vars.yml.example` and `roles/tailscale/defaults/main.yml`, which breaks the repo's own rule. The example file keeps only settings the owner is expected to change, shown commented out when the default is fine.

**Naming.** Role-private options carry the role name as a prefix. `.ansible-lint` skips `var-naming[no-role-prefix]` today (with a written reason that covers `register:` names and shared group vars). The refactor renames the options that break this on purpose, `sftp_enabled` and `host_mnt_dir` in the copyparty role, to `copyparty_sftp_enabled` and `copyparty_host_mnt_dir`, after grepping every use (templates, `teardown*.yml`, docs) and telling the owner to rename them in their own `vars.yml`.

**Checks:** the render test's key-parity check ("a key in `vars.yml` that is missing from `vars.yml.example`") is extended to every pair after the split: `group_vars/all`, `group_vars/nas`, a `host_vars` example, and the vault examples. The render test also loads `derived.yml`. The comment shape is enforced by review, not by a test: a parser for comments would be code to maintain for little gain.

**Decision for the owner: `meta/argument_specs.yml`?** Ansible (2.11+) validates a role's options at start: types, `choices`, `required`, with a description shown by `ansible-doc -t role`. Its docs state that the spec's `default` is documentation only, "the actual default for the role variable will always come from the role defaults", and that the two must be kept matching by hand. So it gives validation and a typed reference, at the cost of every default being written twice per role. Options: (a) **comments in `defaults/main.yml` as the single source** (recommended: plain, one place, matches the current repo); (b) argument specs for the roles that take many options, plus a render-test check that the defaults match. Recommendation is (a) now, revisit if wrong values reaching a role become a real source of failures. This is your call because it trades a typed reference against maintaining two copies.

## Docker data root, logs and state

**Why it matters:** the Pi runs from a microSD card. The Pi 4 runs Docker 29.4.2 with the **containerd image store** (`docker info` shows `Storage Driver: overlayfs`, `driver-type: io.containerd.snapshotter.v1`, `Docker Root Dir: /var/lib/docker`). Docker's documentation says containerd storage "is not automatically moved" by `data-root`, and that `data-root` "does not affect image and container data stored in `/var/lib/containerd`". It is the default for fresh installs from Docker 29.0. **So setting `data-root` alone would leave image layers on the SD.** A host gets the same default if `geerlingguy.docker` installs 29.x on it, which pi5 and the x64 box will.

**Make Docker's directory disposable.** Instead of migrating overlay layers, the plan is that nothing that matters lives in Docker's own storage. Checked on the Pi 4 (`docker inspect`):

| Volume | What it holds | Plan |
|---|---|---|
| `gitea-runner` `/data` (anonymous) | Runner registration: real state | Bind mount on the fast drive (backed up with it). On the Pi 4 a bind mount starts empty, so the step is: stop the runner, `docker cp gitea-runner:/data/. <bind dir>`, deploy; re-registering is the fallback |
| `immich_machine_learning` `/cache`, `immich_model-cache` | Model cache | Rebuilds; leave, or bind mount to avoid re-downloading |
| `immich_redis` `/data` (anonymous) | Redis cache | Rebuilds |
| `immich_microservices` `/data` (anonymous) | Container not in the repo; probably stale | Remove after checking it is not running |
| `nas-docker_caddy_*`, `nas-docker_model-cache`, `simple-nas_model-cache` | Look like leftovers of older project names | Check that nothing mounts them, then `docker volume rm` by name. Not `docker volume prune`: it removes anonymous volumes only, and `-a` would also remove `act-toolcache` and `immich_model-cache` whenever their containers are down (Docker's prune docs) |

**Rule:** a service's state is a bind mount under a drive role. Anything in Docker's storage can be deleted and re-created. New services (Dockge, Caddy's `caddy_data`) follow the same rule.

**The `docker_data_root` option** (empty by default, so Docker's default stays; set per host in `host_vars`). `geerlingguy.docker` writes one variable, `docker_daemon_options`, as `/etc/docker/daemon.json`. **A dict set in a host's `host_vars` replaces the same dict from `group_vars` instead of merging**, so log rotation set in one scope would vanish when another scope sets the data root. So the owner-edited settings are separate scalars (`docker_log_opts`, `docker_data_root`), and `docker_daemon_options` is built once from them with `combine` (`data-root` included only when set) in the tracked `derived.yml`. When `docker_data_root` is set, Ansible also places containerd's storage on the same drive. Two ways to cover containerd, to be chosen by a test on pi5, not by guesswork:

1. Set `root = "<path>/containerd"` in `/etc/containerd/config.toml` (the file ships with `containerd.io` and holds only `disabled_plugins = ["cri"]` on the Pi 4). Docker's daemon page names this file as the place to change containerd's location. Follows Docker's direction.
2. Disable the containerd image store (`"features": {"containerd-snapshotter": false}`). Docker's reference shows only `true` and says switching backends hides images from the other backend. Whether `false` is honored by 29.x is **not confirmed in the docs**; it is only a fallback.

Test (step 4b, after the cutover, on pi5 with a directory on the real drive): apply the option, restart, pull an image, and confirm with `du` that `/var/lib/docker` and `/var/lib/containerd` stay small. Record the result in `docs/` when done.

**Changing it, and changing it back.** Because state is disposable the procedure is the same both ways: stop `docker.service`, `docker.socket` (socket activation restarts the daemon mid-change) **and** `containerd.service`, change the setting, start, then `just deploy` so compose re-pulls images and recreates containers. No `rsync` of overlay layers (whiteouts, hardlinks and xattrs are where copies go wrong). The old directory stays behind as unused space; delete it once the stacks are healthy. Docker's docs do not give a migration procedure, so this is ours and is documented in `docs/storage.md`.

**Mount ordering.** On the Pi 4, `docker.service` has `Wants=containerd.service` (not `Requires=`) and `Requires=docker.socket` (`systemctl cat docker.service`), so a guard on Docker does not protect containerd. Both `docker.service` and `containerd.service` get a drop-in; otherwise containerd can start first and create its directory on the SD under the empty mount point, which the drive then hides. `geerlingguy.docker` does not manage `/etc/containerd/config.toml`, so the refactor adds a task (with a restart handler) for the `root` line and the two drop-ins. A systemd drop-in for `docker.service` with `RequiresMountsFor=<data root>` adds `Requires=` and `After=` on the mount unit (systemd.unit). With `nofail` the fstab mount is only *wanted* by `local-fs.target` (systemd.mount), but `RequiresMountsFor=` adds its own `Requires=` on that mount unit, so a failed mount should stop Docker from starting rather than letting it create an empty directory on the SD. The docs I read do not state this combination explicitly. **Test (step 4b):** reboot pi5 with the drive unplugged; `docker` must be inactive, not running on an SD directory.

**Log rotation (do now, independent of the data root).** Docker's docs: the default `json-file` driver does no rotation; `local` rotates by default. Plan: `docker_daemon_options` sets `log-driver: json-file` with `log-opts: {max-size: "10m", max-file: "3"}` (values must be strings). **These apply only to containers created after the change**, and compose-only services recreate only when their rendered file changes, so the first deploy adds a one-time step: recreate every stack (`docker compose up -d --force-recreate` per project, documented in `ansible/README.md`). A daemon restart also restarts containers unless `live-restore` is set; deploy this when a brief restart is acceptable.

## Ad-hoc app platform (decision pending)

Wanted: a lightweight Coolify-like layer for apps the owner starts by hand, with no database server, easy teardown, arm64 and amd64.

| Candidate | Role | Checked |
|---|---|---|
| Dockge | Compose stack manager (UI) | arm64 and amd64 images. Stacks are plain `compose.yaml` files in `/opt/stacks`, so teardown is removing one container. Stable (1.5.0) dates from March 2025; only `nightly` moves, so pin 1.5.0 and add `/opt/stacks` to that host's backup paths |
| caddy-docker-proxy | Reverse proxy from Docker labels | Multi-arch images at 2.13.1. No database. Syntax in [../caddy-reference.md](../caddy-reference.md). **An option, behind cloudflared** |
| tsdproxy | A tailnet hostname per container | Tailnet-only. arm64 not confirmed on its README. Needs a Tailscale key |
| Portainer + Traefik, Nginx Proxy Manager | Alternatives | Not researched |

## Cutover from the Pi 4 to pi5

Everything under `/mnt/t7` (Docker app data, Immich photos and database, Copyparty files, Homebridge, Gitea, Crafty) and `/mnt/backup` moves by plugging the drives into pi5; `nas_drives` uses UUIDs. By step 4, cloudflared and rclone come from the vault. What is left on the Pi 4's microSD:

| State | What to do |
|---|---|
| Docker's own storage (images, anonymous volumes) | Disposable by the rule in "Docker data root, logs and state": images re-pull. The Gitea runner registration becomes a bind mount in the refactor, so it moves with the drive |
| Tailscale identity | pi5 is a new node: new IP and MagicDNS name. Update WebDAV mounts, bookmarks, the inventory and Funnel |
| `autoback`, `obtain-ampere` containers | Outside this repo; they do not move |

Order: take fresh service dumps and a local snapshot and verify them (`restic snapshots`, `restic check`), avoiding the 2 AM and 4 AM cron windows; stop the stacks cleanly so Postgres shuts down properly; shut the Pi 4 down and **leave its microSD untouched** (moving the drives back is the rollback); move both drives to pi5's blue USB 3 ports; the owner runs `--check --diff` then deploys; verify Immich, Copyparty, Gitea, a backup run and the `/mnt/backup` mount; keep the Pi 4 off for a week before repurposing it.

Power: pi5 has a supply that provides full power, so the USB budget is 1.6A in total. The 500GB HDD has its own brick. The later P10 has none, and the T7 and P10 will both draw bus power from the same 1.6A, so [drive-migration.md](./drive-migration.md) needs a combined-draw check or a powered hub.

## Documentation

This is a major change: **each step updates its docs in the same commit** as the code. Files that change:

| File | Change |
|---|---|
| `README.md` | Doc table; the repo is no longer "a NAS only" |
| `ansible/README.md` and example files | The configuration conventions, the where-an-option-lives table |
| `ansible/README.md` | Setup (inventory, vault layout, first run with `-K`), commands, "add a service/host" |
| `docs/ansible-terms.md` | `host_vars`, `group_vars/all`, several plays, the sudoers drop-in |
| `docs/services.md` | The direct link moves to `networking.md` |
| `docs/networking.md` | New (written now for the parts true today) |
| `docs/backups.md` | Backends, the vault-managed rclone remote |
| `docs/storage.md` | Per-host drives; the Docker data root option and the procedure for moving it |
| `AGENTS.md` | "The Pi" becomes "any host"; single-NAS wording |
| `ansible/justfile` | `deploy` and `preview` take `--limit` and extra flags. Today they hard-code `--ask-vault-pass` and cannot pass `-K`, which the first run on a new host needs |
| `docs/plans/drive-migration.md` | The pi5 order and the power note |

## Owner items

Decisions and things to do by hand before work starts:

1. Decide `argument_specs` vs comments-only (Configuration conventions; recommendation is comments).
2. In the Zero Trust dashboard, check whether the existing tunnel can be migrated to remotely managed.
3. Confirm the Cloudflare API token has Tunnel Write and DNS Edit.
4. Run the netplan spike on pi5 (commands and pass criteria in `networking.md`).
5. Run the first deploy on each new host with `-K`; the sudoers task removes the need afterward.
6. Disable Tailscale key expiry for each server.
7. When installing Ubuntu on the x64 box, do not choose the Docker snap.
8. Publish the Google Drive OAuth app to Production (or backups stop after 7 days), and run `rclone authorize "drive"` on the Mac when the refactor reaches that step.
9. Run the data-root tests (below) right after the cutover, on pi5 with the real drive; I give the exact commands.

## Open decisions

- netplan vs nmcli (the spike).
- The ad-hoc platform.
- Whether orphan DNS records are deleted automatically (today they are only reported).
- containerd root vs disabling the containerd image store (the pi5 test).
- Whether the second Pi joins Tailscale by hand or with a one-off key.

## What is verified and what is not

Checked against primary documentation or the live Pi 4 / pi5 (read-only):

| Claim | Source |
|---|---|
| Pi 4 runs Docker 29.4.2 with the containerd image store; `data-root` does not move containerd storage | `docker info` on the Pi 4; Docker's containerd-store and daemon docs |
| `json-file` does no rotation by default; log options apply only to new containers | Docker logging docs |
| `RequiresMountsFor=` adds `Requires=` and `After=` on the mounts; `nofail` makes a mount only wanted by `local-fs.target` | systemd.unit, systemd.mount |
| An argument spec's `default` is documentation only | Ansible role docs |
| 7-day refresh-token expiry for apps in "Testing" | Google OAuth documentation |
| `cloudflared` latest release is 2026.10.3; `--token-file` landed in 2025.4.0 | GitHub releases page (version); the earlier check (flag) |
| `community.general.cloudflare_dns` supports `proxied` CNAME; restic reaches SFTP natively | module docs; restic docs |

Not verified, with the test that settles each:

| Open item | Test |
|---|---|
| Whether `RequiresMountsFor=` stops Docker when a `nofail` mount is missing | Step 4b, pi5: reboot with the drive unplugged; Docker and containerd must be inactive |
| Whether containerd `root` in `config.toml` moves image layers (and `false` for the snapshotter flag) | Step 4b, pi5: set it, pull an image, `du` both directories |
| Whether `netplan try` rolls back with the NetworkManager renderer; duplicate profiles next to `90-NM-*.yaml` | The spike in `networking.md` |
| `caddy.auto_https: "off"` as a global label | Read the generated Caddyfile when Caddy is first built |
| Whether the existing tunnel can be migrated to remotely managed | The Zero Trust dashboard |
| Whether a Pi on a hotspot returns to home wifi by itself | Not tested; recovery is `nmcli con up` |
| `cloudflared tunnel run --token-file` accepted by the pinned image | `--help` on that image |
