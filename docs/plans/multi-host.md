# Multi-host plan (NAS + general servers)

Goal: manage the NAS and other always-on machines from this repo with plain Ansible. The NAS moves from pi4 to pi5; pi4 then becomes a general server. Work is on the branch `multi-host-refactor`; only docs go straight to main.

How it works now is in [ansible/README.md](../../ansible/README.md), [networking.md](../networking.md), [storage.md](../storage.md) and [services.md](../services.md). This file lists what is left.

## Done

- Groups `servers` > `nas`, `servers_general`; settings split into `group_vars/all`, `group_vars/nas`, `host_vars/<host>`; `derived.yml`; render test covers all of them.
- Base roles on every server: sudoers drop-in, Tailscale install (`state: present`, join by hand), zellij, Ghostty terminfo, SSH keys, log rotation, cloud-init network switch, Docker snap check.
- `docker_data_root` with containerd `root` and mount guards (containerd `root` verified on pi5); Gitea runner bind mount.
- Copyparty option renames, `tailscale_funnel` as its own NAS-only role, all versions in `versions.yml`.
- Cloudflared with a remotely managed tunnel (token and ingress through the API); tested on pi5 against a fake API only. Runs on general servers too (own tunnel and `cloudflared_ingress` per host; the deploy fails if two hosts list one hostname).
- rclone Google Drive remote from the vault; a configured cloud repo that fails to initialise fails the deploy.
- Dockge and caddy-docker-proxy roles for `servers_general`.
- `just deploy` and `just preview` take `--limit` and extra flags (`-K`).
- Decided: Debian-family hosts only (`site.yml` asserts it); no Cloudflare Access or wildcard tunnel; offsite backends are Google Drive and SFTP; options are documented in comments, not `meta/argument_specs.yml`; orphan DNS records are reported, never deleted.

## Open work

### Before the cutover

1. In the Cloudflare Zero Trust dashboard, check whether the existing tunnel (`pi-nas-tunnel`) has a migrate-to-remotely-managed option. If it does not, the deploy stops until the tunnel is deleted, and public hostnames are offline until the next deploy repoints the CNAMEs.
2. Test cloudflared against real Cloudflare, and `cloudflared tunnel run --token-file` on the pinned image (`--help`).
3. Run the netplan spike on pi5 ([networking.md](../networking.md#to-do-netplan-spike-on-pi5)). If it passes, the network role renders one netplan file per host. If not, the role stays on `nmcli` and the `"Wired connection 1"` profile name becomes a per-host variable.
4. Join pi5 to Tailscale by hand (`sudo tailscale up`) and disable key expiry for each server in the Tailscale admin console.
5. Run the first deploy on each new host with `-K`.
6. Publish the Google OAuth app to Production, or the Drive refresh token expires after 7 days ([backups.md](../backups.md)).

### Cutover from the Pi 4 to pi5

Drives hold the data: everything under `/mnt/t7` (app data, Immich, Copyparty, Homebridge, Gitea, Crafty) and `/mnt/backup`. Docker's own storage is disposable and images re-pull.

Does not travel with the drives:

| State | What to do |
|---|---|
| Tailscale identity | pi5 is a new node with a new IP and MagicDNS name. Update WebDAV mounts, bookmarks, the inventory and Funnel |
| `autoback`, `obtain-ampere` containers | Outside this repo; they stay on the Pi 4 |

Order:

1. Take fresh service dumps and a local snapshot, and verify them (`restic snapshots`, `restic check`). Avoid the 2 AM and 4 AM cron windows.
2. Stop the stacks cleanly so Postgres shuts down properly.
3. Shut the Pi 4 down and leave its microSD untouched; moving the drives back is the rollback.
4. Move both drives to pi5's blue USB 3 ports.
5. In the inventory move pi5 from `servers_general` to `nas` and pi4 out of `nas`; add `host_vars/pi5/vars.yml` with its `drives` (UUIDs).
6. Run `just preview '' --limit pi5 -K`, then deploy.
7. Verify Immich, Copyparty, Gitea, a backup run and the `/mnt/backup` mount.
8. Keep the Pi 4 off for a week before repurposing it.

Power: pi5's supply gives 1.6A across all USB ports in total. The 500GB HDD has its own brick. The T7 and the later P10 are both bus-powered, so check their combined draw or use a powered hub ([drive-migration.md](./drive-migration.md)).

### After the cutover

- Docker data-root test on pi5 with the real drive: reboot with the drive unplugged; `systemctl is-active docker containerd` must say `inactive` (listed in [storage.md](../storage.md#not-yet-verified)).
- Remove leftover Docker volumes on the Pi 4 or pi5 by hand ([storage.md](../storage.md#leftover-volumes)).
- Hotspot behaviour: whether a Pi on a hotspot returns to home wifi by itself is untested; the recovery is `nmcli con up` ([networking.md](../networking.md)).

### Later

- Repurpose the Pi 4 as a general server, then add the x64 box.
- Check the ARM-only builds (rawpy, Dockerfile ARGs) when the x64 box is added.
- On Ubuntu Server: do not install Docker from the installer's snap; the first run uses `-K`.

## Per-host backups

Built: the `backup` role also runs on `servers_general` hosts. Set `backup_enabled: true` in the host's `host_vars` and give one drive in `drives` the `backup` role. Without `fast`/`primary` roles it backs up the user's home; add paths such as `/opt/stacks` in `restic_local_paths` (files only root can read are skipped). The offsite copy is off unless `backup_cloud_enabled: true` and `restic_cloud_repository` (its own path per host) are set. `backup-status` runs on the NAS only.

Open:
- Move `vault_cf_api_token`, `vault_cf_account_id`, `vault_restic_password` and `vault_rclone_gdrive_token` from `group_vars/nas/vault.yml` to a new `group_vars/all/vault.yml` (copy `vault.yml.example`). Move them, do not copy: a key left in `nas/vault.yml` wins.
- Test a general host's backup on pi5 with a real drive: `just preview backup --limit pi5`, then deploy.
- Pi microSD to a USB drive: restic backs up files, not a bootable image. A bootable clone needs another tool (`rpi-clone`).
- A second drive in the same machine covers drive failure, not theft or fire. Only hosts with a cloud repository have an offsite copy.
- Decide the paths for a general server that runs Dockge ([services.md](../services.md#ad-hoc-app-platform)): its stacks may be root- or container-owned, which the ansible user cannot read.

## Public hostnames for ad-hoc apps

Apps on general servers are tailnet-only by default, at `http://<host>:<port>` or through Caddy. To publish one app, set `cloudflared_enabled: true` on the host, add a `hostname` and `service` entry to its `cloudflared_ingress` and deploy (its tunnel is `<hostname>-tunnel`). There is no wildcard to Caddy, because every labeled container would become public the moment it starts.

## Networking decisions still open

- Netplan or `nmcli` for per-host profiles (the spike above settles it). Netplan would apply with `netplan try`, which reverts if the connection is not confirmed. Risks: Imager's `90-NM-*.yaml` files may produce duplicate profiles, and `netplan try` may not roll back under the NetworkManager renderer.
- Pass criteria: after applying an Ansible-written netplan file, `nmcli con show` lists one profile per interface or SSID, and `netplan try` rolls back when not confirmed.
- No multi-backend abstraction either way.

## Docs still to update

- `AGENTS.md`: "the Pi" becomes "any host".
- `docs/services.md`: the direct link section moves to `networking.md`.
