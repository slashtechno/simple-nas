# Multi-host plan (NAS + general servers)

Status: planned, nothing implemented. The pi5 migration comes first and is described below; the repo refactor (phase 1 onward) waits until the NAS is running on pi5.

## Goal

Manage the NAS and other always-on machines (a second Pi, later an x64 desktop) from this one repo, declaratively, with plain Ansible. Reliability and the owner maintaining it without an AI agent are equal top priorities (AGENTS.md), and nothing is added as a "temporary" shortcut.

- **NAS** (pi5, confirmed): fully Ansible-managed. Drives, Immich, Copyparty, backups.
- **General server** (the Pi 4 afterward, later the x64 box): Ansible sets up the base (SSH, Tailscale, networking where needed, backup of the machine itself, Docker, a container manager and a reverse proxy). The owner runs apps ad-hoc. This fits the existing rule: Ansible owns what it deploys, the owner owns the rest.

## Supported systems (decision for the owner)

Proposal: **Debian family only** (Raspberry Pi OS, Debian, Ubuntu Server), with an `assert` on `ansible_os_family` in the `common` role so an unsupported host fails at the start with a clear message.

Fedora and other RPM distros would add SELinux `:Z` labels on every bind mount, `dnf` package names and `firewalld`. That is real ongoing work for one hypothetical machine, so it stays out until there is a Fedora host.

Consequences for the design, so the x64 box does not become debt:

- Use `ansible.builtin.apt` for packages (Debian family) and keep package lists in one place per role.
- The NetworkManager wifi and direct-link settings apply only to hosts where NetworkManager manages the interface (Pi OS, Fedora). Ubuntu/Debian servers default to netplan/systemd-networkd or ifupdown, and a wired x64 box needs no network role at all. No multi-backend network abstraction; the role is simply not run on such hosts.
- The cloud-init network switch runs only if `/etc/cloud` exists. The overclock setting runs only on Pi hosts.
- `geerlingguy.docker` and the Tailscale role already support amd64. The remaining amd64 risks are the ARM-only builds (rawpy, Dockerfile ARGs), checked in phase 4.
- Binaries we download (zellij) use static builds that exist for aarch64 and x86_64.

## First: moving the NAS from the Pi 4 to pi5

The Pi 4 is only shut down once pi5 is deployed and verified. This is done on the current repo structure, not mixed with the vars split, so a failure has one possible cause.

### Blockers in the repo today (small fixes, to approve first)

| Item | Problem | Fix |
|---|---|---|
| `network` role | Both its blocks use `nmcli state: present` on `"Wired connection 1"`, and one block runs on every deploy even when `direct_link_enabled` is false. On pi5 (profile `netplan-eth0`) that creates a stray profile next to the real one | Make the default profile name a variable. Default to the current value, set `netplan-eth0` for pi5 |
| `tailscale_enabled: false # tmp since already deployed` | pi5 would never get Tailscale, and a "tmp" flag is debt | Set `tailscale_enabled: true` and `tailscale_up_skip: true` (below) |
| Sudo | pi5 asks for a sudo password; `just deploy` does not pass `-K` | First run with `-K`, then install a sudoers entry |

### What does not move with the drives

Everything under `/mnt/t7` (Docker app data, Immich photos and database, Copyparty files, Homebridge, Gitea, Crafty) and `/mnt/backup` moves by plugging the drives into pi5; the `nas_drives` entries use UUIDs. Found by listing the Pi 4's container mounts:

| State | Where on the Pi 4 | What to do on pi5 |
|---|---|---|
| rclone Google Drive remote | `~/.config/rclone/rclone.conf` | Copy it. Without it, cloud init and cloud backups silently skip, and offsite backups stop |
| Cloudflared tunnel credentials | `/opt/nas/cloudflared/*.json` (not in the vault) | Copy the JSON before the first deploy. `create_tunnel.sh` only reuses credentials it finds there; otherwise it creates a new tunnel |
| Gitea runner registration | anonymous Docker volume (microSD) | Re-register the runner, or copy the volume |
| Immich model cache and Redis | Docker volumes (microSD) | Rebuild themselves |
| Tailscale identity | the Pi 4 node | pi5 is a new node: new IP and MagicDNS name. Update WebDAV mounts, bookmarks, the inventory and Funnel |
| `autoback`, `obtain-ampere` containers | outside this repo | Do not move |

