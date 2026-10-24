# Runbook: NAS on pi5, pi4 as a general server

One-time steps to move the NAS from pi4 to pi5 and reuse pi4 as a general server. Delete this file when both are done.

Everything runs from `ansible/`. Reference docs: [ansible/README.md](../../ansible/README.md), [storage.md](../storage.md), [backups.md](../backups.md), [networking.md](../networking.md), [services.md](../services.md). Never run a playbook without first running it with `--check --diff` (`just preview`) and reading the result.

## How a host is set up

Hosts sit directly under `servers` in `ansible/inventory/hosts.yml`. There are no other groups.

A host needs two files:

- `ansible/host_vars/<host>/vars.yml`: `drives`, the `<name>_enabled` flags, `backup_local_enabled` / `backup_cloud_enabled`, `restic_cloud_repository`, and the cloudflared settings (`cloudflared_enabled`, `cloudflared_tunnel_name`, `cloudflared_ingress`). Start from `host_vars/vars.yml.example`; `host_vars/pi4/vars.yml` is a working example.
- `ansible/host_vars/<host>/vault.yml`: copy `host_vars/vault.yml.example`, keep the keys the host's services use, then `ansible-vault encrypt host_vars/<host>/vault.yml` with the same password as the other vault files.

A host with no flags set deploys only the base roles. Secrets every host shares are in `group_vars/all/vault.yml`, under these names: `vault_cloudflared_api_token`, `vault_cloudflared_account_id`, `vault_restic_password`, `vault_rclone_gdrive_token`. A key in a host vault wins over the same key in `group_vars/all/vault.yml`.

## Cutover from the Pi 4 to pi5

Drives hold the data: everything under `/mnt/t7` (app data, Immich, Copyparty, Homebridge, Gitea, Crafty) and `/mnt/backup`. Docker's own storage is disposable and images re-pull.

Rollback, in this order: `ansible-playbook teardown.yml --limit pi5 --ask-vault-pass`; set `cloudflared_enabled: false` and `backup_cloud_enabled: false` in `host_vars/pi5/vars.yml` and the Pi 4's values back in `host_vars/pi4/vars.yml`; run `sudo tailscale set --hostname=pinas` on the Pi 4 and give pi5 another name; move the drives back; `just deploy '' --limit pi4`. The storage role writes the fstab lines again.

Does not travel with the drives:

| State | What to do |
|---|---|
| Tailscale identity | pi5 is a new node. Give it the Pi 4's name (cutover steps 4 and 9, [Hostnames](#hostnames)) so WebDAV mounts and bookmarks keep working. Its IP differs, so update `ansible_host` in the inventory |
| Tailscale Funnel | Reset on the Pi 4 (step 5); the deploy turns it on for pi5 when `tailscale_funnel_enabled` is true |
| `autoback`, `obtain-ampere` containers | Outside this repo; they stay on the Pi 4 |

### Before: nothing on the hosts changes

