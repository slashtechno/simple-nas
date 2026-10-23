# Service notes

Setup steps for services that need more than `<name>_enabled: true`. Run `just deploy <tag>` from `ansible/` (tag = role name). Settings named `vars.yml` below are in `ansible/group_vars/nas/vars.yml`; per-host ones are in `ansible/host_vars/<host>/vars.yml`. Backups are in [backups.md](./backups.md).

| Service | Role | Section |
|---|---|---|
| Copyparty | `roles/copyparty` | [Accounts and volumes](#copyparty-accounts-and-volumes) |
| pics | `roles/pics`, `roles/github_clone` | [pics](#pics-photo-culling-and-sharing), [Private GitHub repo](#clone-a-private-github-repo) |
| Cloudflare Tunnel | `roles/cloudflared` | [Public hostname](#cloudflare-add-a-public-hostname) |
| Tailscale | `roles/tailscale`, `roles/tailscale_funnel` | [Funnel](#tailscale-funnel) |
| Garage | `roles/garage` | [Garage](#garage-s3) |
| Crafty | `roles/crafty` | [Crafty](#crafty-minecraft-servers) |
| Homebridge | `roles/homebridge` | [Homebridge](#homebridge) |
| Dockge, Caddy | `roles/dockge`, `roles/caddy` | [Ad-hoc app platform](#ad-hoc-app-platform) |
| Direct Ethernet link | `roles/network` | [networking.md](./networking.md#direct-ethernet-link) |

## Copyparty accounts and volumes

- Config: rendered from `roles/copyparty/templates/copyparty.conf.j2` into `copyparty_config_dir`.
- Admin account: `copyparty_user` / `copyparty_pass`. Collaborators: `vault_copyparty_collab_users` in the vault.

Service accounts (for apps that talk to Copyparty): add an entry to `copyparty_service_accounts` in `vars.yml` (user, password variable, volumes as folder plus permissions) and put the password in the vault. `vars.yml.example` has an example.
- Each volume is mounted at `/<folder>` and stored in `copyparty_files_dir/<folder>`, owned by the admin. Those folders then vanish for other accounts that have `/`, such as pocketpi's.
- Leave out `d` unless the app must delete. Without `d` Copyparty also refuses overwrites, so the app can't destroy anything.

`/drives` shows USB drives and cards plugged into the host (`usb_automount_enabled`), read-only unless `usb_automount_writable`. Drives listed in `drives` are never shown. See [storage.md](./storage.md#plugged-in-usb-drives-drives).

`/fast` is a volume on the fast drive (`copyparty_fast_dir`, default `<fast_drive>/fast`) for SSD-speed working space. It exists only when the fast and primary roles are on different drives (`copyparty_fast_enabled`, default `fast_drive != primary_drive`). `/` stays the bulk volume. A `fast/` folder inside `files/` is hidden once the volume exists.

To change anything else, edit `copyparty.conf.j2` or the variables, then `just deploy copyparty`. Image versions are in `ansible/group_vars/all/versions.yml` (see "Update service images" in [ansible/README.md](../ansible/README.md)).

## Clone a private GitHub repo

- Token: `vault_github_read_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how to create it).
- A role calls `roles/github_clone` with `repo` and `dest`. The token is passed to git through its environment, so it is not stored in `.git/config`.
- If the token expires, the clone step fails. Make a new one and update the vault with `ansible-vault edit`.

## pics: photo culling and sharing

Opt-in (`pics_enabled: true`). The `pics` role clones the private `lab` repo (`pics_repo`), builds the image on the Pi (several minutes the first time; later runs rebuild only when the repo's commit changed) and runs it on `nas-services`. It uses the `photos` service account in `copyparty_service_accounts`.

1. In `vars.yml`, copy the `pics_*` entries and the `photos.example.com` entry in `cloudflared_ingress` from `vars.yml.example`. Two ports:
   - Owner app (cull UI, password-gated): `pics_port` (default 8100), the only published port. LAN: `http://<pi>:<pics_port>`; tailnet: `http://<pi-tailscale-ip>:<pics_port>`.
   - Guest surface (share pages, portfolio, no owner routes): `pics_public_port` (8001), inside Docker only. The tunnel points at `http://pics:<pics_public_port>`, so no `path` rule is needed.
2. In the vault add `vault_pics_password` (12+ characters) and `vault_pics_secret_key` (`openssl rand -base64 48`). Use values without single quotes.
3. `just deploy copyparty,pics,cloudflared`. `copyparty` creates the `photos` account and its two volumes first.

The database is in `pics_data_dir`, covered by the daily backup; the app also writes its own daily snapshots there. `teardown.yml --tags pics` keeps that data unless `-e remove_data=true`.

## Cloudflare: add a public hostname

In `vars.yml`:

```yaml
cloudflared_ingress:
  - hostname: newservice.example.com
    service: "http://newservice:8080"
```

Then `just deploy cloudflared`.

- Each hostname's DNS record is created in the zone from `cf_zones` (domain: zone ID) whose domain appears in the hostname. A hostname on a new domain needs that domain in `cf_zones`, and the API token needs DNS:Edit on that zone.
- The deploy fails before calling Cloudflare if a rule has anything besides `hostname` and `service` (no `path:`), or if its hostname matches no domain or more than one in `cf_zones`.
- Hostnames not listed get a 404.
- An existing DNS record is replaced only if it points at a Cloudflare tunnel. A record of any other kind stops the deploy with a message naming it; delete it in the Cloudflare dashboard if unused.
- A record pointing at this tunnel for a hostname you removed from the list is reported and left for you to delete.
- The tunnel is remotely managed: the deploy sets its rules at Cloudflare through the API (from your machine), and the NAS holds only a tunnel token (`/opt/nas/cloudflared/token`). If no tunnel named `cf_tunnel_name` exists, the deploy creates it.
- If a tunnel with that name exists but is "locally managed", the deploy stops. Use its migrate option in the dashboard (Zero Trust, Networks, Tunnels), or delete the tunnel (public hostnames are offline until the next deploy).
- A leftover `*.json` credentials file in `/opt/nas/cloudflared/` is not used and not touched; delete it by hand.

## Tailscale Funnel

Set `tailscale_funnel_enabled: true` in `vars.yml` to expose Copyparty (port `tailscale_funnel_port`, default 3923) at your ts.net hostname, then `just deploy tailscale`.

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret`, `vault_garage_admin_token`, `vault_garage_webui_user` and `vault_garage_webui_pass`, then `just deploy garage,cloudflared`.

- The first deploy (empty `<garage_data_dir>/meta`) adds `--single-node` to the compose command to set up the cluster layout; later deploys leave it out.
- Open `https://garage.example.com` (the `garage-webui` entry in `cloudflared_ingress`), log in with the web UI credentials, and create buckets and access keys there.
- Apps connect with endpoint `https://s3.example.com`, region `garage`, and the key pair from the web UI.

## Crafty (Minecraft servers)

Opt-in (`crafty_enabled: true`). One container runs every server. All data is under `crafty_data_dir` (`servers/ backups/ logs/ config/ import/`).

- Panel: `https://<pi-ip>:28443` (`crafty_panel_port`, self-signed certificate). The first admin password is in `docker logs crafty` or `<crafty_data_dir>/config/default-creds.txt`. Change it in the panel, then delete that file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575); set it when creating the server.
- `crafty_memory_limit` (default 3g) caps all servers combined. On a 4 GB Pi it competes with Immich.
- Not behind Cloudflare Tunnel. Players join over the LAN, a router port-forward of the game port, or Tailscale. The panel and game ports are published on all interfaces, so don't forward the panel port.
- The live `servers/` directory is in the daily restic backup; Crafty's own `backups/` archives are not (see [backups.md](./backups.md)).

## Homebridge

Runs with `network_mode: host` (HomeKit discovery needs it), so it is not on `nas-services` and not in `cloudflared_ingress`.

- Remote Apple Home access needs a HomeKit hub (Apple TV or HomePod) on your LAN. Tailscale does not replace it: off home Wi-Fi the Home app shows the bridge offline even with Tailscale connected.
- The admin UI is reachable over Tailscale at `http://<pi-tailscale-ip>:8581` (plain HTTP).

The role only deploys the container; the image creates `config.json` and `auth.json` on first start. Log in with `admin`/`admin` and change the password at once. The HomeKit PIN and plugins are set in the UI and persist across deploys.

## Ad-hoc app platform

For general servers (the `servers_general` group), not the NAS.

**Dockge** (`dockge_enabled`, default on) is a web UI at `http://<host>:<dockge_port>` (5001) over `compose.yaml` stacks in `dockge_stacks_dir` (`/opt/stacks`). Create the account on first visit. Ansible deploys Dockge only; the stacks are yours and stay when Dockge is removed. A stack keeps its state in bind mounts (see [storage.md](./storage.md#dockges-storage-rule)), not Docker volumes, so deleting a stack is deleting its directory.

**Caddy** (`caddy_enabled`, default off) gives apps names from container labels; syntax in [caddy-reference.md](./caddy-reference.md). Without it, apps are reachable over Tailscale at `http://<host>:<port>`. Stacks that want a name join the `nas-services` network.

No public access on these hosts: cloudflared runs only on the NAS, so reach apps over Tailscale. Removal: `ansible-playbook teardown.yml --tags dockge,caddy --limit <host>`.

Both mount the Docker socket: anyone who can reach their UI or set a label controls Docker on that host.

Nothing backs up `/opt/stacks` or `dockge_data_dir` yet; per-host backups are planned in [plans/multi-host.md](./plans/multi-host.md#per-host-backups).
