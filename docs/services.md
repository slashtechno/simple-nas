# Service notes

Every service below is off until a host sets `<name>_enabled: true` in `ansible/host_vars/<host>/vars.yml`. A few parts are on by default (the flags in [defaults-flags.yml](../ansible/group_vars/all/defaults-flags.yml) and `terminal_tools_enabled`). This page lists what each needs and the setup beyond the flag.

- **Deploy one:** `just deploy <tag>` from `ansible/` (tag = role name).
- **Settings and defaults:** `ansible/group_vars/all/` and each role's `defaults/main.yml`. `just settings` lists them ([where files are](../ansible/README.md#which-files-hold-what)).
- **Backups:** [backups.md](./backups.md).

## Every host

The `common` role runs on every host. It installs the base packages (curl, git, vim, jq, python3, ca-certificates, gnupg, python3-docker) and sets the timezone. It masks sleep and hibernate, so a host never suspends. It adds `ssh_authorized_keys` and the passwordless sudoers file, and sets where Docker stores its data (`docker_data_root`). It keeps the system log on disk across reboots (`journal_storage`, so a host that froze leaves a record in `journalctl -b -1`). `volatile` spares the root drive the writes.

<details>
<summary>Terminal tools (<code>terminal_tools_enabled: false</code> skips them)</summary>

- the Ghostty terminfo entry (a table that tells programs how a terminal draws text), so `TERM=xterm-ghostty` works over SSH.
- zellij, a terminal multiplexer (version and checksums in `versions.yml`).
- zoxide: `cd photos` jumps to the best-matching directory you use. `cd /path` and `cd ..` work as before. `cdi` picks from a list.
- bat: `cat` with syntax colours. eza: `ls` with colours (Debian 13 or Ubuntu 24.04 and later).
- zoxide, bat and eza live in the Ansible user's `~/.bashrc`, for interactive bash only: scripts, cron and `ssh host command` get the real `cd`, `cat` and `ls`, and `\cat` skips an alias.

</details>

## Services

