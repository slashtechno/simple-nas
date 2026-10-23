# Multi-host plan (NAS + general servers)

Status: planned, nothing implemented. Phase 1 needs the owner's approval before any code moves.

## Goal

Manage the NAS and other always-on machines (a second Pi, later an x64 desktop) from this one repo, declaratively, with plain Ansible. Reliability and the owner maintaining it without an AI agent are equal top priorities (AGENTS.md).

- **NAS** (Pi 5 probably, Pi 4 today): fully Ansible-managed. Drives, Immich, Copyparty, backups.
- **General server** (the other Pi, the x64 box): Ansible sets up the base (SSH, Tailscale, networking, backup of the machine itself, Docker, a reverse proxy and a container manager). The owner then runs apps ad-hoc. This fits the existing rule: Ansible owns what it deploys, the owner owns the rest.

## Ansible shape

Only standard Ansible features, no wrapper of our own.

- **Inventory:** hosts are named after hardware (`pi4`, `pi5`, later `desktop`). Groups are named after function: `nas`, `servers_general`, both inside a parent group `servers`. Swapping which Pi is the NAS later is a one-line move in the inventory.
- **Settings:**
  - `group_vars/all/`: timezone, SSH public keys, base flags.
  - `group_vars/nas/`: drives, services, restic (stays where it is).
  - `host_vars/<host>/`: wifi, direct link, overclock, per-host `_enabled` overrides, per-host secrets.
- **`site.yml`:** one play for `hosts: servers` (common, tailscale, network, base roles) and one for `hosts: nas` (storage, services, backup). The existing `<name>_enabled` flags still do per-service opt-in.
- **Access:** set `ansible_host` to the Tailscale (MagicDNS) name, so Ansible reaches a Pi on any network. `pi5.local` stops resolving on a phone hotspot.

## Things that break if we just split the files

| Item | Problem | Fix |
|---|---|---|
| `pre_tasks` vault assert | Checks `vault_restic_password`, which only the NAS has | Move into the `nas` play |
| `tests/render.yml` | Renders templates with the example vars and diffs `vars.yml` against `vars.yml.example` | Update it for `all`/`nas`/`host_vars`; part of phase 1, not an afterthought |
| `network` role | Hard-codes the default eth0 profile `"Wired connection 1"`; pi5's is `netplan-eth0`. With `nmcli state: present`, pi5 would get a new unused profile and the real one would race the static direct link | Make the default profile name a per-host var |
| Sudo | pi5 asks for a sudo password, so Ansible's `become` fails | First run with `-K`; a base role then installs a `/etc/sudoers.d/` entry |

## Networking (one source of truth)

**cloud-init vs Ansible.** cloud-init (Raspberry Pi Imager) configures a machine once at first boot. Ansible re-applies the repo's state each run. Use Imager only to make the Pi reachable (user, hostname, SSH key, first wifi). After that, Ansible owns it.

