# Multi-host: NAS on pi5, pi4 as a general server

Goal: manage the NAS and other always-on machines from this repo with plain Ansible. The NAS moves from pi4 to pi5; pi4 then becomes a general server.

How things work now is in [ansible/README.md](../../ansible/README.md), [storage.md](../storage.md), [networking.md](../networking.md) and [services.md](../services.md). This file is the runbook for the move and the list of what is left.

## What is built

- Groups `servers` > `nas`, `servers_general`; settings in `group_vars/all`, `group_vars/nas` and `host_vars/<host>`; the render test covers all of them.
- Every server: sudoers drop-in, Tailscale install (joined by hand), Docker with `docker_data_root` and mount guards, drive mounts, direct Ethernet link, log rotation.
- NAS: Immich, Copyparty, Gitea, Homebridge, pics, Garage, Crafty, Cloudflare Tunnel, Tailscale Funnel, backups, backup-status, ntfy.
- General servers: Dockge, Caddy, Cloudflare Tunnel, backups.
- Restic backups per host, local daily and Google Drive or SFTP weekly; failures go to the system log and optionally ntfy.
- Decisions: Debian-family hosts only (`site.yml` asserts it); no Cloudflare Access or wildcard tunnel; options are documented in comments, not `meta/argument_specs.yml`; orphan DNS records are reported, never deleted; Tailscale is joined by hand, so no auth key is stored.

