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

1. **Refactor on a branch** (below): the groups and vars split, plus the fixes for the stray profile, Tailscale and sudo. Proof: `--list-tasks` for the Pi 4 is unchanged, `just check` passes, and the owner's `--check --diff` against the Pi 4 shows nothing unexpected.
2. **pi5 joins `servers` only**, getting the base roles. The owner deploys and checks SSH, sudo, Tailscale, networking, zellij.
3. **Cloudflared and rclone come from the vault while still on the Pi 4** (below), so the cutover copies no files. pi5 can run the same tunnel alongside the Pi 4 before the Pi 4 stops, which makes the cutover close to zero downtime.
4. **Cutover:** pi5 moves into `nas`, the Pi 4 leaves it, the drives move ([checklist](#cutover-from-the-pi-4-to-pi5)).
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
- The container is the stock `cloudflare/cloudflared` image running `tunnel run --token-file` (needs cloudflared 2025.4.0 or later; the pinned version must be checked). The token sits in a `0600` file on the host.
- These API calls run with `delegate_to: localhost`, so the broad `CF_API_TOKEN` never lands on a server. Today it is rendered into a 0640 compose file. The owner's API token needs Tunnel Write and DNS Edit.
- **Removed:** `create_tunnel.sh`, both Dockerfiles, the init container, and the dead "migrate credentials from old location" task. That is roughly 200 lines of shell and a build step replaced by documented API calls.
- Tunnel names become per host.
- **Keep what `create_tunnel.sh` does today for DNS**, as Ansible tasks: a record that points at the wrong tunnel is deleted and recreated, and records still pointing at this tunnel for hostnames no longer in `cloudflared_ingress` are **reported, never deleted** (read from the script, `create_tunnel.sh` lines ~225-270). An orphan report that only warns is not cleanup, so the open question is whether to delete orphans automatically; the plan keeps today's report-only behavior unless the owner says otherwise.
- The old tunnel is deleted through the API at the migration, so no orphan tunnel is left behind.

**Migration of the existing tunnel.** Not documented in what I found. The owner checks the Zero Trust dashboard for a migrate option on the existing tunnel. If it exists, the tunnel ID and CNAMEs survive. If not, a new tunnel is created at step 3, Ansible repoints the CNAMEs, and there is a brief public outage while DNS moves. pi5 runs the new tunnel alongside the Pi 4 first.

### Public hostnames for ad-hoc apps

No router port forwarding is needed: cloudflared connects outward. For the ad-hoc host the choice is:

| Way | Per new app | Notes |
|---|---|---|
| **Wildcard to Caddy** (recommended for the ad-hoc host) | Docker labels only | One DNS record `*.<domain>` and one ingress rule `*.<domain>` → `http://caddy:80`, applied once by Ansible. Caddy routes by hostname from the labels. Nothing changes in Cloudflare or the repo per app |
| Rule per app in `cloudflared_ingress` | Repo change and deploy | What the NAS does. Explicit, easy to read; the right choice for the NAS |
| Dashboard rules | Cloudflare UI | Not declarative; the owner wants to avoid it |

The NAS keeps explicit rules. An explicit DNS record wins over a wildcard, so both can share a zone. Constraints to decide:

- **Use a dedicated domain for ad-hoc apps.** Cloudflare Access on `*.example.com` would also gate Immich and WebDAV and break the mobile apps. Access on a separate domain protects every ad-hoc app at once. Access lives in the Cloudflare account and survives rebuilds, so its one-time setup is acceptable.
- **Free certificates cover one level.** `*.apps.example.com` is not covered without paid Advanced Certificate Manager (Cloudflare's Universal SSL limitations page).
- **One wildcard points at one tunnel**, so one ad-hoc host per domain. A second ad-hoc host (the x64 box) needs another domain or Caddy routes over Tailscale. Decide when it exists.
- **Redirect loop.** cloudflared sends plain HTTP to Caddy, and Caddy's automatic HTTPS would redirect and loop. Set the global option once on the Caddy container (`caddy.auto_https: off` by the label rules, inferred; verify when built) rather than `http://` in every app's labels.
- The wildcard exposes every labeled container. Treat "add a label" as "publish to the internet" unless Access is in front.

## rclone and offsite backends

restic speaks several backends natively (checked in its docs): S3 and compatible services, **Backblaze B2** (`b2:bucket:path`, though restic's docs recommend B2's S3 endpoint), **SFTP** (`sftp:user@host:/path`). **rclone is only needed for services restic lacks, such as Google Drive.** The design follows restic's documentation with no layer of ours:

- `restic_cloud_repository` stays the one switch; its URL scheme picks the backend.
- A new `restic_cloud_env` dictionary holds credentials as vault references. The role renders it to a `0600` env file the backup scripts source. The weekly check and the dashboard use the same file.

```yaml
# Backblaze B2 over S3
restic_cloud_repository: "s3:s3.us-west-004.backblazeb2.com/my-bucket/nas"
restic_cloud_env:
  AWS_ACCESS_KEY_ID: "{{ vault_cloud_key_id }}"
  AWS_SECRET_ACCESS_KEY: "{{ vault_cloud_key }}"

# SFTP (private key in the vault, host key pinned in known_hosts, or the first cron run fails)
restic_cloud_repository: "sftp:backup@host:/srv/restic"

# Google Drive (unchanged)
restic_cloud_repository: "rclone:gdrive-nas:/pi-nas-backups"
```

- **Tested here:** restic accepts `-o rclone.args=...` on a non-rclone repository (throwaway local repo), so the existing option does not break other backends.
- The `listremotes` probe and the `gdrive-nas` check in the backup role apply only to `rclone:` repositories.
- **A configured repository whose init fails must fail the deploy**, not skip silently as today.
- **Google Drive:** run `rclone authorize "drive"` on the Mac, put the token in the vault, and have Ansible write `rclone.conf` only when absent (`force: false`), since rclone writes refreshed tokens back. With your own OAuth client, Google expires refresh tokens after 7 days while the app is in "Testing" (reported by rclone users; check Google's docs), so publish it to Production.
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
| Gitea runner registration (anonymous Docker volume) | Re-register the runner, or copy the volume |
| Immich model cache and Redis | Rebuild themselves |
| Tailscale identity | pi5 is a new node: new IP and MagicDNS name. Update WebDAV mounts, bookmarks, the inventory and Funnel |
| `autoback`, `obtain-ampere` containers | Outside this repo; they do not move |

Not yet checked: `immich_microservices` has an anonymous volume on the Pi 4 and may be a stale container.

Order: take fresh service dumps and a local snapshot and verify them (`restic snapshots`, `restic check`), avoiding the 2 AM and 4 AM cron windows; stop the stacks cleanly so Postgres shuts down properly; shut the Pi 4 down and **leave its microSD untouched** (moving the drives back is the rollback); move both drives to pi5's blue USB 3 ports; the owner runs `--check --diff` then deploys; verify Immich, Copyparty, Gitea, a backup run and the `/mnt/backup` mount; keep the Pi 4 off for a week before repurposing it.

Power: pi5 has a supply that provides full power, so the USB budget is 1.6A in total. The 500GB HDD has its own brick. The later P10 has none, and the T7 and P10 will both draw bus power from the same 1.6A, so [drive-migration.md](./drive-migration.md) needs a combined-draw check or a powered hub.

## Documentation

This is a major change: **each step updates its docs in the same commit** as the code. Files that change:

| File | Change |
|---|---|
| `README.md` | Doc table; the repo is no longer "a NAS only" |
| `ansible/README.md` | Setup (inventory, vault layout, first run with `-K`), commands, "add a service/host" |
| `docs/ansible-terms.md` | `host_vars`, `group_vars/all`, several plays, the sudoers drop-in |
| `docs/services.md` | The direct link moves to `networking.md` |
| `docs/networking.md` | New (written now for the parts true today) |
| `docs/backups.md` | Backends, the vault-managed rclone remote |
| `docs/storage.md` | Per-host drives |
| `AGENTS.md` | "The Pi" becomes "any host"; single-NAS wording |
| `ansible/justfile` | `--limit`, per-host commands |
| `docs/plans/drive-migration.md` | The pi5 order and the power note |

## Owner items

Decisions and things to do by hand before work starts:

1. Dedicated domain for ad-hoc apps, and the one-time Cloudflare Access setup on it.
2. In the Zero Trust dashboard, check whether the existing tunnel can be migrated to remotely managed.
3. Confirm the Cloudflare API token has Tunnel Write and DNS Edit.
4. Run the netplan spike on pi5 (commands and pass criteria in `networking.md`).
5. Run the first deploy on each new host with `-K`; the sudoers task removes the need afterward.
6. Disable Tailscale key expiry for each server.
7. When installing Ubuntu on the x64 box, do not choose the Docker snap.

## Open decisions

- netplan vs nmcli (the spike).
- The ad-hoc platform and domain.
- Whether the second Pi joins Tailscale by hand or with a one-off key.