- **Drive roles** (`fast`, `primary`, `backup`) come from entries in the host's `drives` ([storage.md](./storage.md)).
- **Caddy name** means `caddy_enabled` with at least one `caddy_private_domains` entry. The address is `<subdomain>.<first private domain>` (each `<key>_subdomain` is in [defaults-ports-and-names.yml](../ansible/group_vars/all/defaults-ports-and-names.yml)). Caddy builds its names on each deploy, so deploy a newly enabled service with Caddy: `just deploy <service>,caddy --limit <host>`. The [Homepage](#homepage) tile follows with its own deploy.
- **Behind the login:** a service marked "a Caddy name, `tinyauth_enabled`" has no login of its own. It takes the user Tinyauth names from a header ([Tinyauth](#tinyauth-login)), and the deploy stops without both.
- **Vault entries** go in `host_vars/<host>/vault.yml` (service secrets) or `group_vars/all/vault.yml` (shared): [ansible/README.md](../ansible/README.md#vault-secrets).

| Service | What it is | Role | Needs |
|---|---|---|---|
| [Immich](#immich) | Photo library (Google Photos alternative) | `roles/immich` | `primary` and `fast` drive roles, `vault_immich_db_password` |
| [Copyparty](#copyparty-accounts-and-volumes) | File sharing | `roles/copyparty` | `primary` and `fast` drive roles, `vault_copyparty_user`, `vault_copyparty_password`, `vault_copyparty_collab_users` with `copyparty_collab_enabled` |
| [Gitea](#gitea) | Git server | `roles/gitea` | `fast` drive role, `caddy_private_domains` or `gitea_root_url`, `vault_gitea_runner_token` optional |
| [Homebridge](#homebridge) | HomeKit bridge | `roles/homebridge` | `fast` drive role |
| [pics](#pics-photo-culling-and-sharing) | Photo culling and sharing | `roles/pics`, `roles/github_clone` | `fast` and `primary` drive roles, Copyparty, `pics_repo`, `pics_public_url`, `vault_github_read_token`, `vault_pics_password`, `vault_pics_secret_key`, `vault_pics_copyparty_password` ([private repo](#clone-a-private-github-repo)) |
| [Garage](#garage-s3) | S3-compatible object storage | `roles/garage` | `fast` drive role, a Caddy name, `tinyauth_enabled`, `vault_garage_rpc_secret`, `vault_garage_admin_token` |
| [Crafty](#crafty-minecraft-servers) | Minecraft servers | `roles/crafty` | `fast` drive role, RAM headroom |
| [ntfy](#ntfy-failure-alerts) | Push alerts for failed backups | `roles/ntfy` | `fast` drive role, `vault_ntfy_user`, `vault_ntfy_password`, `vault_ntfy_token` |
| [Tinyauth](#tinyauth-login) | Login page in front of browser-only services | `roles/tinyauth` | `fast` drive role, a Caddy name, `vault_tinyauth_users` |
| [Dozzle](#dozzle-container-logs) | Container logs in a browser | `roles/dozzle` | `fast` drive role, a Caddy name, `tinyauth_enabled` |
| [Scrutiny](#scrutiny-drive-health) | Drive health (SMART) dashboard | `roles/scrutiny` | `fast` drive role, a Caddy name, `tinyauth_enabled`, a drive that answers SMART |
| [Cloudflare Tunnel](#cloudflare-add-a-public-hostname) | Public hostnames without port forwarding | `roles/cloudflared` | `cloudflare_zones`, `cloudflared_ingress`, `vault_cloudflared_api_token`, `vault_cloudflared_account_id` |
| Tailscale ([networking](./networking.md)) | Private remote access, installed unless `tailscale_enabled: false` | `roles/tailscale` | Tailscale joined by hand |
| [Homepage](#homepage) | Start page with a tile per enabled service on every host | `roles/homepage` | none |
| [Dockge, Caddy](#ad-hoc-app-platform) | Dockge: web UI for your own compose stacks. Caddy: reverse proxy that names apps from container labels | `roles/dockge`, `roles/caddy` | `fast` drive role |
| Backups ([backups.md](./backups.md)) | Daily local and weekly cloud backups, a weekly check, a read-only status dashboard | `roles/backup`, `roles/backup_status` | [backups.md](./backups.md) |
| Connectivity watchdog ([networking](./networking.md#connectivity-watchdog)) | Reconnects the network when TCP stops working | `roles/connectivity_watchdog` | NetworkManager |
| Raspberry Pi tuning ([memory](./memory.md#memory-limits)) | Memory cgroup, so container memory limits work | `roles/pi` | a Raspberry Pi |
| zram swap ([memory](./memory.md#swap)) | Compressed swap in RAM | `roles/zram` | none |
| Direct Ethernet link ([networking](./networking.md#direct-ethernet-link)) | Cable from a Pi to a laptop for fast transfers | `roles/network` | none |

## Immich

Photo library with a machine-learning container. Photos are in `immich_photos_dir` (`bulk/immich`, primary drive), its Postgres data in `immich_postgres_dir` (`appdata/immich`, fast drive).

- Public access: a `cloudflared_ingress` entry pointing at `http://immich_server:2283`.
- `immich_sso_enabled: true` lets a Tinyauth login open Immich. The deploy sets it through Immich's API, which needs an API key ([Sign in with Tinyauth](./auth-reference.md#sign-in-with-tinyauth-oidc)).
- `roles/immich/files/dump.sh` dumps Postgres before each backup ([backups.md](./backups.md)).
- To move `immich_photos_dir` ([move one service's data](./storage.md#move-one-services-data)), copy the whole directory including the hidden `.immich` file in each subfolder (`library`, `thumbs`, `upload`, ...). Immich checks them at start and refuses to run without them ([system integrity](https://docs.immich.app/administration/system-integrity)).
- On a small host, lower the job concurrency and check the transcoding policy ([memory.md](./memory.md#immich)). Read the release notes before an update ([update images](../ansible/README.md#update-service-images)).

## Gitea

Git hosting with an optional Actions runner (it starts only when `vault_gitea_runner_token` is not empty).

- **Address:** `gitea_root_url` defaults to `https://<gitea_subdomain>.<first private domain>/`. A host with no `caddy_private_domains` must set it. Set it too for another address (a public name through a tunnel), in `group_vars/all/vars.yml` or the host's `vars.yml`: links, clone URLs and Tinyauth sign-in use it.
- **Names:** `gitea_domain` and `gitea_ssh_domain` default to the host in `gitea_root_url`. Set `gitea_ssh_domain` when SSH clones need another name (a Cloudflare tunnel carries only HTTP).
- Web UI on `gitea_port` (3000), SSH clones on `gitea_ssh_port` (2222). Public access: a `cloudflared_ingress` entry pointing at `http://gitea:3000`.
- `gitea_sso_enabled: true` lets a Tinyauth login open Gitea ([Sign in with Tinyauth](./auth-reference.md#sign-in-with-tinyauth-oidc)). `roles/gitea/files/dump.sh` dumps the database before each backup.

## Copyparty accounts and volumes

The deploy renders the config from `roles/copyparty/templates/copyparty.conf.j2` into `copyparty_config_dir`. The admin account is `copyparty_user` / `copyparty_password`. `copyparty_collab_enabled: true` adds `/collab`, a shared folder (`copyparty_collab_dir`, on the `primary` drive) for the friends in `vault_copyparty_collab_users`. The admin has access too. With it off there is no folder and no friend accounts.

`/` is the bulk volume. `/drives` shows plugged-in USB drives when `usb_automount_enabled: true` ([storage.md](./storage.md#plugged-in-usb-drives-drives)). `/fast` is a volume on the fast drive (`copyparty_fast_dir`) when `copyparty_fast_enabled: true`. It is worth it only when the fast and primary roles are on different drives (a `fast/` folder inside `files/` is hidden once it exists).

Apps that store files in Copyparty (pics) get an account named after the app and their own volumes at `/apps/<app>/<folder>`. The app's `copyparty` field in `services.yml` declares them (its comment says how). The volumes are not part of `copyparty_files_dir`, so the admin's listing does not show them. Every admin (`copyparty_user` and, with SSO, `copyparty_sso_admins`) has full access. `/apps/` opens read-only and lists each app's folders. Leave out the `d` permission unless the app must delete: without it Copyparty also refuses overwrites.

`copyparty_sso_enabled: true` puts the browser name (`<copyparty_subdomain>.<first private domain>`) behind the Tinyauth login. It adds to Copyparty's own passwords and does not replace them: the published port, the tunnel hostname, WebDAV, rclone and phone apps keep password logins.

- **Needs:** `tinyauth_enabled`, `caddy_enabled`, `vault_copyparty_idp_key` ([the header key](./glossary.md#names-logins-and-the-web); `just setup` makes it) and `copyparty_sso_admins` in the host's `vars.yml`.
- **Admins:** `copyparty_sso_admins` lists Tinyauth user names, matched exactly, with admin access to `/`, `/collab` and `/fast`. Every other signed-in user has only what `copyparty_extra_conf` grants. `service_users.copyparty` can limit who may open the page at all.

<details>
<summary>Give another app volumes, extra listeners (SFTP), one-folder users, share links</summary>

- **Give another app volumes:**
  1. add a `copyparty` field to its entry in `services.yml`.
  2. add a directory setting per volume to `defaults-data-dirs.yml` and list it in the entry's `data`, so backup and teardown cover it.
  3. name the password's vault variable in `copyparty.password` and put it in the vault.
  4. point the app at `/apps/<key>/<folder>` through Copyparty (pics: `COPYPARTY_ROOT`, `COPYPARTY_TRASH_ROOT` in its env file. The app does not mount the folders itself).

  `perms`: `r` read, `w` write, `m` move, `d` delete.

- **Any other Copyparty option** (an SFTP or FTP listener, extra accounts, more volumes) goes in `copyparty_extra_conf`, written to `extra.conf` beside the generated config. Accounts, groups and global options combine, but a volume (a `[/path]` section) may appear in only one file. So the generated `/`, `/collab` and `/fast` cannot be extended ([config reference](https://github.com/9001/copyparty#global-options)). `copyparty_extra_ports` publishes a listener's port as `"host:container"` strings (without one it is reachable only from other containers).

  ```yaml
  # An SFTP login for a sync client (WebDAV lacks the modtimes rclone needs)
  copyparty_extra_ports: ["3922:3922"]
  copyparty_extra_conf: |
    [global]
      sftp: 3922
      sftp-pw
    [accounts]
      syncer: {{ vault_copyparty_sftp_pass }}   # a vault entry you name yourself
    [/]
      accs:
        rwmd: syncer
  ```

- **A user with access to one folder only:** give them a volume of their own in `copyparty_extra_conf`, on a folder inside `/files` (or `/collab`, `/fast`). The user name is the Tinyauth user name:

  ```yaml
  copyparty_extra_conf: |
    [/shared]
      /files/shared
      accs:
        rw: friend      # r for read-only
  ```

- **Provider logins:** Tinyauth sets `Remote-User` for a GitHub or Google login too (the provider's username). With `TINYAUTH_OAUTH_*` providers on, no whitelisted account may have a provider username equal to a name in `copyparty_sso_admins`.
- **Share links** on the browser name ask for the Tinyauth login too (Copyparty expects the `/shares` prefix to be exempt, [shares](https://github.com/9001/copyparty#shares)). Hand links out on the published port or the tunnel hostname instead.

</details>

To change anything else, edit `copyparty.conf.j2` or the variables, then `just deploy copyparty`.

## Clone a private GitHub repo

Token: `vault_github_read_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how). A role calls `roles/github_clone` with `repo` and `dest`. The token reaches git through its environment, so it is not stored in `.git/config`. If it expires the clone step fails: make a new one and update the vault.

## pics: photo culling and sharing

The `pics` role clones the private repo in `pics_repo` and builds the image on the host (about 10 minutes on a Pi 5). Later runs rebuild only when the repo's commit changed. The role runs the app on `services`. It uses the Copyparty account `pics` and its volumes (`/apps/pics/photos` with no delete, `/apps/pics/trash` where it may delete). The build needs memory on top of the running services. On a 4 GB host deploy a changed `pics` while Immich and Crafty are idle, then check `free -m` and `journalctl -k | grep -i oom`.

1. Set `pics_repo` and `pics_public_url` (see `group_vars/all/vars.yml.example`) and add a `cloudflared_ingress` entry for the public hostname. Two ports: the owner app (cull UI, password-gated) on `pics_port` (8100, the only published port, `http://<pi>:<pics_port>`). The guest surface (share pages, portfolio, no owner routes) runs on `pics_public_port` (8001, inside Docker only). The tunnel points at `http://pics:<pics_public_port>`, so no `path` rule.
2. In the host's vault add `vault_pics_password` (12+ characters), `vault_pics_secret_key` (`openssl rand -base64 48`) and `vault_pics_copyparty_password`, without single quotes.
3. `just deploy copyparty,pics,cloudflared --limit <host>` (`copyparty` creates the account and volumes first).
4. Optional: sign in with Tinyauth (`pics_sso_enabled`, [auth-reference.md](./auth-reference.md#sign-in-with-tinyauth-oidc)). The password login and the importer's token stay, and pics' Caddy name is not behind Tinyauth: pics has its own login.

The database is in `pics_data_dir`, covered by the daily backup (the app also writes its own daily snapshots there). `teardown.yml -e only=pics` keeps all of pics' data unless `-e remove_data=true`, which also deletes the photos and trash.

## Cloudflare: add a public hostname

Add an entry to `cloudflared_ingress` in the host's `host_vars/<host>/vars.yml` (shape in `host_vars/vars.yml.example`), then `just deploy cloudflared`. Any host can run a tunnel: `cloudflared_enabled: true` and its own `cloudflared_ingress`.

- **Names:** the tunnel is `<host>-tunnel` unless you set `cloudflared_tunnel_name`. A hostname may appear in only one host's `cloudflared_ingress`. Hostnames not listed get a 404.
- **Settings:** `cloudflare_zones` in `group_vars/all/vars.yml`, and `vault_cloudflared_api_token` (DNS:Edit on each zone) and `vault_cloudflared_account_id` in `group_vars/all/vault.yml`.
- **Checked first:** a rule has only `hostname` and `service` (no `path:`), and its hostname matches exactly one domain in `cloudflare_zones`.
- **Remotely managed:** the deploy sets the tunnel's rules through the API from your machine. The host holds only a tunnel token (`/opt/services/cloudflared/token`). The deploy creates a missing tunnel.

### DNS records

Every record the role writes carries the comment `managed by simple-nas, tunnel <tunnel name>`, which is how a later deploy knows it is its own. Each deploy (and `--check`) prints a plan of creates, comments, repoints and deletes before changing anything.

<details>
<summary>What the deploy does to each kind of record</summary>

| Record | What the deploy does |
|---|---|
| Listed hostname, points at this tunnel | Keeps it (adds the comment if missing) |
| Listed hostname, has the comment or points at a deleted tunnel | Repoints it |
| Listed hostname, points at another existing tunnel, or is another type (A, MX, TXT) | Stops and names it. Delete it in the Cloudflare dashboard (DNS) if unused |
| Not listed, has the comment or points at this tunnel | Deletes it (also a hostname added in the Zero Trust dashboard. The next deploy deletes its rule too) |
| Not listed, points at a deleted tunnel, no comment | Only lists it in the plan. Delete it in the dashboard |

</details>

### Changing or replacing a tunnel

- **Name change** (the inventory key, or `cloudflared_tunnel_name`): the next deploy creates a tunnel under the new name. The DNS records still point at the old one, so it stops and names them. Delete the old tunnel in the dashboard (Zero Trust, Networks, Tunnels) and deploy again: the records move and the host gets the new token. Public hostnames are down for that moment.
- **A locally managed tunnel with that name:** the deploy stops. Use its migrate option in the dashboard, or delete the tunnel (public hostnames are offline until the next deploy).

## ntfy: failure alerts

A private [ntfy](https://docs.ntfy.sh/) server (`ntfy_enabled`) that a failed backup job writes to, so a failure reaches your phone instead of waiting in a log.

1. Make the secrets: a user and password (`vault_ntfy_user`, `vault_ntfy_password` in `host_vars/<host>/vault.yml`, from `openssl rand -base64 24`) and a token (`vault_ntfy_token` in `group_vars/all/vault.yml`, from `docker run --rm binwiederhier/ntfy token generate`). The deploy hashes the password into the compose file, so the vault holds the plain one.
2. On the ntfy host set `ntfy_enabled: true`, then `just deploy ntfy,caddy --limit <host>`. Then set `ntfy_alert_url` (below) on every host that should send alerts and `just deploy common --limit <host>`.
3. In the ntfy app add the server `http://<host-tailscale-name>:<ntfy_port>` with that user and password (`just edit vault --host <host>` shows them) and subscribe to `ntfy_topic` (default `alerts`). The phone must be on Tailscale.
4. Test: on the host `bash /opt/services/scripts/alert.sh "test"` and check the phone.

`ntfy_alert_url` is the setting that turns alerts on for every sender, in `group_vars/all/vars.yml` for every host or one host's `vars.yml`: the full URL of a topic. A host without it sends nothing. For this repo's ntfy it is the address from step 3 plus the topic (`http://<host-tailscale-name>:<ntfy_port>/alerts`). For another server, `https://ntfy.sh/<your-topic>` (token optional). One server serves the whole homelab. Scrutiny and pics send to the same topic with the same token and need no setting of their own (`just deploy scrutiny,pics --limit <host>` after changing it).

**One ntfy for each sender.** Three senders can alert: `host_alert_url` (backup jobs and the connectivity watchdog), `scrutiny_alert_url` and `pics_alert_url`. Each defaults to `ntfy_alert_url`, and its token (`host_alert_token`, `scrutiny_alert_token`, `pics_alert_token`) defaults to `vault_ntfy_token`. Set one to send only that sender elsewhere. Put its token in the vault under a name you choose and point the setting at it, so each URL travels with its own token. Backup alerts name no file contents, so they can go to a public topic while the other alerts stay on your own server:

```yaml
host_alert_url: "https://ntfy.sh/<a-long-random-topic-name>"
host_alert_token: ""                                          # ntfy.sh would refuse this repo's own token
```

It cannot report the host being down or a backup that never started (cron not running, host off).

<details>
<summary>An https address, the web page, how alert.sh works, iOS push</summary>

- With Caddy and a private domain, `https://ntfy.<host>.<your domain>` also works: set `ntfy_base_url` to it so links and iOS push use that address. In a browser, sign in there, subscribe to the topic and allow notifications (browsers notify only from `https://`. The plain `http://` address lists messages without a pop-up).
- The server denies everyone but that user and its token, even on the LAN. The page at `/alerts` loads without a login because it is only the app's shell. The compose file sets the user and token at every start. The data directory holds message history and the user database. `vault_ntfy_token` is optional: leave it out for a topic with no login.
- `alert.sh` (common role) runs when a backup cron job fails and when the [connectivity watchdog](./networking.md#connectivity-watchdog) recovers. It writes to the system log under its tag (`journalctl -t backup`, `-t connectivity`). It sends to ntfy only if `host_alert_url` is set (it defaults to `ntfy_alert_url`). A failed send times out after 15 seconds, so alerting cannot stall a backup.
- iOS push for a self-hosted server goes through ntfy.sh: `ntfy_ios_push: true` sends it the message ID and a hash of the topic URL, not the message. Android needs no relay.

</details>

## Tinyauth: login

[Tinyauth](https://tinyauth.app/docs/about/) (`tinyauth_enabled`) is a small login page. Caddy asks it about every request to a protected name ([forward auth](./glossary.md#names-logins-and-the-web)), so a service needs no login of its own. A browser without a session goes to `https://auth.<first private domain>`, and other clients get a 401. It suits a homelab, not setups that need roles and fine-grained permissions. Tinyauth and the protected services must run on the same host.

1. Make a login: add `name` and `password` to the list `vault_tinyauth_users` in `group_vars/all/vault.yml` (shape in `vault.yml.example`). The deploy hashes it, so the vault holds it in plain text. Another user is another list entry. Two-factor codes, GitHub or Google sign-in, Tailscale, sessions: [auth-reference.md](./auth-reference.md).
2. On the host set `tinyauth_enabled: true`. It needs Caddy with a private domain: the page only has that https name.
3. `just deploy tinyauth,caddy,homepage --limit <host>`.

- With `tinyauth_enabled`, every service with a Caddy name is behind the login except those marked `own_login: true` in `services.yml`. Immich, Gitea, Copyparty, pics and ntfy have apps, git, WebDAV and push clients that cannot log in through a web page. Tinyauth is its own login. Copyparty's browser name joins with `copyparty_sso_enabled`. To exempt another service, add `own_login: true` to its entry.
- Caddy serves a protected service under the first `caddy_private_domains` entry only ([why](./auth-reference.md#reach-a-protected-service-from-outside-the-tailnet)). A published host port is not protected.
- An app you run in Dockge opts in with one label, `caddy.import: tinyauth_forwarder`. A name in `caddy_sites` uses the same import ([Protect an app of your own](./auth-reference.md#protect-an-app-of-your-own)). [SilverBullet](https://silverbullet.md/) expects an authentication proxy, so leave its `SB_USER` unset.

### How an app joins

How an app gets past its own login, for this repo's services and your own, is in [Protect an app of your own](./auth-reference.md#protect-an-app-of-your-own). Dockge's switch is under [Ad-hoc app platform](#ad-hoc-app-platform). Crafty has none, so behind Tinyauth you sign in twice ([Crafty](#crafty-minecraft-servers)). Every deploy sets an app's own login in both directions: turning Tinyauth off, or publishing a port again, brings the app's own login back.

## Dozzle: container logs

[Dozzle](https://dozzle.dev/) (`dozzle_enabled`) shows every container's logs in a browser at `https://dozzle.<private domain>`. It runs read-only (no shell, no container actions), and Docker's log rotation (`docker_log_opts`) bounds what it keeps. The daily backup covers `dozzle_data_dir`, which holds per-user settings.

1. Set `dozzle_enabled: true` and `just deploy dozzle --limit <host>`.
2. `dozzle_port` is empty by default. Setting it publishes the page without a login, which Dozzle's docs warn against in forward-proxy mode.

## Scrutiny: drive health

[Scrutiny](https://github.com/Starosdev/scrutiny) (the Starosdev fork of AnalogJ/scrutiny, `scrutiny_enabled`) is a dashboard of every drive's SMART health and history, at `https://scrutiny.<private domain>`.

1. Set `scrutiny_enabled: true` and `just deploy scrutiny --limit <host>`.
2. The role reads the drive list from `smartctl --scan` at deploy time. Set `scrutiny_devices` to a list of device paths when that is wrong. SMART passes through a USB bridge only for some enclosures. When no drive answers the deploy stops with "no drive on this host answers SMART".
3. After plugging in or unplugging a drive, `just deploy scrutiny --limit <host>` again so the container gets the new list.
4. With `ntfy_alert_url` set ([ntfy](#ntfy-failure-alerts)), Scrutiny alerts there when a drive's SMART status fails, as often as `scrutiny_collect_schedule` reads the drives. A stopped Scrutiny sends nothing. Test: `docker exec scrutiny curl -X POST localhost:8080/api/health/notify`.

Scrutiny can show a drive as failed while `smartctl -H` says PASSED. It also fails an attribute, such as `Current_Pending_Sector` (197), that Backblaze's fleet data ties to a high failure rate. A failed drive sends a notification at every collection until you fix or override the cause. The fork's device page can override one attribute: Ignore, Force passed, or Acknowledge current value (the fork's README has the details). Acknowledge current value stops the alerts, and Scrutiny keeps it in its database (lost if you wipe that data). It fails the attribute again if its value changes. Every backup leaves out the InfluxDB history in `scrutiny_influx_dir`, and covers `scrutiny_config_dir`. What the counters mean: [storage.md](./storage.md#drive-damage-and-wear).

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret` and `vault_garage_admin_token` in the host's vault, then `just deploy garage,caddy --limit <host>`.

- The web UI is at `https://garage.<private domain>` (create buckets and access keys there). It holds Garage's admin token, so it has no host port and no tunnel name: never point a `cloudflared_ingress` entry at `garage-webui`. Any container on the `services` network can reach it.
- Apps connect with endpoint your tunnel hostname for the `garage-cors-proxy` container (a `cloudflared_ingress` entry), region `garage`, and the key pair from the UI. The S3 API also answers on the host at `garage_s3_port` (3900, LAN and tailnet) through the `garage-cors-proxy` container.
- Garage's metadata is root-owned, so the backup carries it as a dump (`garage-meta-*.tar.gz`): [Restore: Garage](./backups.md#restore-garage).
- Garage reads its cluster layout from `garage_meta_dir` (the object blocks are in `garage_blocks_dir`). A first deploy (empty meta dir) starts with `--single-node` so it auto-configures one node. Later starts omit the flag, which Garage requires once a layout exists (see the comment in `roles/garage/tasks/main.yml`).

## Crafty (Minecraft servers)

One container runs every server. All data is under `crafty_data_dir` (`bulk/crafty`: `servers/ backups/ logs/ config/ import/`).

- Panel: `https://<host-ip>:28443` (`crafty_port`, self-signed certificate). The first admin password is in `<crafty_data_dir>/config/default-creds.txt` (Crafty makes it and has no setting for it). Behind Tinyauth it is the second login, so change it in the panel to something short, then delete the file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575). Set it when creating the server.
- `crafty_memory_limit` caps all servers combined. On a Raspberry Pi Docker enforces it once the memory cgroup is on ([memory.md](./memory.md#memory-limits)). It competes with Immich on a small host: size the two so they leave room for the rest.
- Not behind Cloudflare Tunnel: players join over the LAN, a router port-forward of the game port, or Tailscale. Docker publishes the panel and game ports on all interfaces, so do not forward the panel port.
- The live `servers/` directory is in the daily backup. Crafty's own `backups/` archives are not ([backups.md](./backups.md#what-is-backed-up-where)).

## Homebridge

Runs with `network_mode: host` (HomeKit discovery needs it), so it is not on `services` and not in `cloudflared_ingress`. The role only deploys the container. The image creates `config.json` and `auth.json` on first start. Log in with `admin`/`admin` and change the password at once. You set the HomeKit PIN and plugins in the UI, and they persist across deploys.

- Remote Apple Home access needs a HomeKit hub (Apple TV or HomePod) on your LAN. Tailscale does not replace it.
- The admin UI is at `http://<tailscale-ip>:8581` (plain HTTP).

## Homepage

A start page (`homepage_enabled`, [Homepage](https://gethomepage.dev)) for all your servers. Run it on one host: it shows a group of tiles for every host in the inventory. One tile per service that host has on and that has a host port or a Caddy name. A green or red dot shows whether the page answers.

- With `tinyauth_enabled` and `caddy_private_domains` it is at `https://<homepage_subdomain>.<first private domain>` behind the login and publishes no port. Without Tinyauth, set `homepage_port` (for example 3001) and open `http://<homepage_host>:<homepage_port>`. Anyone on the network can then open it.
- **The address must match.** `homepage_host` defaults to the address Ansible reaches the host at (the full tailnet name). The page also answers on the inventory name. Any other address gets a host validation error: set `homepage_host` to the one you use.
- A tile links to the service's `https://` name when that host runs Caddy with `caddy_private_domains` and the service has a subdomain ([caddy-reference.md](./caddy-reference.md#names-for-apps-caddy_private_domains)). Otherwise it links to that host's `ansible_host` and port. After switching a service on or off elsewhere, `just deploy homepage --limit <homepage host>`.
- Tiles are the `services.yml` entries that have an `icon` (add an entry to add a tile), and Caddy and Cloudflare Tunnel have none. `homepage_links` adds your own tiles in a "Links" group: a public hostname, a machine outside the inventory, an app from Dockge (format in `roles/homepage/defaults/main.yml`).
- Ansible writes every file Homepage reads (tiles, title, colours), so a deploy resets edits to them: change them in the repo. Homepage's own password login and live-number widgets are not set up on purpose: Tinyauth is the login and the page holds only links.

## Ad-hoc app platform

**Dockge** (`dockge_enabled`) is a web UI at `http://<host>:<dockge_port>` (5001) over `compose.yaml` stacks in `dockge_stacks_dir` (`<fast drive>/stacks`). Create the account on first visit. **Caddy** (`caddy_enabled`) gives apps names from container labels ([caddy-reference.md](./caddy-reference.md)). With `caddy_private_domains` set, names under your own domain get Let's Encrypt certificates. Without it, apps are reachable over Tailscale at `http://<host>:<port>`. A stack that wants a name or a tunnel route joins the `services` network (the ingress `service` is `http://<container_name>:<port>`). Public access is off unless the host sets `cloudflared_enabled: true` ([Cloudflare](#cloudflare-add-a-public-hostname)).

- **Dockge's login.** With a `dockge_port` set, the published port skips Caddy and Tinyauth, so Dockge keeps its own login. `dockge_port: ""` makes the Tinyauth login its only one. The deploy needs the first account before it can switch Dockge's login off, so create it, then deploy again. Then every name that reaches Dockge must import `tinyauth_forwarder`, including one in `caddy_sites`.
- **Risk.** With its login off, any container on the `services` network can reach Dockge, and so the Docker socket ([glossary](./glossary.md#drives-and-docker)), without a password. Keep untrusted containers off that network, or leave `dockge_port` set. Anyone who can set a label on a container can also publish a route through Caddy.
- **If Tinyauth is down or removed**, Dockge has no way in from a browser. Use ssh, or set `tinyauth_enabled: false` (or publish `dockge_port`) and `just deploy dockge --limit <host>` to get its own login back.
- **Ansible deploys Dockge only.** The stacks are yours and stay when you delete Dockge. A stack keeps state in bind mounts ([storage.md](./storage.md#dockers-own-storage)), so deleting a stack is deleting its directory. Stacks, Dockge's data and Caddy's data sit on the `fast` drive and the host's backup covers them.
- **Removal:** `just teardown <host> -e only=dockge,caddy,cloudflared` ([teardown](../ansible/README.md#disable-or-remove-a-service)).