Not yet checked: `immich_microservices` has an anonymous volume on the Pi 4 and may be a stale container.

### Power and ports (owner to confirm)

- Pi 5 limits total USB power to 600mA unless it detects a 5V/5A USB-C supply (then 1.6A). Which supply do you have? Raspberry Pi warns that SSDs and hard drives may misbehave on the 600mA limit.
- The ST3500418AS is a 3.5" desktop drive. Confirm its USB enclosure has its own power brick.
- Plug both drives into the blue USB 3 ports.

### Order of operations

1. Make the three fixes above (on a branch, or direct to main if you prefer); `just check`; `--syntax-check`; `--list-tasks --limit pi5`.
2. Add pi5 to the inventory in the `nas` group; copy the cloudflared JSON and `rclone.conf`; join Tailscale by hand.
3. On the Pi 4: take fresh service dumps and a local snapshot, and verify them (`restic snapshots`, `restic check`). Avoid the 2 AM and 4 AM cron windows.
4. Stop the stacks cleanly so Postgres shuts down properly, then shut the Pi 4 down. **Leave its microSD untouched.** Moving the drives back is the rollback.
5. Move both drives to pi5.
6. You run `--check --diff` against pi5, then deploy with `-K`.
7. Verify: Immich, Copyparty, Gitea, a backup run, and `/mnt/backup` mounted.
8. Keep the Pi 4 powered off for a week before repurposing it.

The T7 plus the 500GB HDD move as they are; the drive upgrade follows in [drive-migration.md](./drive-migration.md).

## Ansible shape (after the migration)

Only standard Ansible features, no wrapper of our own.

- **Inventory:** hosts are named after hardware (`pi4`, `pi5`, later `desktop`). Groups are named after function: `nas` and `servers_general`, both under a parent group `servers`. Changing which machine is the NAS is a one-line move.
- **Settings:**
  - `group_vars/all/`: timezone, SSH public keys, base flags.
  - `group_vars/nas/`: drives, services, restic (stays where it is).
  - `host_vars/<host>/`: wifi, direct link, overclock, per-host `_enabled` overrides, per-host secrets.
- **`site.yml`:** one play for `hosts: servers` (common, tailscale, network, base roles) and one for `hosts: nas` (storage, services, backup). The existing `<name>_enabled` flags keep doing per-service opt-in.
- **Access:** set `ansible_host` to the Tailscale (MagicDNS) name so Ansible reaches a Pi on any network. `pi5.local` stops resolving on a phone hotspot.

Other things that break if the files are split carelessly:

| Item | Problem | Fix |
|---|---|---|
| `pre_tasks` vault assert | Checks `vault_restic_password`, which only the NAS has | Move into the `nas` play |
| `tests/render.yml` | Renders templates with the example vars and diffs `vars.yml` against `vars.yml.example` | Update it for `all`/`nas`/`host_vars`; part of phase 1 |

## Networking (one source of truth)

**cloud-init vs Ansible.** cloud-init (Raspberry Pi Imager) configures a machine once, at first boot. Ansible re-applies the repo's state every run. Use Imager only to make the Pi reachable (user, hostname, SSH key, first wifi). After that, Ansible owns networking.