1. **Cloudflare tunnel.** In the Cloudflare Zero Trust dashboard, check whether `pi-nas-tunnel` has a migrate-to-remotely-managed option. If it does not, the deploy stops until the tunnel is deleted, and public hostnames are offline until the next deploy repoints the CNAMEs. This is the only step that can take public sites down; do it first.
2. **Vault keys.** In `group_vars/all/vault.yml`, the Cloudflare keys are `vault_cloudflared_api_token` and `vault_cloudflared_account_id`. Rename them if they still have the old names `vault_cf_api_token` and `vault_cf_account_id`. Check that no encrypted vault file still holds the old names.
3. **Google OAuth.** Publish the OAuth app to Production, or the Drive refresh token expires after 7 days ([backups.md](../backups.md)).
4. **Do not create `host_vars/pi5/` yet.** With a `drives:` block in place, any deploy to pi5 tries to mount drives that are not attached. Cutover step 8 creates it.
5. **ntfy (optional).** Failure alerts to your phone: [services.md](../services.md#ntfy-failure-alerts).

### Cutover

1. Take fresh service dumps and a local snapshot, and check them (`restic snapshots`; `restic check` stays manual). Avoid the 2 AM and 4 AM cron windows.
2. **Rename the on-host names.** Every host that was deployed before the `nas` prefix was dropped runs `ansible/migrate-old-names.sh` once, as root on the host, with the ansible user as argument. The script is gitignored; if it is missing, restore it from your copy. It stops the compose projects, removes the old cron jobs, and renames:
   - `/opt/nas` to `/opt/services`
   - the Docker network `nas-services` to `services`
   - the cron jobs `nas-backup-*` to `backup-local`, `backup-cloud` and `restic-check`
   - `/var/lib/nas-backup` to `/var/lib/backup-work`
   - the unit `nas-drive-remount` to `drive-remount`

   Run it on the Pi 4 now (`scp ansible/migrate-old-names.sh pi4:/tmp/ && ssh -t pi4 sudo bash /tmp/migrate-old-names.sh <ansible-user>`). Run it on pi5 too if it was ever deployed.
3. **pi5 drops its old services.** If pi5 ran Dockge, Caddy or cloudflared: `ansible-playbook teardown.yml --tags dockge,caddy,cloudflared --limit pi5 --ask-vault-pass`.
4. **Free the Pi 4's name.** On the Pi 4: `sudo tailscale set --hostname=pi4`, and set the OS hostname ([Hostnames](#hostnames)).
5. **Stop the Pi 4's services** so nothing restarts when it boots without drives: `ansible-playbook teardown.yml --limit pi4 --ask-vault-pass` (`--limit` is required; teardown stops every service, removes the cron jobs, keeps all data). Then on the Pi 4 run `sudo tailscale funnel reset` and remove the T7 and backup lines from `/etc/fstab`.
6. Shut the Pi 4 down and leave its microSD untouched.
7. Move both drives to pi5's blue USB 3 ports. Power: pi5's supply gives 1.6A across all USB ports in total. The 500GB HDD has its own brick; the T7 and the later P10 are bus-powered, so check their combined draw or use a powered hub ([drive-migration.md](./drive-migration.md)).
8. **Create pi5's files.** In `host_vars/pi4/vars.yml`, set `cloudflared_enabled: false` and `backup_cloud_enabled: false` (a hostname belongs to one host, and two hosts must not back up into one repository). In `ansible/inventory/hosts.yml`, set pi5's `ansible_host`. Create `host_vars/pi5/vars.yml`, with the `drives:` block from `host_vars/pi4/vars.yml` (same UUIDs and mounts), the service flags the NAS runs, `backup_local_enabled: true`, `backup_cloud_enabled: true`, `restic_cloud_repository` (the NAS's existing path: pi5 takes over the NAS's offsite repository, which is safe only because the Pi 4 was shut down in step 6; two hosts must never run a cloud backup into one repository), `cloudflared_enabled: true`, `cloudflared_tunnel_name: pi-nas-tunnel`, `cloudflared_ingress`, and the direct-link settings if pi5 should have the link. Create `host_vars/pi5/vault.yml` from `host_vars/vault.yml.example` (the same secrets the Pi 4 uses), then encrypt it.
9. **Name pi5 like the old NAS.** If it is not logged in to Tailscale, run `sudo tailscale up`. Then `sudo tailscale set --hostname=pinas` and set the OS hostname ([Hostnames](#hostnames)). Disable key expiry for it in the Tailscale admin console.
10. `just preview '' --limit pi5 -K`, read the whole diff, then `just deploy '' --limit pi5 -K`.
11. **Check:** Immich, Copyparty, Gitea, the public hostnames and Funnel; a backup run (`bash /opt/services/scripts/backup-restic-local.sh`, then `restic snapshots`); `/mnt/backup` is mounted. Optionally reboot with a drive unplugged to test the Docker mount guard ([storage.md](../storage.md#check-after-a-reboot-with-the-drive-unplugged)).
12. **Prune the old snapshot group.** The first offsite backup under `/opt/services` starts a new snapshot group for that path. When `restic snapshots` on the cloud repo shows it, list the groups with `restic -r <repo> snapshots --group-by host,paths`, then remove the old group's snapshots by hand with `restic -r <repo> forget <snapshot-id> --prune` (the same as in [backups.md](../backups.md)).
13. **Clean up:** delete the stale offline Gitea runner ([storage.md](../storage.md#gitea-runner-registration)), the old tunnel `*.json` credentials in `/opt/services/cloudflared/`, and the old `pinas` node if it still shows in the Tailscale admin console.
14. Keep the Pi 4 off for a week.

### The Pi 4 as a general server

1. Boot it. Set the hostname and Tailscale name if not done ([Hostnames](#hostnames)).
2. Rewrite `ansible/host_vars/pi4/vars.yml`: a `drives:` block that claims `fast` ([storage.md](../storage.md#examples)), and the services it runs (`dockge_enabled: true`, optionally `caddy_enabled: true`). To back it up, add a drive with the `backup` role and `backup_local_enabled: true`; for an offsite copy also `backup_cloud_enabled: true` and its own `restic_cloud_repository` ([backups.md](../backups.md)). Check the `host_vars/pi4/vault.yml` keys against the services it runs.
3. If the Pi 4 was not migrated in cutover step 2, run `ansible/migrate-old-names.sh` on it now.
4. `just preview '' --limit pi4 -K`, then `just deploy '' --limit pi4 -K`. Dockge is at `http://<host>:5001`.
5. Remove leftover Docker volumes by hand ([storage.md](../storage.md#leftover-volumes)).
6. Optional: Caddy, a public hostname ([below](#public-hostnames-for-ad-hoc-apps)), `docker_data_root` on a drive ([storage.md](../storage.md#dockers-own-storage)).

### Hostnames

The inventory name (`pi4`) is only a label in Ansible's output; the host's own hostname is separate and changes nothing in Ansible. It matters in three places: the Tailscale name (MagicDNS, WebDAV mounts, the Funnel URL), the shell prompt, and restic, which groups snapshots by hostname and paths. A repo that moves to pi5 keeps its snapshot groups only if pi5's hostname equals the old one (`pinas`); otherwise the old snapshots stay as a separate group until you remove them by hand (step 12). The name move is symmetrical: the Pi 4 must give up `pinas` (and the rollback gives it back) before another host takes it.

To rename a host:

```bash
sudo hostnamectl set-hostname <name>
sudo sed -i 's/^127.0.1.1.*/127.0.1.1 <name>/' /etc/hosts
sudo tailscale set --hostname=<name>
```

If Tailscale shows the name with a `-1` suffix, the old node still holds it: rename or delete the old node in the admin console first. On Ubuntu, cloud-init can set the hostname back at boot; if it does, put `preserve_hostname: true` in `/etc/cloud/cloud.cfg.d/99-hostname.cfg`.

## Per-host backups

Any host can run the `backup` role. Set `backup_local_enabled: true` in the host's `host_vars` and give a drive in `drives` the `backup` role. The offsite copy needs `backup_cloud_enabled: true` and a `restic_cloud_repository` with its own path per host. `backup_status_enabled` needs a local backup. Details and limits: [backups.md](../backups.md).

## Public hostnames for ad-hoc apps

Apps on general servers are tailnet-only by default, at `http://<host>:<port>` or through Caddy. To publish one app, set `cloudflared_enabled: true` on the host, add a `hostname` and `service` entry to its `cloudflared_ingress` and deploy (its tunnel is `<hostname>-tunnel`). There is no wildcard to Caddy, because every labeled container would become public the moment it starts.

## Not done

- x64 box as a general server. Check the ARM-only builds (rawpy, Dockerfile ARGs) first.
- On Ubuntu Server: do not install Docker from the installer's snap; the first run uses `-K`.
