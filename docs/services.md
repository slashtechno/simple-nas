# Service notes

Every service is off until a host sets `<name>_enabled: true` in `ansible/host_vars/<host>/vars.yml`. This page lists what each service needs and the setup steps beyond the flag. Run `just deploy <tag>` from `ansible/` (tag = role name). Settings and their defaults are in `ansible/group_vars/all/defaults.yml` and each role's `defaults/main.yml`; file locations are in [ansible/README.md](../ansible/README.md). Backups are in [backups.md](./backups.md).

## Every host

The `common` role runs on every host. It installs base packages (curl, git, vim, jq, python3), sets the timezone, masks sleep and hibernate so a host never suspends, adds `ssh_authorized_keys`, adds the passwordless sudoers file, sets where Docker stores its data (`docker_data_root`), the Ghostty terminfo entry (so `TERM=xterm-ghostty` works over SSH) and zellij (a terminal multiplexer; the version and checksums are in `group_vars/all/versions.yml`).

## Services

- **Drive roles** (`fast`, `primary`, `backup`) are claimed by entries in the host's `drives` ([storage.md](./storage.md)). A service that needs a role the host has not claimed fails the deploy with a message naming the role.
- **Vault entries** go in `host_vars/<host>/vault.yml` (service secrets) or `group_vars/all/vault.yml` (shared secrets): [ansible/README.md](../ansible/README.md#vault-secrets).

| Service | What it is | Role | Needs | Section |
|---|---|---|---|---|
| Immich | Photo library (Google Photos alternative) | `roles/immich` | `primary` and `fast` drive roles; `vault_immich_db_password` | [Immich](#immich) |
| Copyparty | File sharing | `roles/copyparty` | `primary` and `fast` drive roles; `vault_copyparty_user`, `vault_copyparty_pass`; `vault_copyparty_collab_users` with `copyparty_collab_enabled` | [Accounts and volumes](#copyparty-accounts-and-volumes) |
| Gitea | Git server | `roles/gitea` | `fast` drive role; `gitea_root_url`, `gitea_domain`, `gitea_ssh_domain`; `vault_gitea_runner_token` is optional | [Gitea](#gitea) |
| Homebridge | HomeKit bridge | `roles/homebridge` | `fast` drive role | [Homebridge](#homebridge) |
| pics | Photo culling and sharing | `roles/pics`, `roles/github_clone` | `fast` drive role; Copyparty with a `photos` service account; `pics_repo`, `pics_public_url`; `vault_github_read_token`, `vault_pics_password`, `vault_pics_secret_key` | [pics](#pics-photo-culling-and-sharing), [Private GitHub repo](#clone-a-private-github-repo) |
| Garage | S3-compatible object storage | `roles/garage` | `fast` drive role; four `vault_garage_*` entries | [Garage](#garage-s3) |
| Crafty | Minecraft servers | `roles/crafty` | `fast` drive role; RAM headroom | [Crafty](#crafty-minecraft-servers) |
| ntfy | Push alerts for failed backups | `roles/ntfy` | `fast` drive role; `vault_ntfy_password`, `vault_ntfy_token` | [ntfy: failure alerts](#ntfy-failure-alerts) |
| Cloudflare Tunnel | Public hostnames without port forwarding | `roles/cloudflared` | `cloudflare_zones`, `cloudflared_ingress`; `vault_cloudflared_api_token`, `vault_cloudflared_account_id` | [Public hostname](#cloudflare-add-a-public-hostname) |
| Tailscale | Private remote access, installed on every host | `roles/tailscale` | Tailscale joined by hand | [Networking](./networking.md) |
| Homepage | Start page with a tile for each enabled service on the host | `roles/homepage` | none | [Homepage](#homepage) |
| Dockge, Caddy | Web UI for your own compose stacks; names for apps, routed by container label | `roles/dockge`, `roles/caddy` | `fast` drive role | [Ad-hoc app platform](#ad-hoc-app-platform) |
| Backups | Daily local and weekly cloud backups, a weekly integrity check, a read-only status dashboard | `roles/backup`, `roles/backup_status` | [backups.md](./backups.md) | [backups.md](./backups.md) |
| Direct Ethernet link | Cable from a Pi to a laptop for fast transfers | `roles/network` | none | [networking.md](./networking.md#direct-ethernet-link) |

## Immich

Photo library with a machine-learning container. Photos are stored in `immich_upload_location` (primary drive) and its Postgres data in `immich_db_data_location` (fast drive).

- Public access is a `cloudflared_ingress` entry pointing at `http://immich_server:2283`.
- Postgres is dumped before each backup by `roles/immich/files/dump.sh`, so the database is backed up consistently ([backups.md](./backups.md)).
- Moving Immich to a newer image can run database migrations: read its release notes first ([ansible/README.md](../ansible/README.md#update-service-images)).

## Gitea

Git hosting with an optional Actions runner.

- Set `gitea_root_url`, `gitea_domain` and `gitea_ssh_domain` in `group_vars/all/vars.yml` or the host's `vars.yml`.
- Web UI on `gitea_port` (3000), SSH for clones on `gitea_ssh_port` (2222). Public access is a `cloudflared_ingress` entry pointing at `http://gitea:3000`.
- The runner starts only when `vault_gitea_runner_token` is not empty.
- The database is dumped before each backup by `roles/gitea/files/dump.sh`.

## Copyparty accounts and volumes

- Config: rendered from `roles/copyparty/templates/copyparty.conf.j2` into `copyparty_config_dir`.
- Admin account: `copyparty_user` / `copyparty_pass`. `copyparty_collab_enabled: true` adds `/collab`, a shared folder (`copyparty_collab_dir`, on the `primary` drive) for the friends listed in `vault_copyparty_collab_users`; the admin has access too. With it off there is no folder and no friend accounts.

Service accounts (for apps that talk to Copyparty): add an entry to `copyparty_service_accounts` in `group_vars/all/vars.yml` or the host's `vars.yml` (user, password variable, volumes as folder plus permissions) and put the password in the vault. The example is in the comment above `copyparty_service_accounts` in `ansible/group_vars/all/defaults.yml`.

- Each volume is mounted at `/<folder>` and stored in `copyparty_files_dir/<folder>`, owned by the admin. Those folders then vanish for other accounts that have `/`, such as the SFTP account (see `copyparty_sftp_enabled` below).
- Leave out `d` unless the app must delete. Without `d` Copyparty also refuses overwrites, so the app can't destroy anything.

`/drives` shows USB drives and cards plugged into the host (`usb_automount_enabled`), read-only unless `usb_automount_writable`. Drives listed in `drives` are never shown. See [storage.md](./storage.md#plugged-in-usb-drives-drives).

`/fast` is a volume on the fast drive (`copyparty_fast_dir`, default `<fast_drive>/fast`) for SSD-speed working space. It exists only when you set `copyparty_fast_enabled: true`, which is worth it only when the fast and primary roles are on different drives. `/` stays the bulk volume. A `fast/` folder inside `files/` is hidden once the volume exists.

`copyparty_sftp_enabled: true` opens an SFTP listener on `copyparty_sftp_port` for the pocketpi sync. Its account is `vault_pocketpi_sftp_user` and `vault_pocketpi_sftp_pass` from the vault, with read, write, move and delete on `/files`.

To change anything else, edit `copyparty.conf.j2` or the variables, then `just deploy copyparty`. Image versions are in `ansible/group_vars/all/versions.yml` (see "Update service images" in [ansible/README.md](../ansible/README.md)).

## Clone a private GitHub repo

- Token: `vault_github_read_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how to create it).
- A role calls `roles/github_clone` with `repo` and `dest`. The token is passed to git through its environment, so it is not stored in `.git/config`.
- If the token expires, the clone step fails. Make a new one and update the vault with `ansible-vault edit`.

## pics: photo culling and sharing

The `pics` role clones the private `lab` repo (`pics_repo`), builds the image on the Pi (several minutes the first time; later runs rebuild only when the repo's commit changed) and runs it on `services`. It uses the `photos` service account in `copyparty_service_accounts`.

1. Set `pics_repo` and `pics_public_url` (see `group_vars/all/vars.yml.example`) and add a `cloudflared_ingress` entry for the public hostname in the host's `vars.yml`. Two ports:
   - Owner app (cull UI, password-gated): `pics_port` (default 8100), the only published port. LAN: `http://<pi>:<pics_port>`; tailnet: `http://<pi-tailscale-ip>:<pics_port>`.
   - Guest surface (share pages, portfolio, no owner routes): `pics_public_port` (8001), inside Docker only. The tunnel points at `http://pics:<pics_public_port>`, so no `path` rule is needed.
2. In the host's vault add `vault_pics_password` (12+ characters) and `vault_pics_secret_key` (`openssl rand -base64 48`). Use values without single quotes.
3. `just deploy copyparty,pics,cloudflared --limit <host>`. `copyparty` creates the `photos` account and its two volumes first.

The database is in `pics_data_dir`, covered by the daily backup; the app also writes its own daily snapshots there. `teardown.yml --tags pics` keeps that data unless `-e remove_data=true`.

## Cloudflare: add a public hostname

In the host's `host_vars/<host>/vars.yml`:

```yaml
cloudflared_ingress:
  - hostname: newservice.example.com
    service: "http://newservice:8080"
```

Then `just deploy cloudflared`.

Any host can run a tunnel: set `cloudflared_enabled: true` and its own `cloudflared_ingress` in `host_vars/<host>/vars.yml`. The tunnel is named `<host>-tunnel` unless the host sets `cloudflared_tunnel_name`. `cloudflare_zones` goes in `group_vars/all/vars.yml`; the API token and account ID are `vault_cloudflared_api_token` and `vault_cloudflared_account_id` in `group_vars/all/vault.yml`. A hostname may appear in only one host's `cloudflared_ingress`; the deploy fails if two hosts list it.

- Each hostname's DNS record is created in the zone from `cloudflare_zones` (domain: zone ID) whose domain appears in the hostname. A hostname on a new domain needs that domain in `cloudflare_zones`, and the API token needs DNS:Edit on that zone.
- The deploy fails before calling Cloudflare if a rule has anything besides `hostname` and `service` (no `path:`), or if its hostname matches no domain or more than one in `cloudflare_zones`.
- Hostnames not listed get a 404.
- Every record the role writes carries the comment `managed by simple-nas, tunnel <tunnel name>`; that comment is how a later deploy knows the record is its own. A deploy prints the DNS plan (create, comment, repoint, delete) before changing anything, and `--check` prints the same plan.
- A hostname's existing record is kept if it points at this tunnel (the comment is added if missing), and repointed if it has the comment or points at a deleted tunnel. A record that points at another tunnel that still exists, or is any other type (A, MX, TXT, ...), stops the deploy with a message naming it; delete it in the Cloudflare dashboard (DNS) if unused.
- A record not in `cloudflared_ingress` is deleted if it has the comment or points at this tunnel. That covers a hostname removed from the list and one added in the Zero Trust dashboard (the next deploy also removes its rule). A record that points at a deleted tunnel and has no comment is only listed in the plan; delete it in the dashboard.
- The tunnel is found by name. If the name changes (the host's key in the inventory, or `cloudflared_tunnel_name`), the next deploy creates a tunnel under the new name. The DNS records still point at the old tunnel, which exists, so the deploy stops and names them. Delete the old tunnel in the dashboard (Zero Trust, Networks, Tunnels) and deploy again: that repoints the records at the new tunnel and gives the host the new token, and the public hostnames are down for the moment that takes.
- The tunnel is remotely managed: the deploy sets its rules at Cloudflare through the API (from your machine), and the host holds only a tunnel token (`/opt/services/cloudflared/token`). If no tunnel named `cloudflared_tunnel_name` exists, the deploy creates it.
- If a tunnel with that name exists but is "locally managed", the deploy stops. Use its migrate option in the dashboard (Zero Trust, Networks, Tunnels), or delete the tunnel (public hostnames are offline until the next deploy).
- A leftover `*.json` credentials file in `/opt/services/cloudflared/` is not used and not touched; delete it by hand.

## ntfy: failure alerts

A private [ntfy](https://docs.ntfy.sh/) server (`ntfy_enabled`) that a failed backup job writes to, so a failure reaches your phone instead of waiting in a log.

1. Make the secrets: a login password and a token (`docker run --rm binwiederhier/ntfy token generate`). The password goes in `vault_ntfy_password` (`host_vars/<host>/vault.yml`) and the token in `vault_ntfy_token` (`group_vars/all/vault.yml`). The deploy hashes the password; no hash is stored.
2. Set `ntfy_enabled: true` and `ntfy_alert_url: "http://localhost:8090/alerts"` (topic `alerts`) in the host's `vars.yml`; `just deploy ntfy,backup --limit <host>`.
3. In the ntfy app, add the server `http://<host-tailscale-name>:8090` with user `alerts` and your password, and subscribe to topic `alerts`. The phone must be on Tailscale.
4. Test the chain: on the host run `bash /opt/services/scripts/alert.sh "test"` and check the phone gets it.

- The server denies everyone but the `alerts` user and its token, so the published port is not open to the LAN. The user and token are set from the compose file at every start; the data directory only holds message history.
- Another host sends alerts to the same server by setting `ntfy_alert_url` to `http://<ntfy-host-tailscale-name>:8090/alerts` in its `host_vars`; it needs `vault_ntfy_token` (`group_vars/all/vault.yml`).
- `alert.sh` (backup role) runs when a cron job fails: it always writes to the system log (`journalctl -t backup`) and sends to ntfy only if `ntfy_alert_url` is set. A failed send is ignored and times out after 15 seconds, so alerting cannot fail or stall a backup.
- It cannot report the host being down or a backup that never started (cron not running, host off).
- iOS push for a self-hosted server goes through ntfy.sh: `ntfy_ios_push: true` sends ntfy.sh the message ID and a hash of the topic URL, not the message. Android needs no relay.

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret`, `vault_garage_admin_token`, `vault_garage_webui_user` and `vault_garage_webui_pass` in the host's vault, then `just deploy garage,cloudflared --limit <host>`.

- Garage's metadata is root-owned, so the backup carries it as a dump (`garage-meta-*.tar.gz`), not as files: [Restore: Garage](./backups.md#restore-garage).
- Garage always starts with `--single-node`: it creates the one-node layout on first start and leaves an existing layout alone.
- `vault_garage_webui_pass` is the web UI password; the deploy hashes it (bcrypt with a fixed salt, so the output is the same on every run).
- Open `https://garage.example.com` (the `garage-webui` entry in `cloudflared_ingress`), log in with the web UI credentials, and create buckets and access keys there.
- Apps connect with endpoint `https://s3.example.com`, region `garage`, and the key pair from the web UI.

## Crafty (Minecraft servers)

One container runs every server. All data is under `crafty_data_dir` (`servers/ backups/ logs/ config/ import/`).

- Panel: `https://<pi-ip>:28443` (`crafty_port`, self-signed certificate). The first admin password is in `docker logs crafty` or `<crafty_data_dir>/config/default-creds.txt`. Change it in the panel, then delete that file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575); set it when creating the server.
- `crafty_memory_limit` (default 3g) caps all servers combined. On a 4 GB Pi it competes with Immich if both run on the host.
- Not behind Cloudflare Tunnel. Players join over the LAN, a router port-forward of the game port, or Tailscale. The panel and game ports are published on all interfaces, so don't forward the panel port.
- The live `servers/` directory is in the daily restic backup; Crafty's own `backups/` archives are not (see [backups.md](./backups.md)).

## Homebridge

Runs with `network_mode: host` (HomeKit discovery needs it), so it is not on `services` and not in `cloudflared_ingress`.

- Remote Apple Home access needs a HomeKit hub (Apple TV or HomePod) on your LAN. Tailscale does not replace it: off home Wi-Fi the Home app shows the bridge offline even with Tailscale connected.
- The admin UI is reachable over Tailscale at `http://<pi-tailscale-ip>:8581` (plain HTTP).

The role only deploys the container; the image creates `config.json` and `auth.json` on first start. Log in with `admin`/`admin` and change the password at once. The HomeKit PIN and plugins are set in the UI and persist across deploys.

## Homepage

A start page (`homepage_enabled`, [Homepage](https://gethomepage.dev)) for all your servers. Run it on one host: it shows a group of tiles for every host in the inventory, one tile per service that host has switched on and that has a host port or a Caddy name, each with a green or red dot for whether the page answers. It follows the device's light or dark setting, in Catppuccin Latte and Mocha colours (`roles/homepage/files/custom.css`).

- Open it at `http://<homepage_host>:<homepage_port>` (port 3001). `homepage_host` defaults to the address Ansible reaches the host at (the full tailnet name). The page also answers on the inventory name and on the address Ansible reaches the host at. Any other address (a LAN IP, a Caddy name) gets a host validation error: set `homepage_host` to the one you use.
- Each host's tiles link to the service's `https://` name when that host runs Caddy with `caddy_private_domains` and the service has a subdomain ([networking.md](./networking.md#names-for-apps-caddy_private_domains)), and otherwise to that host's `ansible_host` and port settings. The page changes when the Homepage host is deployed, so after switching a service on or off elsewhere, run `just deploy homepage --limit <homepage host>`.
- The tiles are the `web_services` list in `group_vars/all/web_services.yml`, with a comment on each field; add a line to add a tile. Garage, Caddy and Cloudflare Tunnel have no web UI to link to. Without a Caddy name, Crafty's panel uses a self-signed certificate and the browser warns.
- `homepage_links` adds your own tiles in a "Links" group: a public hostname, a machine outside the inventory, an app you made in Dockge (link its Caddy name, with `monitor: true` for an up/down dot), any page. The format and examples are in `roles/homepage/defaults/main.yml`; run `just deploy homepage --limit <the host that runs the Homepage>` to show a change.
- Ansible writes every file Homepage reads (tiles, title, an empty bookmarks and widgets list, the colours), so a deploy resets edits to them. Change them in the repo.
- The page has no login and holds only links; each service keeps its own. Homepage's optional password login ([security](https://gethomepage.dev/installation/#security-authentication)) is not set up; it matters only if the page is published.
- Widgets (live numbers from Immich, Gitea and others) are not set up. Each needs an API key from the app ([widgets](https://gethomepage.dev/widgets/)).

## Ad-hoc app platform

**Dockge** (`dockge_enabled`) is a web UI at `http://<host>:<dockge_port>` (5001) over `compose.yaml` stacks in `dockge_stacks_dir` (`<fast drive>/stacks`). Create the account on first visit. Ansible deploys Dockge only; the stacks are yours and stay when Dockge is removed. A stack keeps its state in bind mounts (see [storage.md](./storage.md#examples)), not Docker volumes, so deleting a stack is deleting its directory.

**Caddy** (`caddy_enabled`) gives apps names from container labels; syntax in [caddy-reference.md](./caddy-reference.md). With `caddy_private_domains` set, names under your own domain get Let's Encrypt certificates ([networking.md](./networking.md#names-for-apps-caddy_private_domains)). Without it, apps are reachable over Tailscale at `http://<host>:<port>`. Stacks that want a name join the `services` network.

Public access is off unless the host sets `cloudflared_enabled: true` ([Cloudflare](#cloudflare-add-a-public-hostname)); otherwise reach apps over Tailscale. A stack is reachable from the tunnel when it joins `services`; the ingress `service` is then `http://<container_name>:<port>`. Removal: `ansible-playbook teardown.yml --tags dockge,caddy,cloudflared --limit <host> --vault-password-file .vault-pass`.

Both mount the Docker socket: anyone who can reach their UI or set a label controls Docker on that host.

Stacks, Dockge's data and Caddy's data sit on the host's `fast` drive, so the host's backup covers them ([backups.md](./backups.md)).
