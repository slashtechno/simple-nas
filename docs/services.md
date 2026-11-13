# Service notes

Every service below is off until a host sets `<name>_enabled: true` in `ansible/host_vars/<host>/vars.yml`. Four things are on by default: `storage_enabled`, `tailscale_enabled`, `pi_enabled: auto` (it acts only on a Raspberry Pi) and `terminal_tools_enabled`. This page lists what each service needs and the setup beyond the flag.

- **Deploy one:** `just deploy <tag>` from `ansible/` (tag = role name).
- **Settings and defaults:** `ansible/group_vars/all/` and each role's `defaults/main.yml`. `just settings` lists them ([where files are](../ansible/README.md#which-files-hold-what)).
- **Backups:** [backups.md](./backups.md).

## Every host

The `common` role runs on every host. It:

- installs the base packages (curl, git, vim, jq, python3, ca-certificates, gnupg, python3-docker) and sets the timezone;
- masks sleep and hibernate, so the host never suspends;
- adds your `ssh_authorized_keys` and a passwordless sudoers file;
- sets where Docker keeps its data (`docker_data_root`);
- keeps the system log on disk across reboots, so a host that froze leaves a record in `journalctl -b -1`. Set `journal_storage: volatile` to keep the log in RAM instead and spare the root drive the writes.

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
- **Behind the login:** a service whose "Needs" lists `tinyauth_enabled` has no login of its own. Tinyauth names the user in a header ([Tinyauth](#tinyauth-login)), and the deploy stops without both.
- **Vault entries** go in `host_vars/<host>/vault.yml` (service secrets) or `group_vars/all/vault.yml` (shared): [ansible/README.md](../ansible/README.md#vault-secrets).

| Service | What it is | Role | Needs |
|---|---|---|---|
| [Immich](#immich) | Photo library (Google Photos alternative) | `roles/immich` | `primary` and `fast` drive roles, `vault_immich_db_password` |
| [Copyparty](#copyparty-folders-and-logins) | File sharing | `roles/copyparty` | `primary` and `fast` drive roles, `vault_copyparty_accounts` with at least one `admin: true` login, `copyparty_folders` for folders besides the default `files` |
| [Gitea](#gitea) | Git server | `roles/gitea` | `fast` drive role, `caddy_private_domains` or `gitea_root_url`, `vault_gitea_runner_token` optional |
| [Homebridge](#homebridge) | HomeKit bridge | `roles/homebridge` | `fast` drive role |
| [pics](#pics-photo-culling-and-sharing) | Photo culling and sharing | `roles/pics`, `roles/github_clone` | `fast` and `primary` drive roles, Copyparty, `pics_repo`, `pics_public_url`, `vault_github_read_token`, `vault_pics_password`, `vault_pics_secret_key`, `vault_pics_copyparty_password` ([private repo](#clone-a-private-github-repo)) |
| [Garage](#garage-s3) | S3-compatible object storage | `roles/garage` | `fast` and `primary` drive roles, a Caddy name, `tinyauth_enabled`, `vault_garage_rpc_secret`, `vault_garage_admin_token` |
| [Crafty](#crafty-minecraft-servers) | Minecraft servers | `roles/crafty` | `primary` drive role, RAM headroom |
| [ntfy](#ntfy-failure-alerts) | Push alerts for failed backups | `roles/ntfy` | `fast` drive role, `vault_ntfy_user`, `vault_ntfy_password`, `vault_ntfy_token` |
| [Tinyauth](#tinyauth-login) | Login page in front of browser-only services | `roles/tinyauth` | `fast` drive role, a Caddy name, `vault_tinyauth_users` |
| [Dozzle](#dozzle-container-logs) | Container logs in a browser | `roles/dozzle` | `fast` drive role, a Caddy name, `tinyauth_enabled` |
| [Scrutiny](#scrutiny-drive-health) | Drive health (SMART) dashboard | `roles/scrutiny` | `fast` drive role, a Caddy name, `tinyauth_enabled`, a drive that answers SMART |
| [Cloudflare Tunnel](#cloudflare-add-a-public-hostname) | Public hostnames without port forwarding | `roles/cloudflared` | `cloudflare_zones`, `cloudflared_ingress`, `vault_cloudflared_api_token`, `vault_cloudflared_account_id` |
| Tailscale ([networking](./networking.md)) | Private remote access, installed unless `tailscale_enabled: false` | `roles/tailscale` | Tailscale joined by hand |
| [Homepage](#homepage) | Start page with a tile per enabled service on every host | `roles/homepage` | `tinyauth_enabled` and `caddy_enabled`, or `homepage_port` |
| [Dockge, Caddy](#ad-hoc-app-platform) | Dockge: web UI for your own compose stacks. Caddy: reverse proxy that names apps from container labels | `roles/dockge`, `roles/caddy` | `fast` drive role |
| [Unlock page](./encryption.md#unlock-page) | Show, unlock and lock the encrypted folders from a browser | `roles/unlock_page` | `tinyauth_enabled`, a Caddy name, `encrypted_folders` |
| Backups ([backups.md](./backups.md)) | Daily local and weekly cloud backups, a weekly check, a read-only status dashboard | `roles/backup`, `roles/backup_status` | [backups.md](./backups.md) |
| Connectivity watchdog ([networking](./networking.md#connectivity-watchdog)) | Reconnects the network when TCP stops working | `roles/connectivity_watchdog` | NetworkManager |
| Raspberry Pi tuning ([memory](./memory.md#memory-limits)) | Memory cgroup, so container memory limits work | `roles/pi` | a Raspberry Pi |
| zram swap ([memory](./memory.md#swap)) | Compressed swap in RAM | `roles/zram` | none |
| Direct Ethernet link ([networking](./networking.md#direct-ethernet-link)) | Cable from a host to a laptop for fast transfers | `roles/network` | none |

## Immich

Photo library with a machine-learning container. Photos are in `immich_photos_dir` (`appdata/immich/photos`, primary drive), its Postgres data in `immich_postgres_dir` (`appdata/immich/postgres`, fast drive).

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

## Copyparty folders and logins

Copyparty serves each folder in `copyparty_folders` (the host's `vars.yml`) at `/<name>`. A login in `vault_copyparty_accounts` (the vault) opens the folders that name it. `/` lists only the folders a login may open, unless one folder has [`root: true`](#add-a-folder-or-a-login). The default is one folder, `files`, in `<copyparty_shared_dir>/files` for the admins.

### Add a folder or a login

1. Add the folder to `copyparty_folders`, with `access: {login: letters}`.
2. Add each new login to `vault_copyparty_accounts` (shape: `host_vars/vault.yml.example`). Add `admin: true` for an admin.
3. Run `just deploy copyparty --limit <host>`.

```yaml
copyparty_folders:
  files: {}                                                           # /files, for the admins only
  collab: {access: {friend1: rwmd, friend2: rwmd}}                    # /collab
  team: {access: {friend2: A, friend1: r}}                            # friend1 can only read
  pics-photos: {dir: "{{ pics_photos_dir }}", access: {pics: rwm}}    # an app (see pics)
```

- **Letters:** `r` read, `w` write, `m` move, `d` delete. `A` is all four, plus `a` (Copyparty's folder admin) and dotfiles. Copyparty's docs explain `g`, `G` and `h`.
- **Admin** (`admin: true`): full access to every folder, so no `access` entry. On `/drives`: read-only, or full with `usb_automount_writable`.
- **Person or app:** only the folders that name it in `access`.
- **Tinyauth-only login:** no `pass` (needs `copyparty_sso_enabled`). It has no password login.
- **Name:** letters, digits, `-` and `_`, not `drives` or `shares` (Copyparty's own).
- **`root: true`:** serves that folder at `/` instead of `/<name>`. Only one folder may have it, and not a pics folder. A folder inside it named like another folder, `shares` or `drives` is hidden.
- **`dir`:** an absolute path on the host. The default is `<copyparty_shared_dir>/<name>`, on the `primary` drive. The deploy creates it. Use the `primary` or `fast` drive: the local backup covers those. When a folder uses the default `dir`, teardown with `remove_data` deletes `copyparty_shared_dir` and every folder inside it. It keeps a `dir` outside it, unless a service lists that `dir` as its data.
- **Names in the vault:** write `access: "{{ vault_copyparty_collab_access }}"` and put the mapping in the vault. The tracked file then holds no user names.
- **No `d` for an app:** without `d`, Copyparty also refuses to overwrite a file.
- **Your own list replaces the default whole:** write `files: {}` in it to keep the admins' folder.
- **No folders:** `copyparty_folders: {}` serves `/shares` and, with `usb_automount_enabled`, `/drives`.

A symlink that someone with shell access puts in a folder shares the target. Uploads and WebDAV create only regular files.

### Logins and Tinyauth

Copyparty keeps its own passwords. Tinyauth stores only password hashes, and Copyparty cannot check a hash. The passwords work on Copyparty's login page, on WebDAV and in apps. Caddy serves the web address `<copyparty_subdomain>.<domain>`, and Tinyauth does not guard it until you set `copyparty_sso_enabled`. `service_users.copyparty` needs that setting too: the deploy stops without it ([who can use it](./auth-reference.md#who-may-use-what)).

`copyparty_sso_enabled: true` puts that web address behind the Tinyauth login. The host port and the tunnel hostname still use Copyparty's passwords. Which login applies depends on where you connect:

| You connect to | Login |
|---|---|
| The host port (`http://<tailnet name>:3923`), or the tunnel hostname | Copyparty password (an account with a `pass`) |
| The Caddy name, SSO off | Copyparty password |
| The Caddy name, SSO on, in a browser | Tinyauth login page. Copyparty then uses the Tinyauth user name |
| The Caddy name, SSO on, from WebDAV, rclone or a script | The Tinyauth user name and password, sent as HTTP Basic auth. It fails for a user with a `totp` secret, and Copyparty-only passwords are refused here |

Tinyauth answers every request on the Caddy name before Copyparty sees it. So a client that needs two-factor or a Copyparty-only password uses the host port instead ([two-factor limit](./auth-reference.md#two-factor-codes-totp)). A user with no `pass` signs in only through Tinyauth.

- **Needs:** `tinyauth_enabled`, `caddy_enabled` and `vault_copyparty_idp_key` ([the header key](./glossary.md#names-logins-and-the-web); `just setup` makes it).
- **Who is who:** the Tinyauth user name must equal the Copyparty `user`, character for character. Copyparty then gives that login's folders after the Tinyauth sign-in.
- **No password:** leave out `pass` for a person who uses only the Tinyauth sign-in. The deploy stops if that `user` is not a Tinyauth user name.
- **Not in the list:** a Tinyauth user with no entry in `vault_copyparty_accounts` sees no folder.

<details>
<summary>Give an app a folder, more drives, extra listeners (SFTP), share links</summary>

- **Give an app a folder** (the same steps for any app that stores files in Copyparty):
  1. Add a data directory setting to `defaults-data-dirs.yml`. List it in `data` of the app's entry in `services.yml`. Backup and teardown then include it.
  2. Add the folder to `copyparty_folders` with `dir` set to that setting.
  3. Add the app's login to `vault_copyparty_accounts`. Put its password in the vault.
  4. Point the app at `/<folder>` through Copyparty. The app does not mount the folder.
- **Give a login another folder:** add the login to the `access` of that folder, then deploy. Point the app at `/<folder>`. `access` decides only what a login can open.
- **Any other Copyparty option** (an SFTP or FTP listener, global options, more volumes) goes in `copyparty_extra_conf`. The deploy writes it to `extra.conf` beside the generated config. Accounts, groups and global options combine. A volume (a `[/path]` section; `[/]` is taken when a folder has `root: true`) can appear in only one file, so you cannot extend a folder from `copyparty_folders` there ([config reference](https://github.com/9001/copyparty#global-options)). `copyparty_extra_volumes` mounts more host folders. `copyparty_extra_ports` publishes a listener port as `"host:container"` strings. Without it, only other containers reach the listener.

  ```yaml
  # An SFTP listener for a sync client (WebDAV lacks the modtimes rclone needs).
  # The login `syncer` and its folder come from vault_copyparty_accounts and copyparty_folders.
  copyparty_extra_ports: ["3922:3922"]
  copyparty_extra_conf: |
    [global]
      sftp: 3922
      sftp-pw
  ```

- **Provider logins:** Tinyauth sets `Remote-User` for a GitHub or Google login too (the name at the provider). With `TINYAUTH_OAUTH_*` providers on, a provider name must not equal a `user` in `vault_copyparty_accounts`.
- **Share links** on the web address ask for the Tinyauth login too. Copyparty expects the `/shares` prefix to be exempt ([shares](https://github.com/9001/copyparty#shares)). Give out links from the host port or the tunnel hostname instead.

</details>

### Show a read-only host folder

`copyparty_folders` covers most needs. For a read-only mount, use `copyparty_extra_volumes` and `copyparty_extra_conf`:

```yaml
copyparty_extra_volumes:                  # "host path:path in the container[:ro]"
  - "/mnt/backup/service-dumps:/backup:ro"
copyparty_extra_conf: |
  [/backup]
    /backup
    accs:
      A: yourusername                     # your own volumes do not give admin access: name each admin
```

- **One folder only:** mount the folder, not the whole drive. A drive root can hold `appdata` (database passwords, tokens) and the restic repository. Never give a volume write access to either.
- **Locked folders:** a folder in an [encrypted folder](./encryption.md) looks empty until you unlock it. The unlock restarts Copyparty.

To change anything else, edit `copyparty.conf.j2` or the settings, then run `just deploy copyparty`.

## Clone a private GitHub repo

Token: `vault_github_read_token`, a read-only fine-grained token scoped to the one repo (`vault.yml.example` says how). A role calls `roles/github_clone` with `repo` and `dest`. The token reaches git through its environment, so it is not stored in `.git/config`. If it expires the clone step fails: make a new one and update the vault.

## pics: photo culling and sharing

The `pics` role clones the private repo in `pics_repo` and builds the image on the host (about 10 minutes on a Pi 5). Later runs rebuild only when the repo's commit changed. The role runs the app on `services`. It uses the Copyparty login `pics` and two folders: `/pics-photos` (no delete) and `/pics-trash` (delete allowed). The build needs memory on top of the running services. On a 4 GB host deploy a changed `pics` while Immich and Crafty are idle, then check `free -m` and `journalctl -k | grep -i oom`.

1. Set `pics_repo` and `pics_public_url` (see `group_vars/all/vars.yml.example`).
2. Add a `cloudflared_ingress` entry for the public hostname, pointing at `http://pics:<pics_public_port>` (8001, inside Docker only). It serves the guest pages (shares, portfolio) and no owner routes, so it needs no `path` rule. The owner app (cull UI, password-gated) is on the host port `pics_port` (8100): `http://<host>:<pics_port>`.
3. Add `vault_pics_password` (12+ characters), `vault_pics_secret_key` (`openssl rand -base64 48`) and `vault_pics_copyparty_password` to the host's vault, without single quotes. Then add the login `pics` to `vault_copyparty_accounts` with `pass: "{{ vault_pics_copyparty_password }}"`.
4. Add two folders to `copyparty_folders` in the host's `vars.yml`, as in the [example](#add-a-folder-or-a-login). Add `pics-photos` with `dir: "{{ pics_photos_dir }}"` and `access: {pics: rwm}`. Add `pics-trash` with `dir: "{{ pics_trash_dir }}"` and `access: {pics: rwmd}`. The deploy stops when a folder or a `dir` is not valid.
5. Run `just deploy copyparty,pics,cloudflared --limit <host>` (`copyparty` creates the login and folders first).
6. Optional: sign in with Tinyauth (`pics_sso_enabled`, [auth-reference.md](./auth-reference.md#sign-in-with-tinyauth-oidc)). The password login and the importer's token stay, and pics' Caddy name is not behind Tinyauth: pics has its own login.

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

1. Make the secrets in the vault: a user name you choose (`vault_ntfy_user`) and a password from `openssl rand -base64 24` (`vault_ntfy_password`), both in `host_vars/<host>/vault.yml`, and a token (`vault_ntfy_token` in `group_vars/all/vault.yml`, from `docker run --rm binwiederhier/ntfy token generate`). The deploy hashes the password into the compose file, so the vault holds the plain one.
2. On the ntfy host set `ntfy_enabled: true`, then `just deploy ntfy,caddy --limit <host>`. Then name the topic and pick who sends to it (below).
3. In the ntfy app add the server `http://<tailnet name>:<ntfy_port>` with that user and password (`just edit vault --host <host>` shows them) and subscribe to `ntfy_topic` (default `alerts`). The phone must be on Tailscale.
4. Test: on the host `/opt/services/scripts/alert.sh system test "test alert" "hello"` and check the phone.

**Where alerts go.** `ntfy_destinations` maps a name to a topic. Each has a `url` (the full address of the topic, required) and an optional `token` (the login). Put it in `group_vars/all/vars.yml` to share it between hosts; a host's own `ntfy_destinations` replaces it whole, so list every name that host needs. Then each sender picks a destination by name. A sender with `""` sends nothing, and that is the default for all four:

```yaml
ntfy_destinations:
  home: {url: "http://<tailnet name>:<ntfy_port>/alerts", token: "{{ vault_ntfy_token }}"}   # this repo's ntfy
  public: {url: "{{ vault_ntfy_public_url }}"}                                                        # ntfy.sh: no login
system_alert_to: home        # failed backup jobs and the connectivity watchdog
unlock_alert_to: home        # the locked-folder alert
scrutiny_alert_to: home      # drive health alerts
pics_alert_to: public        # pics' own alerts, to a different topic
```

- **Turn a sender off:** set its `*_alert_to` to `""`. Write `""`, not an empty value.
- **Public server:** a topic name on `ntfy.sh` works like a password.
  - Keep the address in the vault (`group_vars/all/vault.yml`) and write `"{{ vault_<name> }}"` as the `url`.
  - Leave out `token`. `ntfy.sh` has no login, and this repo's own token must not go there. This repo's own ntfy has no anonymous access, so a destination for it needs the token.
  - The deploy writes the address into the sender's file on the host, where anyone on the host can read it. `alert.sh` and the token files are in no backup, but Scrutiny's compose file and pics' `pics.env` are in the cloud one.
- **A name that is not in `ntfy_destinations`, or a destination with no `url`,** stops the deploy and names the setting.
- **A `vault_` name** in a destination must exist on the hosts that send to it.
- **After a change** run `just deploy common,scrutiny,pics,encryption --limit <host>`. Each role writes the address into its own script or file. After you change `vault_ntfy_token`, also run `just deploy ntfy` so the server accepts the new token.
- **Use https:// or a tailnet address.** The token travels in the request.

It cannot report the host being down or a backup that never started (cron not running, host off).

<details>
<summary>An https address, the web page, how alert.sh works, iOS push</summary>

- With Caddy and a private domain, `https://ntfy.<host>.<your domain>` also works: set `ntfy_base_url` to it so links and iOS push use that address. In a browser, sign in there, subscribe to the topic and allow notifications (browsers notify only from `https://`. The plain `http://` address lists messages without a pop-up).
- The server denies everyone but that user and its token, even on the LAN. The page at `/alerts` loads without a login because it is only the app's shell. The compose file sets the user and token at every start. The data directory holds message history and the user database.
- `alert.sh <sender> <log tag> <title> <message>` (common role) runs when a backup cron job fails, when the [connectivity watchdog](./networking.md#connectivity-watchdog) recovers (sender `system`), and at boot with a locked folder (sender `unlock`, from `unlock.sh`). It writes to the system log under the tag (`journalctl -t backup`, `-t connectivity`, `-t unlock`). It sends to ntfy only if that sender's `*_alert_to` names a destination. Each sender's token is a file in `alert_token_dir`; no backup copies them or the script. A failed send times out after 15 seconds, so alerting cannot stall a backup.
- iOS push for a self-hosted server goes through ntfy.sh, so `ntfy_ios_push` is on by default: ntfy.sh gets the message ID and a hash of the topic URL, not the message. Set it to `false` to send nothing to ntfy.sh; an iPhone then shows messages only when the app is refreshed. Android needs no relay. After a change, re-add the subscription in the iOS app.

</details>

## Tinyauth: login

[Tinyauth](https://tinyauth.app/docs/about/) (`tinyauth_enabled`) is a small login page. Caddy asks it about every request to a protected name ([forward auth](./glossary.md#names-logins-and-the-web)), so a service needs no login of its own. A browser without a session goes to `https://auth.<first private domain>`, and other clients get a 401. It suits a homelab, not setups that need roles and fine-grained permissions. Tinyauth and the protected services must run on the same host.

1. Make a login: add `name` and `password` to the list `vault_tinyauth_users` in `group_vars/all/vault.yml` (shape in `vault.yml.example`). The deploy hashes it, so the vault holds it in plain text. Another user is another list entry. Two-factor codes, GitHub or Google sign-in, Tailscale, sessions: [auth-reference.md](./auth-reference.md).
2. On the host set `tinyauth_enabled: true`. It needs Caddy with a private domain: the page only has that https name.
3. `just deploy tinyauth,caddy,homepage --limit <host>`.

- With `tinyauth_enabled`, every service with a Caddy name is behind the login except those marked `own_login: true` in `services.yml`. A service marked that way has apps, git, WebDAV or push clients that cannot log in through a web page, so it keeps its own login. Tinyauth is its own login. Copyparty's web address joins with `copyparty_sso_enabled`. To exempt another service, add `own_login: true` to its entry.
- Caddy serves a protected service under the first `caddy_private_domains` entry only ([why](./auth-reference.md#reach-a-protected-service-from-outside-the-tailnet)). A host port is not protected.
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
4. With `scrutiny_alert_to` set ([ntfy](#ntfy-failure-alerts)), Scrutiny alerts there when a drive's SMART status fails, as often as `scrutiny_collect_schedule` reads the drives. A stopped Scrutiny sends nothing. Test: `docker exec scrutiny curl -X POST localhost:8080/api/health/notify`.

<details>
<summary>Scrutiny shows a failed drive but <code>smartctl -H</code> says PASSED</summary>

Scrutiny also fails an attribute such as `Current_Pending_Sector` (197) that Backblaze's fleet data ties to a high failure rate. A failed drive sends a notification at every collection until you fix or override the cause.

- The fork's device page can override one attribute: Ignore, Force passed, or Acknowledge current value (the fork's README has the details).
- Acknowledge current value stops the alerts. Scrutiny keeps it in its database, and fails the attribute again if its value changes.
- Backups cover `scrutiny_config_dir` and leave out the InfluxDB history in `scrutiny_influx_dir`.
- What the counters mean: [storage.md](./storage.md#drive-damage-and-wear).

</details>

## Garage (S3)

Set `garage_enabled: true`, fill in `vault_garage_rpc_secret` and `vault_garage_admin_token` in the host's vault, then `just deploy garage,caddy --limit <host>`.

- The web UI is at `https://garage.<private domain>` (create buckets and access keys there). It holds Garage's admin token, so it has no host port and no tunnel name: never point a `cloudflared_ingress` entry at `garage-webui`. Any container on the `services` network can reach it.
- Apps connect to the hostname of the `garage-cors-proxy` container's `cloudflared_ingress` entry, with region `garage` and the key pair from the UI. The S3 API also answers on the host at `garage_s3_port` (3900, LAN and tailnet) through the `garage-cors-proxy` container.
- Garage's metadata is root-owned, so the backup carries it as a dump (`garage-meta-*.tar.gz`): [Restore: Garage](./backups.md#restore-garage).

## Crafty (Minecraft servers)

One container runs every server. All data is under `crafty_data_dir` (`appdata/crafty` on the primary drive: `servers/ backups/ logs/ config/ import/`).

- Panel: `https://<host-ip>:28443` (`crafty_port`, self-signed certificate). The first admin password is in `<crafty_data_dir>/config/default-creds.txt` (Crafty makes it and has no setting for it). Behind Tinyauth it is the second login, so change it in the panel to something short, then delete the file.
- Each server needs a port inside `crafty_mc_ports` (default 25565-25575). Set it when creating the server.
- `crafty_memory_limit` caps all servers combined. On a Raspberry Pi Docker enforces it once the memory cgroup is on ([memory.md](./memory.md#memory-limits)). It competes with Immich on a small host: size the two so they leave room for the rest.
- Not behind Cloudflare Tunnel: players join over the LAN, a router port-forward of the game port, or Tailscale. Docker publishes the panel and game ports on all interfaces, so do not forward the panel port.
- The live `servers/` directory is in the daily backup. Crafty's own `backups/` archives are not ([backups.md](./backups.md#what-is-backed-up-where)).

## Homebridge

Runs with `network_mode: host` (HomeKit discovery needs it), so it is not on `services` and not in `cloudflared_ingress`. The role only deploys the container. The image creates `config.json` and `auth.json` on first start. Log in with `admin`/`admin` and change the password at once. You set the HomeKit PIN and plugins in the UI, and they persist across deploys.

- Remote Apple Home access needs a HomeKit hub (Apple TV or HomePod) on your LAN. Tailscale does not replace it.
- The admin UI is at `http://<tailnet name>:8581` (plain HTTP).

## Homepage

A start page (`homepage_enabled`, [Homepage](https://gethomepage.dev)) for all your servers. Run it on one host: it shows a group of tiles for every host in the inventory. One tile per service that host has on and that has a host port or a Caddy name. A green or red dot shows whether the page answers.

- With `tinyauth_enabled`, `caddy_enabled` and `caddy_private_domains` it is at `https://<homepage_subdomain>.<first private domain>` behind the login and publishes no port. Without Tinyauth, set `homepage_port` (for example 3001) and open `http://<homepage_host>:<homepage_port>`. Anyone on the network can then open it.
- **The address must match.** `homepage_host` defaults to the address Ansible reaches the host at (`ansible_host`). With `homepage_port` set, the page also answers on the inventory name. Any other address gets a host validation error: set `homepage_host` to the one you use.
- A tile links to the service's `https://` name when that host runs Caddy with `caddy_private_domains` and the service has a subdomain ([caddy-reference.md](./caddy-reference.md#names-for-apps-caddy_private_domains)). Otherwise it links to that host's `ansible_host` and port. After switching a service on or off elsewhere, `just deploy homepage --limit <homepage host>`.
- Tiles are the `services.yml` entries that have an `icon` (add an entry to add a tile), and Caddy and Cloudflare Tunnel have none. `homepage_links` adds your own tiles in a "Links" group: a public hostname, a machine outside the inventory, an app from Dockge (format in `roles/homepage/defaults/main.yml`).
- Ansible writes every file Homepage reads, so a deploy resets edits to them: change them in the repo. There is no Homepage login or widget on purpose: Tinyauth is the login and the page holds only links.

## Ad-hoc app platform

**Dockge** (`dockge_enabled`) is a web UI at `http://<host>:<dockge_port>` (5001) over `compose.yaml` stacks in `dockge_stacks_dir` (`<fast drive>/stacks`). Create the account on first visit. **Caddy** (`caddy_enabled`) gives apps names from container labels ([caddy-reference.md](./caddy-reference.md)). With `caddy_private_domains` set, names under your own domain get Let's Encrypt certificates. Without it, apps are reachable over Tailscale at `http://<host>:<port>`. A stack that wants a name or a tunnel route joins the `services` network (the ingress `service` is `http://<container_name>:<port>`). Public access is off unless the host sets `cloudflared_enabled: true` ([Cloudflare](#cloudflare-add-a-public-hostname)).

- **Dockge's login.** With a `dockge_port` set, the host port skips Caddy and Tinyauth, so Dockge keeps its own login. `dockge_port: ""` makes the Tinyauth login its only one. The deploy needs the first account before it can switch Dockge's login off, so create it, then deploy again. Then every name that reaches Dockge must import `tinyauth_forwarder`, including one in `caddy_sites`.
- **Risk.** With its login off, any container on the `services` network can reach Dockge, and so the Docker socket ([glossary](./glossary.md#drives-and-docker)), without a password. Keep untrusted containers off that network, or leave `dockge_port` set. Anyone who can set a label on a container can also publish a route through Caddy.
- **If Tinyauth is down or removed**, Dockge has no way in from a browser. Use ssh, or set `tinyauth_enabled: false` (or publish `dockge_port`) and `just deploy dockge --limit <host>` to get its own login back.
- **Ansible deploys Dockge only.** The stacks are yours and stay when you delete Dockge. A stack keeps state in bind mounts ([storage.md](./storage.md#dockers-own-storage)), so deleting a stack is deleting its directory. Stacks, Dockge's data and Caddy's data sit on the `fast` drive and the host's backup covers them.
- **Removal:** `just teardown <host> -e only=dockge,caddy,cloudflared` ([teardown](../ansible/README.md#turn-off-or-remove-a-service)).