- `host_vars/<host>` is the single source: wifi networks, static IPs, direct link.
- A base role writes `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` (`network: {config: disabled}`, cloud-init's documented switch), only where `/etc/cloud` exists, so cloud-init cannot rewrite network config after bootstrap.
- Ansible changes networking only through `nmcli`. It never edits the `/etc/netplan/90-NM-*.yaml` files, which NetworkManager generates.

**Fallback behavior** (what to expect):

- NetworkManager's `autoconnect-priority` picks among profiles whose network is **in range**. It knows nothing about internet reachability: with home wifi up and the ISP down, the Pi stays on home wifi and does not try the hotspot.
- NetworkManager's docs say autoconnect "never replaces or competes with an already active profile", so a Pi on the hotspot probably stays there when home wifi comes back. Some bug reports say priority is ignored altogether. Test on a real Pi when convenient.
- No switch-back automation for now: AGENTS.md says no abstraction without a current use. The recovery is `nmcli con up <home-profile>` over Tailscale or ethernet.
- **Dispatcher scripts** are the standard NetworkManager hook: executable files in `/etc/NetworkManager/dispatcher.d/`, owned by root and not writable by group or others. NetworkManager runs them with the interface name and an event (`up`, `down`, and others). If switch-back is wanted later, a dispatcher script or a systemd timer that runs `nmcli device wifi rescan` and `nmcli con up` for the preferred profile are the two usual shapes. Both are small, and neither is a ready-made tool: a timer sketch from a search result was untested, so write and test it on the Pi when there is a real need.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, alongside wifi. It is a way in when wifi is gone.
- **Tailscale** works over any connection with internet (hotspots included) while the node key is valid. Keys expire after 180 days by default: **disable key expiry for each server in the admin console**, or a headless Pi locks you out.
- Rules for the `network` role: never change the connection Ansible is using without a fallback; schedule a revert first (`systemd-run --on-active=5m` restoring the old profile) and cancel it once the Pi is confirmed reachable; always `--check --diff` first.

## Tailscale without a reusable auth key

The `artis3n.tailscale.machine` role fails when `tailscale_authkey` is empty unless `tailscale_up_skip: true` is set (read in the installed role's `tasks/main.yml`; with the skip set it does not run `tailscale up`).

- **Hosts joined by hand** (the default here): run `sudo tailscale up` once, open the URL, set `tailscale_up_skip: true` for that host. Ansible still manages Funnel and settings.
- **Hosts with a one-off key:** put the key in that host's vault file and delete it after the first run.
- Never put a key in `group_vars/all`.

## Base roles (phase 2)

Small, each on a standard module:

- SSH authorized keys: `ansible.posix.authorized_key`; passwordless sudo entry for the Ansible user.
- **Ghostty terminfo:** the `ncurses-term` package on pi5 has no `xterm-ghostty`. Copy it from the Mac (`infocmp -x xterm-ghostty`) and compile with `tic -x`.
- **Zellij:** not in Debian trixie's apt (checked on pi5). Use the static musl release, which exists for aarch64 and x86_64 (v0.45.1 today), pinned in `versions.yml` with its sha256 and installed to `/usr/local/bin` with `get_url` and `unarchive`. There is also a `no-web` build without the web client; pick one.
- Wifi: `community.general.nmcli` from `host_vars` (NetworkManager hosts only).
- cloud-init network switch (above).
- Optional overclock (`arm_freq` in `/boot/firmware/config.txt`), off by default, Pi hosts only. Not on the NAS: its limits are IO and network, and an unstable clock risks data.

## Backups per host (phase 3)

The same restic pattern on every host; only the inputs change: what to back up, where, and whether there is an offsite copy. Those move to `host_vars`, not the NAS-only drive roles.

- Pi microSD to a 128GB USB drive: restic backs up files (`/etc`, `/opt`, home), not a bootable image. A bootable clone is a different tool (`rpi-clone`).
- x64 256GB SSD to its 512GB SSD: same pattern.
- A second drive in the same machine covers drive failure, not theft or fire. Only the NAS has an offsite copy.
- Not yet checked: how much of the `backup` role depends on `nas_drives`.

### Offsite backends

restic speaks several backends natively (checked in its docs): S3 and S3-compatible services, **Backblaze B2** (`b2:bucket:path`, though the docs recommend B2's S3 endpoint), **SFTP** (`sftp:user@host:/path`), and others. **rclone is only needed for services restic does not support, such as Google Drive.** So the design follows restic's own documentation, with no layer of ours:

- `restic_cloud_repository` stays the one switch. Its URL scheme picks the backend.
- A new `restic_cloud_env` dictionary holds the credentials as vault references. The role renders it to a `0600` env file that the backup scripts source. The same file feeds the weekly check and the dashboard.

```yaml
# Backblaze B2 over S3
restic_cloud_repository: "s3:s3.us-west-004.backblazeb2.com/my-bucket/nas"
restic_cloud_env:
  AWS_ACCESS_KEY_ID: "{{ vault_cloud_key_id }}"
  AWS_SECRET_ACCESS_KEY: "{{ vault_cloud_key }}"

# SFTP (key in the vault, host key pinned in known_hosts, or the first cron run fails)
restic_cloud_repository: "sftp:backup@host:/srv/restic"

# Google Drive (unchanged)
restic_cloud_repository: "rclone:gdrive-nas:/pi-nas-backups"
```

- **Tested here:** restic accepts `-o rclone.args=...` on a non-rclone repository without error (throwaway local repo), so the existing option does not break other backends; it is just unused.
- The `listremotes` probe and `gdrive-nas` check in the backup role apply only to `rclone:` repositories.
- **A configured repository whose init fails must fail the deploy**, not silently skip as today. A host with no offsite backup is a reliability gap.
- **Google Drive setup:** run `rclone authorize "drive"` on the Mac (where the browser is), put the token in the vault, and have Ansible write `rclone.conf` only when absent (`force: false`), because rclone writes refreshed tokens back and a re-render each deploy would overwrite them. With your own OAuth client, Google expires refresh tokens after 7 days while the app is in "Testing" (reported by rclone users; check Google's docs), so publish it to Production.
- The remote name `gdrive-nas` appears in the vars, the docs and the backup role. The dashboard only receives `restic_cloud_repository`, so it needs no change (checked with grep).

## Ad-hoc app platform (decision pending)

Wanted: a lightweight Coolify-like layer for apps the owner starts by hand, with no database server, easy teardown, arm64 and amd64.

| Candidate | Role | Checked |
|---|---|---|
| Dockge | Compose stack manager (UI) | arm64 and amd64 images. Stacks are plain `compose.yaml` files in `/opt/stacks`, so teardown is removing one container. Stable (1.5.0) dates from March 2025; only `nightly` moves, so pin 1.5.0. No reverse-proxy features |
| caddy-docker-proxy | Reverse proxy from Docker labels | Multi-arch images (arm64, amd64) at 2.13.1. No database. Syntax in [../caddy-reference.md](../caddy-reference.md). **Left as an option** |
| tsdproxy | A tailnet hostname per container | Tailnet-only. arm64 not confirmed on its README. Needs a Tailscale key |
| Portainer + Traefik, Nginx Proxy Manager | Alternatives | Not researched |

**How public access works with cloudflared** (the likely path, since no router port forwarding is needed): cloudflared makes an outbound connection, so nothing is opened on the home router. For ad-hoc apps there are three ways, the first being the least work per app:

1. **One wildcard rule to a proxy:** `*.example.com` → `http://caddy:80` in the tunnel's ingress, plus a wildcard DNS record. Each new app then needs only Caddy labels. Cloudflare's free certificate covers one level (`*.example.com`, not `*.apps.example.com`). Caddy uses `http://` site addresses, since Cloudflare terminates TLS. **Every labeled container becomes public**, so put Cloudflare Access in front or limit the wildcard to a dedicated domain.
2. **One ingress rule per app** in `cloudflared_ingress`, as the NAS does today. Declarative and explicit, but each app means a repo change and a deploy.
3. **Rules in the Cloudflare dashboard** (remotely managed tunnel). No repo change, but not declarative.

Which of the three (or tailnet-only through Tailscale) is open until the first ad-hoc host exists.

## Phases

0. **Migrate the NAS to pi5** (above), on the current structure.
1. **Split groups and vars with no change for the NAS.** Proof: `--list-tasks` for the NAS host is identical before and after, and `just check` passes. Includes the vault assert and `tests/render.yml`.
2. **Base roles** and the second server.
3. **Per-host backups, offsite backends, rclone setup.**
4. **x64 box and the ad-hoc platform** once the candidate is chosen.

Playbooks are never run against any host from here: use `--list-hosts`, `--list-tasks --limit <host>` and `--syntax-check`; the owner runs `--check --diff`.

## Open decisions

- Debian-family-only support (proposed above).
- Which power supply pi5 has; whether the 3.5" drive has its own brick.
- Approval of the three migration fixes.
- The ad-hoc platform and its public-access path.
- Whether the second Pi gets a Tailscale key or joins by hand.
- Zellij build (`no-web` or full).