- `host_vars/<host>` is the single source: wifi networks, static IPs, direct link.
- A base role writes `/etc/cloud/cloud.cfg.d/99-disable-network-config.cfg` containing `network: {config: disabled}` (cloud-init's documented switch), so cloud-init can never rewrite network config afterward.
- Ansible changes networking only through `nmcli`. It never edits the `/etc/netplan/90-NM-*.yaml` files, which NetworkManager generates.

**Fallback behavior** (what to expect, not a guarantee):

- NetworkManager's `autoconnect-priority` picks among profiles whose network is **in range**. It knows nothing about internet reachability: if home wifi is up and the ISP is down, the Pi stays on home wifi and does not try the hotspot.
- Priority only matters when choosing a profile to connect. NetworkManager's docs say autoconnect "never replaces or competes with an already active profile", so a Pi on the hotspot will probably not move back to home wifi when it reappears. Reports of priority being ignored exist too. **To verify on a real Pi before relying on it**, and if it stays on the hotspot, add a small NetworkManager dispatcher script or timer that retries the preferred profile.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, in parallel with wifi. It is a way in when wifi is gone, not a last step in a chain.
- **Tailscale** works over any connection with internet, including a hotspot, but only while the node key is valid. Keys expire after 180 days by default. **Disable key expiry for each server in the Tailscale admin console**, or a headless Pi gets locked out.
- Safety rules for the `network` role: never change the connection Ansible is using without a fallback; schedule a revert first (`systemd-run --on-active=5m` restoring the old profile) and cancel it once the Pi is confirmed reachable; always `--check --diff` first.

## Tailscale without a reusable auth key

The `artis3n.tailscale.machine` role fails when `tailscale_authkey` is empty, unless `tailscale_up_skip: true` is set (verified in the installed role's `tasks/main.yml`; with the skip set it does not run `tailscale up`). So:

- **Hosts joined by hand:** run `sudo tailscale up` once and open the URL. Set `tailscale_up_skip: true` in that host's `host_vars`. Ansible still manages Funnel and settings.
- **Hosts with a one-off key:** put the key in that host's vault file and delete it after the first run.
- Do not put a key in `group_vars/all`.

## Base roles (phase 2)

Small, each built on a standard module:

- SSH authorized keys: `ansible.posix.authorized_key`.
- Passwordless sudo entry for the Ansible user.
- Ghostty terminfo: pi5's `ncurses-term` has no `xterm-ghostty`, so install it from the Mac (`infocmp -x xterm-ghostty`, then `tic -x`).
- Wifi: `community.general.nmcli`, from `host_vars`.
- cloud-init network switch (above).
- Optional overclock (`arm_freq` in `/boot/firmware/config.txt`), off by default. Not on the NAS: its limits are IO and network, and an unstable clock risks data.

## Backups per host (phase 3)

The same restic pattern on every host; only the inputs differ: what to back up, where, whether there is an offsite copy. Those move to `host_vars`, not the NAS-only drive roles.

- Pi microSD to a 128GB USB drive: restic backs up files (`/etc`, `/opt`, home), not a bootable image. A bootable clone is a different tool (`rpi-clone`).
- x64 256GB SSD to its 512GB SSD: same pattern.
- A second drive in the same machine covers drive failure, not theft or fire. Only the NAS has an offsite copy.
- Not yet checked: how much of the `backup` role depends on `nas_drives`. Read it before estimating.

### rclone remote UX

Today `rclone config` is run by hand on the Pi (browser-less OAuth), and a missing `gdrive-nas` remote silently skips cloud init. Options, owner to pick:

1. **Authorize on the Mac:** `rclone authorize "drive"` runs where the browser is; paste the token into the Pi.
2. **Remote in the vault:** Ansible writes `rclone.conf` only when absent (`force: false`), because rclone writes refreshed tokens back and re-rendering each deploy would clobber them. A rebuilt host then needs no re-auth.
3. **Own OAuth client in Production:** with an external app in "Testing" status, Google expires refresh tokens after 7 days (reported by rclone users; check Google's own docs). Publish the app to Production.
4. **Fail loudly:** show a warning at the end of the deploy when the remote is missing, since a host with no offsite backup is a reliability gap.
5. **Per-host remote name and path:** `gdrive-nas` is hard-coded in vars, docs and the backup-status dashboard (`app.py`, `index.html`), so generalizing touches the dashboard too.

## Ad-hoc app platform (decision pending)

Wanted: a lightweight Coolify-like layer that handles the reverse proxy, with no heavy database, easy teardown, runs on arm64. Not Coolify or Dokploy. Candidates (the facts below are from each project's README; arm64 for two of them is unconfirmed):

| Candidate | Role | Notes |
|---|---|---|
| Dockge | Compose stack manager (UI) | arm64 yes. Stacks are plain `compose.yaml` files on disk (`/opt/stacks`), so teardown means removing one container. No reverse-proxy features |
| caddy-docker-proxy | Reverse proxy from Docker labels | Labels become Caddy routes, automatic HTTPS, no database. arm64 not confirmed on its README (arm32v6 mentioned) |
| tsdproxy | Gives each container its own tailnet hostname and HTTPS | Tailnet-only access. arm64 not confirmed on its README. Needs a Tailscale key or OAuth for headless use |
| Portainer + Traefik, Nginx Proxy Manager | Alternatives | Not researched yet |

Leading combination: Dockge + caddy-docker-proxy. Access path (tailnet only, LAN, or public via cloudflared) decides between Caddy and tsdproxy.

## Phases

1. **Split groups and vars with no change for the NAS.** Proof: `--list-tasks` for the NAS host is identical before and after, and `just check` passes. Includes the vault assert, `tests/render.yml` and the network-profile var.
2. **Base roles and pi5 / the second server.**
3. **Per-host backups, rclone UX, and the x64 box.** The x64 risks are `nmcli` and Pi-specific assumptions and ARM-only builds (rawpy, Dockerfile ARGs).
4. **Ad-hoc platform** once the candidate is chosen.

Playbooks are never run against any host from here: use `--list-hosts`, `--list-tasks --limit <host>` and `--syntax-check`; the owner runs `--check --diff`.

## Open decisions

- Which Pi is the NAS (probably pi5).
- The ad-hoc platform.
- Which rclone options (1–5).
- Whether the second Pi gets a Tailscale key or joins by hand.