Not built: x64 support (see [Later](#later)).

## Cutover from the Pi 4 to pi5

Drives hold the data: everything under `/mnt/t7` (app data, Immich, Copyparty, Homebridge, Gitea, Crafty) and `/mnt/backup`. Docker's own storage is disposable and images re-pull. Rollback: move the drives back to the Pi 4 and run `just deploy '' --limit pi4`.

Does not travel with the drives:

| State | What to do |
|---|---|
| Tailscale identity | pi5 is a new node. Give it the Pi 4's name (cutover steps 3 and 8, [Hostnames](#hostnames)) so WebDAV mounts and bookmarks keep working; its IP still changes, so update the inventory |
| Tailscale Funnel | Reset on the Pi 4 (step 4); the deploy turns it on for pi5 when `tailscale_funnel_enabled` is true |
| `autoback`, `obtain-ampere` containers | Outside this repo; they stay on the Pi 4 |

### Before: nothing on the hosts changes

1. **Cloudflare tunnel.** In the Cloudflare Zero Trust dashboard, check whether `pi-nas-tunnel` has a migrate-to-remotely-managed option. If it does not, the deploy stops until the tunnel is deleted, and public hostnames are offline until the next deploy repoints the CNAMEs. This is the only step that can take public sites down; do it first.
2. **Vault.** Move (do not copy: a key left in `nas/vault.yml` wins) `vault_cf_api_token`, `vault_cf_account_id`, `vault_restic_password` and `vault_rclone_gdrive_token` from `group_vars/nas/vault.yml` to a new `group_vars/all/vault.yml` (copy `vault.yml.example`), then `ansible-vault encrypt` it with the same password.
3. **Google OAuth.** Publish the OAuth app to Production, or the Drive refresh token expires after 7 days ([backups.md](../backups.md)).
4. **Preview the Pi 4.** `just preview '' --limit pi4`. Expected changes: `/drives` loses the backup, fast and primary drives; `direct-link.conf` loses the netmask and dnsmasq restarts; the Homebridge compose file changes; Garage, Caddy and the web UI move to new versions; USB automount turns on; the three cron jobs now end in `alert.sh`, which is a new file; the backup role creates its directories.
5. **ntfy (optional).** Failure alerts to your phone: [services.md](../services.md#ntfy-failure-alerts).

### Cutover

1. Take fresh service dumps and a local snapshot, and check them (`restic snapshots`; `restic check` stays manual). Avoid the 2 AM and 4 AM cron windows.
2. **pi5 leaves the general-server role.** `ansible-playbook teardown.yml --tags dockge,caddy,cloudflared --limit pi5 --ask-vault-pass`. Joining `nas` does not remove them.
3. **Free the Pi 4's name.** On the Pi 4: `sudo tailscale set --hostname=pi4`, and set the OS hostname ([Hostnames](#hostnames)).
4. **Stop the Pi 4's services** so nothing restarts when it boots without drives: `ansible-playbook teardown.yml --limit pi4 --ask-vault-pass` (stops every service, removes the cron jobs, keeps all data). Then on the Pi 4 run `sudo tailscale funnel reset` and remove the T7 and backup lines from `/etc/fstab`.
5. Shut the Pi 4 down and leave its microSD untouched.
6. Move both drives to pi5's blue USB 3 ports. Power: pi5's supply gives 1.6A across all USB ports in total. The 500GB HDD has its own brick; the T7 and the later P10 are bus-powered, so check their combined draw or use a powered hub ([drive-migration.md](./drive-migration.md)).
7. **Inventory** (`ansible/inventory/hosts.yml`): move `pi5` under `nas` and `pi4` under `servers_general`. Then `mkdir ansible/host_vars/pi5` and move the `drives:` block from `host_vars/pi4/vars.yml` to `host_vars/pi5/vars.yml` (same UUIDs); move the direct-link settings too if pi5 should have the link. Do not create pi5's file earlier: its next deploy would try to mount drives that are not attached.
8. **Name pi5 like the old NAS.** If it is not logged in to Tailscale, run `sudo tailscale up`. Then `sudo tailscale set --hostname=pinas` and set the OS hostname ([Hostnames](#hostnames)). Disable key expiry for it in the Tailscale admin console.
9. `just preview '' --limit pi5 -K`, then `just deploy '' --limit pi5 -K`.
10. **Check:** Immich, Copyparty, Gitea, the public hostnames and Funnel; a backup run (`bash /opt/services/scripts/backup-restic-local.sh`, then `restic snapshots`); `/mnt/backup` is mounted. Optionally reboot with a drive unplugged to test the Docker mount guard ([storage.md](../storage.md#check-after-a-reboot-with-the-drive-unplugged)).
11. **Clean up:** delete the stale offline Gitea runner ([storage.md](../storage.md#gitea-runner-registration)), the old tunnel `*.json` credentials in `/opt/services/cloudflared/`, and the old `pinas` node if it still shows in the Tailscale admin console.
12. Keep the Pi 4 off for a week.

### The Pi 4 as a general server

1. Boot it. It is already in `servers_general`; set the hostname and Tailscale name if not done ([Hostnames](#hostnames)).
2. Write `ansible/host_vars/pi4/vars.yml` with a `drives:` block that claims `fast` ([storage.md](../storage.md#examples)). To back it up, add `backup_enabled: true` and a drive with the `backup` role ([backups.md](../backups.md)).
3. `just preview '' --limit pi4 -K`, then `just deploy '' --limit pi4 -K`. Dockge is at `http://<host>:5001`.
4. Remove leftover Docker volumes by hand ([storage.md](../storage.md#leftover-volumes)).
5. Optional: Caddy, a public hostname ([below](#public-hostnames-for-ad-hoc-apps)), `docker_data_root` on a drive ([storage.md](../storage.md#dockers-own-storage)).

### Hostnames

The inventory name (`pi4`) is only a label in Ansible's output; the host's own hostname is separate and changes nothing in Ansible. It matters in three places: the Tailscale name (MagicDNS, WebDAV mounts, the Funnel URL), the shell prompt, and restic, which groups snapshots by hostname and paths. A repo that moves to pi5 keeps its snapshot groups only if pi5's hostname equals the old one (`pinas`); otherwise the old snapshots stay as a separate group until `restic forget --host pinas ...`.

To rename a host:

```bash
sudo hostnamectl set-hostname <name>
sudo sed -i 's/^127.0.1.1.*/127.0.1.1 <name>/' /etc/hosts
sudo tailscale set --hostname=<name>
```

If Tailscale shows the name with a `-1` suffix, the old node still holds it: rename or delete the old node in the admin console first. On Ubuntu, cloud-init can set the hostname back at boot; if it does, put `preserve_hostname: true` in `/etc/cloud/cloud.cfg.d/99-hostname.cfg`.

## Per-host backups

The `backup` role also runs on `servers_general` hosts. Set `backup_enabled: true` in the host's `host_vars` and give a drive in `drives` the `backup` role. It backs up the host's `fast` drive, where Dockge's stacks and data live. The offsite copy is off unless `backup_cloud_enabled: true` and `restic_cloud_repository` (its own path per host) are set. `backup-status` runs on the NAS only.

Limits:
- Files only root or a container can read are skipped, because the backup runs as the ansible user ([backups.md](../backups.md)).
- restic backs up files, not a bootable image. A bootable microSD clone needs another tool (`rpi-clone`).
- A second drive in the same machine covers drive failure, not theft or fire. Only hosts with a cloud repository have an offsite copy.

## Public hostnames for ad-hoc apps

Apps on general servers are tailnet-only by default, at `http://<host>:<port>` or through Caddy. To publish one app, set `cloudflared_enabled: true` on the host, add a `hostname` and `service` entry to its `cloudflared_ingress` and deploy (its tunnel is `<hostname>-tunnel`). There is no wildcard to Caddy, because every labeled container would become public the moment it starts.

## Later

- Add the x64 box as a general server. Check the ARM-only builds (rawpy, Dockerfile ARGs) first.
- On Ubuntu Server: do not install Docker from the installer's snap; the first run uses `-K`.
