# Service notes

Every service is off until a host sets `<name>_enabled: true` in `ansible/host_vars/<host>/vars.yml`. This page lists what each service needs and the setup steps beyond the flag. Run `just deploy <tag>` from `ansible/` (tag = role name). Settings and their defaults are in `ansible/group_vars/all/defaults.yml` and each role's `defaults/main.yml`; file locations are in [ansible/README.md](../ansible/README.md). Backups are in [backups.md](./backups.md).

## Every host

The `common` role runs on every host. It installs base packages (curl, git, vim, jq, python3, ca-certificates, gnupg, python3-docker), sets the timezone, masks sleep and hibernate so a host never suspends, adds `ssh_authorized_keys`, adds the passwordless sudoers file, sets where Docker stores its data (`docker_data_root`), and, unless `terminal_tools_enabled: false`, installs the Ghostty terminfo entry (so `TERM=xterm-ghostty` works over SSH) and zellij (a terminal multiplexer; the version and checksums are in `group_vars/all/versions.yml`).

## Services

- **Drive roles** (`fast`, `primary`, `backup`) are claimed by entries in the host's `drives` ([storage.md](./storage.md)). A service that needs a role the host has not claimed fails the deploy with a message naming the role.
- **Vault entries** go in `host_vars/<host>/vault.yml` (service secrets) or `group_vars/all/vault.yml` (shared secrets): [ansible/README.md](../ansible/README.md#vault-secrets).

| Service | What it is | Role | Needs | Section |
|---|---|---|---|---|
| Immich | Photo library (Google Photos alternative) | `roles/immich` | `primary` and `fast` drive roles; `vault_immich_db_password` | [Immich](#immich) |
| Copyparty | File sharing | `roles/copyparty` | `primary` and `fast` drive roles; `vault_copyparty_user`, `vault_copyparty_pass`; `vault_copyparty_collab_users` with `copyparty_collab_enabled` | [Accounts and volumes](#copyparty-accounts-and-volumes) |
| Gitea | Git server | `roles/gitea` | `fast` drive role; `gitea_root_url`; `vault_gitea_runner_token` is optional | [Gitea](#gitea) |
| Homebridge | HomeKit bridge | `roles/homebridge` | `fast` drive role | [Homebridge](#homebridge) |
| pics | Photo culling and sharing | `roles/pics`, `roles/github_clone` | `fast` and `primary` drive roles; Copyparty; `pics_repo`, `pics_public_url`; `vault_github_read_token`, `vault_pics_password`, `vault_pics_secret_key`, `vault_pics_copyparty_pass` | [pics](#pics-photo-culling-and-sharing), [Private GitHub repo](#clone-a-private-github-repo) |
| Garage | S3-compatible object storage | `roles/garage` | `fast` drive role; four `vault_garage_*` entries | [Garage](#garage-s3) |
| Crafty | Minecraft servers | `roles/crafty` | `fast` drive role; RAM headroom | [Crafty](#crafty-minecraft-servers) |
| ntfy | Push alerts for failed backups | `roles/ntfy` | `fast` drive role; `vault_ntfy_password`, `vault_ntfy_token` | [ntfy: failure alerts](#ntfy-failure-alerts) |
| Tinyauth | Login page in front of browser-only services | `roles/tinyauth` | `fast` drive role; `caddy_enabled` with `caddy_private_domains`; `vault_tinyauth_users` | [Tinyauth: login](#tinyauth-login) |
| Dozzle | Container logs in a browser | `roles/dozzle` | `fast` drive role; `caddy_enabled` with `caddy_private_domains`; `tinyauth_enabled` | [Dozzle: container logs](#dozzle-container-logs) |
| Scrutiny | Drive health (SMART) dashboard | `roles/scrutiny` | `fast` drive role; `caddy_enabled` with `caddy_private_domains`; `tinyauth_enabled`; a drive that answers SMART | [Scrutiny: drive health](#scrutiny-drive-health) |
| Cloudflare Tunnel | Public hostnames without port forwarding | `roles/cloudflared` | `cloudflare_zones`, `cloudflared_ingress`; `vault_cloudflared_api_token`, `vault_cloudflared_account_id` | [Public hostname](#cloudflare-add-a-public-hostname) |
| Tailscale | Private remote access, installed on every host | `roles/tailscale` | Tailscale joined by hand | [Networking](./networking.md) |
| Homepage | Start page with a tile for each enabled service on every host in the inventory | `roles/homepage` | none | [Homepage](#homepage) |
| Dockge, Caddy | Dockge: web UI for your own compose stacks. Caddy: reverse proxy that gives each app a name from its container labels | `roles/dockge`, `roles/caddy` | `fast` drive role | [Ad-hoc app platform](#ad-hoc-app-platform) |
| Backups | Daily local and weekly cloud backups, a weekly integrity check, a read-only status dashboard | `roles/backup`, `roles/backup_status` | [backups.md](./backups.md) | [backups.md](./backups.md) |
| Connectivity watchdog | Reconnects the network when TCP stops working | `roles/connectivity_watchdog` | NetworkManager to reconnect | [networking.md](./networking.md#connectivity-watchdog) |
| Direct Ethernet link | Cable from a Pi to a laptop for fast transfers | `roles/network` | none | [networking.md](./networking.md#direct-ethernet-link) |

## Immich

Photo library with a machine-learning container. Photos are stored in `immich_upload_location` (primary drive) and its Postgres data in `immich_db_data_location` (fast drive).

- Public access is a `cloudflared_ingress` entry pointing at `http://immich_server:2283`.
- `immich_sso_enabled: true` lets a Tinyauth login open Immich ([Sign in with Tinyauth](./auth-reference.md#sign-in-with-tinyauth-oidc)).
- With it on, Immich reads its whole configuration from `/opt/services/immich/immich-config.json`, and its admin settings page is read-only: a setting the template does not write gets Immich's default, not the value the page saved. A setting you need goes into `roles/immich/templates/immich-config.json.j2` (Administration > Settings shows the key and value to copy).
- Postgres is dumped before each backup by `roles/immich/files/dump.sh`, so the database is backed up consistently ([backups.md](./backups.md)).
- To move `immich_upload_location` to another drive ([move one service's data](./storage.md#move-one-services-data)), copy the whole directory including the hidden `.immich` file in each subfolder (`library`, `thumbs`, `upload` and others). Immich checks those files at start and refuses to run without them ([system integrity](https://docs.immich.app/administration/system-integrity)).
- Moving Immich to a newer image can run database migrations: read its release notes first ([ansible/README.md](../ansible/README.md#update-service-images)).

## Gitea

Git hosting with an optional Actions runner.

- Set `gitea_root_url` in `group_vars/all/vars.yml` or the host's `vars.yml`. `gitea_domain` and `gitea_ssh_domain` default to the host name in `gitea_root_url`; set `gitea_ssh_domain` when SSH clones need another name, because a Cloudflare tunnel carries only HTTP.
- Web UI on `gitea_port` (3000), SSH for clones on `gitea_ssh_port` (2222). Public access is a `cloudflared_ingress` entry pointing at `http://gitea:3000`.
- The runner starts only when `vault_gitea_runner_token` is not empty.
- `gitea_sso_enabled: true` lets a Tinyauth login open Gitea ([Sign in with Tinyauth](./auth-reference.md#sign-in-with-tinyauth-oidc)).
- The database is dumped before each backup by `roles/gitea/files/dump.sh`.

## Copyparty accounts and volumes

- Config: rendered from `roles/copyparty/templates/copyparty.conf.j2` into `copyparty_config_dir`.
- Admin account: `copyparty_user` / `copyparty_pass`. `copyparty_collab_enabled: true` adds `/collab`, a shared folder (`copyparty_collab_dir`, on the `primary` drive) for the friends listed in `vault_copyparty_collab_users`; the admin has access too. With it off there is no folder and no friend accounts.

Apps that store files in Copyparty (pics) get an account named after the app, with the password `vault_<app>_copyparty_pass`, and their own volumes at `/<app>/<folder>` from directories of their own (for pics, `pics_photos_dir` and `pics_trash_dir`). They are declared in the app's `copyparty` field in `group_vars/all/services.yml`; the field comment says how to give another app one.

- The volumes are not part of `copyparty_files_dir`, so the admin's file listing and the SFTP account do not show them. The admin has full access to them at their own addresses.
- Leave out `d` unless the app must delete. Without `d` Copyparty also refuses overwrites, so the app can't destroy anything.

`/drives` shows the USB drives and cards plugged into the host when `usb_automount_enabled: true`, read-only unless `usb_automount_writable` ([storage.md](./storage.md#plugged-in-usb-drives-drives)).

`/fast` is a volume on the fast drive (`copyparty_fast_dir`, default `<fast_drive>/fast`) for SSD-speed working space. It exists only when you set `copyparty_fast_enabled: true`, which is worth it only when the fast and primary roles are on different drives. `/` stays the bulk volume. A `fast/` folder inside `files/` is hidden once the volume exists.

`copyparty_sftp_enabled: true` opens an SFTP listener on `copyparty_sftp_port` for a sync client. Its account is `copyparty_sftp_user` with the password `vault_copyparty_sftp_pass` from the vault, with read, write, move and delete on `/files`.

`copyparty_sso_enabled: true` puts the browser name (`<copyparty_subdomain>.<first private domain>`) behind the Tinyauth login, so one login opens it.

- It needs `tinyauth_enabled`, `caddy_enabled`, `vault_copyparty_idp_key` (the name of a header only Caddy sends; `openssl rand -hex 24`) and `copyparty_sso_admins` in the host's `vars.yml`: the Tinyauth user names, matched exactly, that get admin access to `/`, `/collab` and `/fast`. Tinyauth sends groups only for LDAP and OAuth logins, so Copyparty gets names, not Tinyauth groups.
- The browser name is the only lane behind the login. The published port, the Cloudflare tunnel hostname and SFTP keep Copyparty's own passwords: WebDAV, rclone and phone apps use `http://<host>:<copyparty_port>` with their account. A tunnel hostname that points at Copyparty bypasses Caddy, so it keeps the password login too.
- A share link on the browser name asks for the Tinyauth login as well. Copyparty's docs expect the share prefix (`/shares`) to be exempt from the login ([shares](https://github.com/9001/copyparty#shares)); hand links out on the published port or the tunnel hostname instead.

To change anything else, edit `copyparty.conf.j2` or the variables, then `just deploy copyparty`. Image versions are in `ansible/group_vars/all/versions.yml` (see "Update service images" in [ansible/README.md](../ansible/README.md)).

## Clone a private GitHub repo

- Token: `vault_github_read_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how to create it).
- A role calls `roles/github_clone` with `repo` and `dest`. The token is passed to git through its environment, so it is not stored in `.git/config`.
- If the token expires, the clone step fails. Make a new one and update the vault with `ansible-vault edit`.

## pics: photo culling and sharing

The `pics` role clones the private repo named in `pics_repo`, builds the image on the Pi (several minutes the first time; later runs rebuild only when the repo's commit changed) and runs it on `services`. It uses the Copyparty account `pics` and its two volumes (`/pics/photos` with no delete, `/pics/trash` where it may delete).

1. Set `pics_repo` and `pics_public_url` (see `group_vars/all/vars.yml.example`) and add a `cloudflared_ingress` entry for the public hostname in the host's `vars.yml`. Two ports:
   - Owner app (cull UI, password-gated): `pics_port` (default 8100), the only published port. LAN: `http://<pi>:<pics_port>`; tailnet: `http://<pi-tailscale-ip>:<pics_port>`.
   - Guest surface (share pages, portfolio, no owner routes): `pics_public_port` (8001), inside Docker only. The tunnel points at `http://pics:<pics_public_port>`, so no `path` rule is needed.
2. In the host's vault add `vault_pics_password` (12+ characters), `vault_pics_secret_key` (`openssl rand -base64 48`) and `vault_pics_copyparty_pass`. Use values without single quotes.
3. `just deploy copyparty,pics,cloudflared --limit <host>`. `copyparty` creates the `pics` account and its volumes first.
4. Optional: sign in with Tinyauth instead of the password (`pics_sso_enabled`, [auth-reference.md](./auth-reference.md#sign-in-with-tinyauth-oidc)). The password login and the importer's token stay. pics' Caddy name is not behind Tinyauth: pics has its own login and the sign-in goes through it.

The database is in `pics_data_dir`, covered by the daily backup; the app also writes its own daily snapshots there. `teardown.yml -e only=pics` keeps all of pics' data unless `-e remove_data=true`, which also deletes the photos and trash (`pics_photos_dir`, `pics_trash_dir`).

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

## ntfy: failure alerts

A private [ntfy](https://docs.ntfy.sh/) server (`ntfy_enabled`) that a failed backup job writes to, so a failure reaches your phone instead of waiting in a log.

1. Make the secrets: a login password and a token (token: `docker run --rm binwiederhier/ntfy token generate`; password: `openssl rand -base64 24`). The password goes in `vault_ntfy_password` (`host_vars/<host>/vault.yml`) and the token in `vault_ntfy_token` (`group_vars/all/vault.yml`). The deploy hashes the password into the compose file (mode 0640), so the vault holds the plain password.
2. On the host that runs ntfy, set `ntfy_enabled: true` and `ntfy_server: <that host's inventory name>` in its `vars.yml`; `just deploy ntfy,common --limit <host>`.
3. In the ntfy app, add the server `http://<host-tailscale-name>:8090` with user `alerts` and your password, and subscribe to topic `alerts`. The phone must be on Tailscale. With Caddy and a private domain, `https://ntfy.<host>.<your domain>` also works; set `ntfy_base_url` to it in the host's `vars.yml` so links and iOS push use that address, and add that server in the app instead.
4. Test the chain: on the host run `bash /opt/services/scripts/alert.sh "test"` and check the phone gets it.

- The server denies everyone but the `alerts` user and its token, so the published port asks for a login even on the LAN. The user and token are set from the compose file at every start; the data directory holds the message history and the user database.
- One ntfy server serves the whole homelab. Another host sends its alerts there by setting only `ntfy_server: <the ntfy host's inventory name>` (and no `ntfy_enabled`); it needs `vault_ntfy_token` from `group_vars/all/vault.yml`, and `just deploy common --limit <host>` after setting `ntfy_server`. A host with neither setting sends nothing. A server this repo does not run, such as ntfy.sh, is `ntfy_alert_url`.
- `alert.sh` (common role) runs when a backup cron job fails and when the [connectivity watchdog](./networking.md#connectivity-watchdog) recovers; it writes to the system log under the tag it is given (`journalctl -t backup` for the backup jobs, `-t connectivity` for the watchdog) and sends to ntfy only if `ntfy_alert_url` is set. A failed send is ignored and times out after 15 seconds, so alerting cannot fail or stall a backup.
- It cannot report the host being down or a backup that never started (cron not running, host off).
- iOS push for a self-hosted server goes through ntfy.sh: `ntfy_ios_push: true` sends ntfy.sh the message ID and a hash of the topic URL, not the message. Android needs no relay.

## Tinyauth: login

[Tinyauth](https://tinyauth.app/docs/about/) (`tinyauth_enabled`) is a small login page. Caddy asks it about every request to a protected name, so the service needs no login of its own: a browser with a session passes, one without it is redirected (302) to the login page at `https://auth.<first private domain>`, and any other client gets a 401, so scripts and apps fail instead of following a redirect. Its docs say it is for homelabs and sharing with family and friends, not for setups that need roles and fine-grained permissions. Tinyauth and the protected services must run on the same host.

1. Make a login: add `name` and `password` to the list `vault_tinyauth_users` in `group_vars/all/vault.yml` (shape in `group_vars/all/vault.yml.example`; the deploy hashes the password, so the vault holds it in plain text). A second user is another list entry. Two-factor codes, sign in with GitHub or Google, Tailscale, session length: [auth-reference.md](./auth-reference.md).
2. On the host, set `tinyauth_enabled: true` in `vars.yml`. It needs Caddy with a private domain: the page only has that https name.
3. `just deploy tinyauth,caddy,homepage --limit <host>`.

- With `tinyauth_enabled`, every service this repo deploys that has a Caddy name is behind the login, except the ones marked `own_login: true` in `group_vars/all/services.yml`: Immich, Gitea, Copyparty, pics and ntfy have apps, git, WebDAV and push clients that cannot log in through a web page, and Tinyauth is its own login. Copyparty's browser name is behind the login with `copyparty_sso_enabled` ([Copyparty accounts and volumes](#copyparty-accounts-and-volumes)). To exempt another service, add `own_login: true` to its entry.
- A protected service is served under the first `caddy_private_domains` entry only: the session cookie covers one parent domain. The published host port, if any, is not protected.
- An app you run in Dockge opts in with one label, `caddy.import: tinyauth_forwarder`, next to its other `caddy` labels ([label syntax](./caddy-reference.md#label-syntax)); a name in `caddy_sites` opts in with the same import. The app receives the signed-in user in the `Remote-User`, `Remote-Name` and `Remote-Email` headers. [SilverBullet](https://silverbullet.md/), for example, has no single sign-on of its own, and [its docs](https://edge.silverbullet.md/Authentication) say to put it behind an authentication proxy, which Tinyauth is, so leave its `SB_USER` unset.

### How an app joins

The label above is the way in for every app; what the app can do next removes the second login. Try these in order:

1. **It speaks OpenID Connect (Gitea, Immich, pics):** Tinyauth is its OIDC provider when `gitea_sso_enabled`, `immich_sso_enabled` or `pics_sso_enabled` is on, so the app knows who signed in and keeps its own accounts and permissions ([Sign in with Tinyauth](./auth-reference.md#sign-in-with-tinyauth-oidc)).
2. **It trusts a proxy's user header (Dozzle, Copyparty):** the app takes the name from `Remote-User`, with its own setting for it. Where the app lets you name the header, that name is a secret, so another container on the network cannot forge it.
3. **It has an off switch, written by the role (Dockge):** the deploy sets `disableAuth` in Dockge's database and opens Dockge straight into the account it already has, so Dockge never asks. Every Dockge account collapses into that one ([Ad-hoc app platform](#ad-hoc-app-platform)).
4. **Its own login is optional (webtop, Homepage):** leave the app's login unset and Tinyauth is the only one. Check the app's docs for how, and keep its port unpublished, since the port skips Tinyauth.
5. **Otherwise its own login stays** (`own_login: true`, so Tinyauth is not put in front of it at all). Crafty is not there: it has no off switch or basic auth and no header trust, and upstream [issue 762](https://gitlab.com/crafty-controller/crafty-4/-/work_items/762) asks for OIDC, so it shows its own login behind Tinyauth and you sign in twice.

The rule: an app's own login is switched off only when Tinyauth is in front of it and the app publishes no host port, because the port skips Caddy and the login. The role sets that setting in both directions on every deploy, so turning Tinyauth off, or publishing a port again, brings the app's own login back.

## Dozzle: container logs

[Dozzle](https://dozzle.dev/) (`dozzle_enabled`) shows the logs of every container on the host in a browser. It has no login of its own: it takes the user Tinyauth names from a header ([Tinyauth](#tinyauth-login)), so it needs `tinyauth_enabled` and Caddy with a `caddy_private_domains` entry, and is served at `https://logs.<private domain>`.

1. On the host, set `dozzle_enabled: true` and run `just deploy dozzle --limit <host>`.
2. `dozzle_port` is empty by default; setting it publishes the page without a login, which Dozzle's docs warn against in forward-proxy mode.

The socket is mounted read-only because Dozzle only reads, not because that limits the Docker API. The view is read-only: no shell and no container actions. It shows every container's log, and Docker's log rotation (`docker_log_opts`, three files of 10m) bounds how much is kept. `dozzle_data_dir` holds per-user settings and is backed up.

## Scrutiny: drive health

[Scrutiny](https://github.com/AnalogJ/scrutiny) (`scrutiny_enabled`) is a dashboard of every drive's SMART health and history. It has no login of its own: it needs `tinyauth_enabled` and Caddy with a `caddy_private_domains` entry, and is served at `https://disks.<private domain>`.

1. On the host, set `scrutiny_enabled: true` and run `just deploy scrutiny --limit <host>`.
2. The role reads the drive list from `smartctl --scan` at deploy time; set `scrutiny_devices` to a list of device paths when that list is wrong for the host. SMART passes through a USB bridge only for some enclosures; when no drive answers, the deploy stops with "no drive on this host answers SMART; Scrutiny has nothing to show".
3. After plugging in or unplugging a drive, run `just deploy scrutiny --limit <host>` again so the container gets the new list.

The InfluxDB history in `scrutiny_influx_dir` is left out of the backup; `scrutiny_config_dir` is covered.

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret`, `vault_garage_admin_token`, `vault_garage_webui_user` and `vault_garage_webui_pass` in the host's vault, then `just deploy garage,cloudflared --limit <host>`.

- Garage's metadata is root-owned, so the backup carries it as a dump (`garage-meta-*.tar.gz`), not as files: [Restore: Garage](./backups.md#restore-garage).
- Garage reads its cluster layout from `garage_data_dir/meta`. A first deploy (empty meta dir) starts with `--single-node` so Garage auto-configures the one-node layout; later starts omit the flag, which Garage requires once a layout exists (the reason is in the comment in `roles/garage/tasks/main.yml`).
- `vault_garage_webui_pass` is the web UI password; the deploy hashes it (bcrypt with a fixed salt, so the output is the same on every run).
- Open `https://garage.example.com` (the `garage-webui` entry in `cloudflared_ingress`), log in with the web UI credentials, and create buckets and access keys there.
- Apps connect with endpoint `https://s3.example.com`, region `garage`, and the key pair from the web UI. The same S3 API answers on the host at `garage_s3_port` (3900, LAN and tailnet) through the `garage-cors-proxy` container.

## Crafty (Minecraft servers)

One container runs every server. All data is under `crafty_data_dir` (`servers/ backups/ logs/ config/ import/`).

- Panel: `https://<pi-ip>:28443` (`crafty_port`, self-signed certificate). The first admin password is in `<crafty_data_dir>/config/default-creds.txt` (the container log names the file). Crafty makes this password itself and has no setting for it. Behind Tinyauth it is the second login, so change it in the panel to something short, then delete that file.
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

- With `tinyauth_enabled` and `caddy_private_domains` it is at `https://<homepage_subdomain>.<first private domain>` behind the login, and publishes no port. Without Tinyauth, set `homepage_port` (for example 3001) and open `http://<homepage_host>:<homepage_port>`; anyone on the network can then open it. `homepage_host` defaults to the address Ansible reaches the host at (the full tailnet name); the page also answers on the inventory name. Any other address gets a host validation error: set `homepage_host` to the one you use.
- Each host's tiles link to the service's `https://` name when that host runs Caddy with `caddy_private_domains` and the service has a subdomain ([caddy-reference.md](./caddy-reference.md#names-for-apps-caddy_private_domains)), and otherwise to that host's `ansible_host` and port settings. The page changes when the Homepage host is deployed, so after switching a service on or off elsewhere, run `just deploy homepage --limit <homepage host>`.
- The tiles are the entries of `services` in `group_vars/all/services.yml` that have an `icon`, with a comment on each field; add an entry to add a tile. Garage, Caddy and Cloudflare Tunnel have no tile: they have no entry in `web_services` (no icon). Garage's web UI is reached through its `cloudflared_ingress` entry instead. Without a Caddy name, Crafty's panel uses a self-signed certificate and the browser warns.
- `homepage_links` adds your own tiles in a "Links" group: a public hostname, a machine outside the inventory, an app you made in Dockge (link its Caddy name, with `monitor: true` for an up/down dot), any page. The format and examples are in `roles/homepage/defaults/main.yml`; run `just deploy homepage --limit <the host that runs the Homepage>` to show a change.
- Ansible writes every file Homepage reads (tiles, title, an empty bookmarks and widgets list, the colours), so a deploy resets edits to them. Change them in the repo.
- The page has no login of its own and holds only links; each service keeps its own. Homepage's optional password login ([security](https://gethomepage.dev/installation/#security-authentication)) is not set up, because Tinyauth is the login.
- Widgets (live numbers from Immich, Gitea and others) are not set up. Each needs an API key from the app ([widgets](https://gethomepage.dev/widgets/)).

## Ad-hoc app platform

**Dockge** (`dockge_enabled`) is a web UI at `http://<host>:<dockge_port>` (5001) over `compose.yaml` stacks in `dockge_stacks_dir` (`<fast drive>/stacks`). Create the account on first visit. Set `dockge_port: ""` to make the Tinyauth login its only one: the published port skips Caddy and Tinyauth, so Dockge keeps its own login while the port is set ([Tinyauth](#tinyauth-login)). The deploy needs that first account before it can switch Dockge's login off, so create it and deploy again. With `dockge_port: ""` Dockge has no login of its own, so every name that reaches it must import `tinyauth_forwarder`, including a name in `caddy_sites`. With its login off, any container on the `services` network (your own stacks included) can reach Dockge, and so the Docker socket, without a password; only the published port and Caddy are guarded. Keep untrusted containers off that network, or leave `dockge_port` set to keep Dockge's own login. If Tinyauth is down or removed, Dockge has no way in from a browser: set `tinyauth_enabled: false` (or publish `dockge_port`) and run `just deploy dockge --limit <host>` to get Dockge's own login back, and use ssh until then. Ansible deploys Dockge only; the stacks are yours and stay when Dockge is removed. A stack keeps its state in bind mounts (see [storage.md](./storage.md#dockers-own-storage)), not Docker volumes, so deleting a stack is deleting its directory.

**Caddy** (`caddy_enabled`) gives apps names from container labels; syntax in [caddy-reference.md](./caddy-reference.md). With `caddy_private_domains` set, names under your own domain get Let's Encrypt certificates ([caddy-reference.md](./caddy-reference.md#names-for-apps-caddy_private_domains)). Without it, apps are reachable over Tailscale at `http://<host>:<port>`. Stacks that want a name join the `services` network.

Public access is off unless the host sets `cloudflared_enabled: true` ([Cloudflare](#cloudflare-add-a-public-hostname)); otherwise reach apps over Tailscale. A stack is reachable from the tunnel when it joins `services`; the ingress `service` is then `http://<container_name>:<port>`. Removal: `ansible-playbook teardown.yml -e only=dockge,caddy,cloudflared --limit <host> --vault-password-file .vault-pass`.

Both mount the Docker socket: anyone who can reach their UI or set a label controls Docker on that host.

Stacks, Dockge's data and Caddy's data sit on the host's `fast` drive, so the host's backup covers them ([backups.md](./backups.md)).
