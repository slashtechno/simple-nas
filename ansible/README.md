# Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/services/<compose dir>/` on the host, all on the shared Docker network `services` except Homebridge, which runs on the host network for HomeKit discovery. Ansible runs on your Mac and SSHes into each host, which only needs SSH and Python. New to Ansible? Read [docs/ansible-terms.md](../docs/ansible-terms.md) first.

Files Ansible manages (`/opt/services/*/docker-compose.yml`, cron jobs, rendered configs) are overwritten on the next run, so change them here. Everything else on the host is yours and Ansible leaves it alone, except the system files a role documents (fstab, udev rules, Docker and containerd config, cloud-init, netplan, dnsmasq, sudoers and the restic password file). Restarting a container by hand is fine.

Everything is opt-in. A service runs on a host only when that host's `host_vars/<host>/vars.yml` sets `<name>_enabled: true`. Every service flag in `group_vars/all/flags.yml` defaults to false; the two switches for base parts there, `storage_enabled` (mounts the drives) and `tailscale_enabled`, default to true. Groups never carry behaviour: hosts are listed under `servers` in `inventory/hosts.yml`, and `site.yml` runs on all of them.

All commands below run from `ansible/`.

## Task index

| I want to | Edit | Then run |
|---|---|---|
| Deploy everything to one host | nothing | `just deploy '' --limit <host> -K` |
| Turn a service on for a host | `<name>_enabled: true` in `host_vars/<host>/vars.yml`, plus the drive roles and vault entries the service needs ([services](../docs/services.md)) | `just deploy <name> --limit <host>` |
| Stop deploying a service | set the flag to `false` (or delete it) | `ansible-playbook teardown.yml -e only=<name> --limit <host> --vault-password-file .vault-pass` ([remove a service](#disable-or-remove-a-service)) |
| Change a setting | the file that owns it ([change a setting](#change-a-setting)) | `just deploy <tag>` |
| Look up a setting, its default and every override | nothing | `just settings <part of the name>` (or `grep -rn "^<name>:" group_vars host_vars roles/*/defaults`) |
| Add or change a secret | `ansible-vault edit host_vars/<host>/vault.yml` (or `group_vars/all/vault.yml`) | `just deploy <tag>` |
| Update a service's image | its line in `group_vars/all/versions.yml` | `just preview <tag>`, then `just deploy <tag>` ([update images](#update-service-images)) |
| Update the OS, Docker Engine or Tailscale | nothing to edit | `just os-upgrade [host]` ([details](#update-software-that-is-not-a-docker-image)) |
| Add a host | [add a host](#add-a-host) | `just deploy '' --limit <host> -K` |
| Add a drive or move one service's data | [docs/storage.md](../docs/storage.md) | `just deploy storage --limit <host>` for a drive; `just deploy <service> --limit <host>` for a move |
| Give services `https://` names, or change a port or name | `caddy_private_domains` (each web service with a subdomain then gets a name), `<name>_subdomain`, `<name>_port`, and `caddy_sites` for the root of the server or a redirect, in `host_vars/<host>/vars.yml` ([HTTPS](../docs/caddy-reference.md#web-addresses-and-https)) | `just deploy caddy,homepage --limit <host>`, plus the service's tag |
| See what is running | nothing | open the Homepage, or `ssh <host> docker ps` |
| Add a public hostname | `cloudflared_ingress` in `host_vars/<host>/vars.yml` ([services](../docs/services.md#cloudflare-add-a-public-hostname)) | `just deploy cloudflared --limit <host>` |
| Add a new service to the repo | [add a new service](#add-a-new-service) | `just check`, then `just deploy <name>` |
| Preview without changing anything | nothing | `just preview <tag> --limit <host>` |
| Check my edits before committing | nothing | `just check` |
| Encrypt a folder | `encrypted_folders` ([docs/encryption.md](../docs/encryption.md)) | `just deploy encryption,backup --limit <host>`, then [set up the folder](../docs/encryption.md#set-up-a-folder) |
| Restore from a backup | nothing | [docs/backups.md](../docs/backups.md) |

## Which files hold what

| File | In git | Holds | Create it |
|---|---|---|---|
| `inventory/hosts.yml` | no (addresses) | The hosts under `servers`, with SSH address, user and key | Copy `hosts.yml.example` |
| `group_vars/all/defaults.yml` and its topic files `flags.yml` (all `<name>_enabled`, false except `storage_enabled` and `tailscale_enabled`), `backups.yml`, `data-dirs.yml`, `cloudflare.yml`, `direct-link.yml`, `web-uis.yml` | yes | Every shared setting with its default; a setting is in exactly one of them | Already there; not edited |
| `group_vars/all/vars.yml` | yes | Your values that apply to every host (timezone, SSH keys, Cloudflare zones, Gitea and pics URLs) | Copy `vars.yml.example` |
| `host_vars/<host>/vars.yml` | yes | One host: its `<name>_enabled` flags, `drives`, data paths, direct link, tunnel hostnames, backup repository | Copy `host_vars/vars.yml.example`, keep only what the host needs |
| `group_vars/all/vault.yml` | no (secrets) | Secrets shared by hosts: Cloudflare token and account, restic password, rclone token, ntfy token | Copy `vault.yml.example`, fill in, encrypt |
| `host_vars/<host>/vault.yml` | no (secrets) | One host's service secrets (database passwords, Copyparty logins, Garage keys) | Copy `host_vars/vault.yml.example`, keep the keys its services use, encrypt |
| `group_vars/all/derived.yml` | yes | Values worked out from the settings (`fast_drive`, `drive_mounts`, ...); not settings, so `just settings` leaves them out | Already there; not edited |
| `group_vars/all/versions.yml` | yes | Every image version | Already there |
| `group_vars/all/services.yml` | yes | One entry per service: its settings' prefix, compose directory, data directories (backup coverage and teardown) and, for a web UI, the Homepage tile and Caddy container | Already there |

Every setting has a comment and its default in `group_vars/all/` (shared settings: `defaults.yml` and the topic files) or `roles/<role>/defaults/main.yml` (one role's). Read the file; nothing is generated. The `vars` check inside `just check` only verifies that a vault name or a setting with no default appears in its example file ([Commands](#commands)).

A value is taken from the last of these that sets it: a role's `defaults/main.yml`, `group_vars/all/defaults.yml` and its topic files, `group_vars/all/vars.yml`, `host_vars/<host>/vars.yml`.

## Vault (secrets)

A vault file is a YAML file encrypted with `ansible-vault`. Ansible decrypts it in memory with the password in `ansible/.vault-pass` (one line, nothing else; the file is gitignored, so `chmod 600` it and keep the password in your password manager too). `just deploy` and `just preview` pass `--vault-password-file .vault-pass`; type the same flag when you run `ansible-playbook` yourself. Use the same password for every vault file.

Secrets live in `vault_*` variables inside a vault file. Templates and defaults read them through a plain name, for example `copyparty_pass` is `"{{ vault_copyparty_pass }}"`, so the committed files never hold a secret.

`just setup <host>` does the first-time work: it creates `.vault-pass` with a random password, creates `host_vars/<host>/vars.yml` from the example, and writes both vault files with random values for every generated secret (database passwords, the ntfy token, the restic password). It encrypts them, never prints a secret, and on a later run adds only what is missing. It then lists every other secret in the examples (account names, Cloudflare, GitHub, Google Drive, lists such as `vault_copyparty_collab_users`); add the ones your services use. Copy `.vault-pass` into your password manager: the restic backups cannot be read without it.

```bash
just setup <host>
ansible-vault edit --vault-password-file .vault-pass host_vars/<host>/vault.yml      # add the secrets it listed, or change one later
ansible-vault edit --vault-password-file .vault-pass group_vars/all/vault.yml
```

By hand instead: put a password in `.vault-pass`, copy `host_vars/vault.yml.example` to `host_vars/<host>/vault.yml` (and `group_vars/all/vault.yml.example` to `group_vars/all/vault.yml`), keep the keys your services use, and run `ansible-vault encrypt --vault-password-file .vault-pass <file>`.

A vault file you forget to encrypt still deploys, with its secrets in plain text on your computer: check that it starts with `$ANSIBLE_VAULT`.

`.gitignore` keeps every `vault.yml` and `inventory/hosts.yml` out of git. A name in both a host's vault and the shared vault takes the host's value. The names are flat (`vault_ntfy_token`, not `vault.ntfy.token`) on purpose: Ansible replaces a dict instead of merging it, so a host file holding one key of an app's dict would hide the others from the shared file, and one app's secrets are split that way (ntfy's token is shared, its password is per host). What each service needs is listed in [docs/services.md](../docs/services.md); the names and meanings are in `group_vars/all/vault.yml.example` and `host_vars/vault.yml.example`. Keep a copy of the vault files and their password somewhere that is not the Pi: restoring a backup needs `vault_restic_password` ([docs/backups.md](../docs/backups.md)).

## First-time setup

```bash
brew install ansible just uv rclone   # rclone only for the Google Drive backup; uv runs the linters; Docker is only needed for `just platforms`. The ansible package includes passlib and bcrypt, which hash the ntfy, Garage and Tinyauth passwords
cd ansible/
just deps
```

Then create the files in the table above and [add each host](#add-a-host). The first deploy to a host needs its sudo password once (`-K`); the sudoers file the `common` role installs makes `-K` unnecessary afterwards.

## Add a host

1. Make sure the host runs a Debian-family OS (Raspberry Pi OS, Debian 12 or newer, Ubuntu; Debian 11 ships restic 0.11, too old for the `- !` backup rules) with SSH and Python, and that your SSH key is on it. Ubuntu Server and Ubuntu Desktop work (Desktop uses more RAM and needs a keyboard-free setup, so install it only if you want one); skip Docker's snap, since the deploy installs Docker from apt and stops if it finds the snap. The direct link works with NetworkManager or netplan ([docs/networking.md](../docs/networking.md)).
2. In `inventory/hosts.yml`, add it under `servers: hosts:` with `ansible_host`, `ansible_user` (the username you set when you imaged the root drive) and `ansible_ssh_private_key_file`. The key you give it (for example `pinas`) is its nickname and names its `host_vars` directory.
3. Run `just setup <host>`: it creates `host_vars/<host>/vars.yml` from `host_vars/vars.yml.example` and the vault files (step 4). Set `drives` (each drive's UUID, mount point, filesystem and roles; see [docs/storage.md](../docs/storage.md)) and the `<name>_enabled` flags for what the host should run. A service that stores data needs the drive roles it uses; the deploy stops with a message naming a missing role.
4. `just setup` also wrote `host_vars/<host>/vault.yml` and `group_vars/all/vault.yml` (the shared secrets: Cloudflare, restic). Add the secrets it listed for the services you enabled ([Vault](#vault-secrets)).
5. Run `just deploy '' --limit <host> -K`. Join Tailscale once by hand afterwards: `sudo tailscale up`. If the host has `caddy_private_domains`, Caddy stops that first deploy until it has joined: join, then run the deploy again. Reboot the host once (`sudo reboot`): the drive guard (see [docs/storage.md](../docs/storage.md#how-a-drive-is-mounted)) is armed only at boot. Then set `ansible_host` to the host's tailnet name (`<host>.<tailnet>.ts.net`): it works from anywhere, and the Homepage and the service links use it.
6. Optional, by hand, Raspberry Pi OS only (the `rpi-connect` packages come from the Raspberry Pi repository, not Ubuntu or Debian): Raspberry Pi Connect (remote shell from a browser). Ansible leaves it alone because its sign-in needs a short-lived per-device key. On Lite: `sudo apt install rpi-connect-lite`, `loginctl enable-linger`, `rpi-connect on`, `rpi-connect signin`, and open the URL it prints. To remove it, run `rpi-connect signout` and delete the device on connect.raspberrypi.com.

## Pick what you use

Every part is a switch in `host_vars/<host>/vars.yml`; nothing you leave off is touched. The `common` role always runs: it gives the Ansible user passwordless sudo, installs the base packages, Docker and the terminal tools (`terminal_tools_enabled: false` leaves out zellij and the Ghostty terminfo), sets the timezone and the Docker data directory, adds your SSH keys, and masks suspend and hibernate. The `network` role (the shared Docker network and the direct link) also always runs. Three example hosts:

- **Everything:** turn on the services in [../docs/services.md](../docs/services.md).
- **Bare minimum:** `tailscale_enabled: true` (the default), `backup_local_enabled: true` and `drives:`. No service containers; run your own software however you like and still get the drives, remote access and backups.
- **Dockge and Cloudflare:** `dockge_enabled: true` and `cloudflared_enabled: true` with your own `cloudflared_ingress`, a `drives` entry with the `fast` role (Dockge keeps its stacks there) and `backup_local_enabled: true` with a drive whose roles include `backup`. You write the compose stacks in Dockge; Ansible keeps Docker, the tunnel and the backups.

To add your own service as a fork, follow [Add a new service](#add-a-new-service).

## Using this repo for your own hosts

The tracked `vars.yml` files hold the repo owner's values (domains, SSH public key, timezone, drive UUIDs), kept in git so the owner's setup is reproducible. Anyone else who copies the repo replaces them:

1. Copy `group_vars/all/vars.yml.example` over `group_vars/all/vars.yml` (create it if the file is missing) and delete any existing `host_vars/<host>/` directories.
2. Replace at least `ssh_authorized_keys` (the owner's key would otherwise be added to your hosts), `timezone`, and the Cloudflare, Gitea and pics values; set `restic_cloud_repository` in the `vars.yml` of each host that turns the offsite backup on.
3. Create `inventory/hosts.yml`, the vaults and your own `host_vars/<host>/` files as in the table.

## Commands

[`just`](https://just.systems) is a plain command runner. Run `just` in `ansible/` to list the recipes; each is a short shell snippet in `justfile`.

| Command | Does |
|---|---|
| `just check` | Everything CI runs; run before committing. Steps, each runnable alone: `_lint` (ansible-lint, shellcheck, ruff; skipped rules and reasons in `.ansible-lint`), `_syntax` (both playbooks parse), `_vars` (a vault name or a setting with no default missing from its example file), `_links` (a `file.md#anchor` naming no heading), `_test` (renders every template with the example vars and shellchecks the scripts; fails on an undefined variable, an undeclared key in a `vars.yml`, or a service missing from its flag, port or subdomain setting, `site.yml`, `services.yml` or `docs/services.md`) |
| `just settings [word]` | Every setting with its default, what it does and whether a host sets it; a word filters by name. Needs `uv`: the script (`tools/settings.py`) declares its one dependency in its own header, and a recipe that outgrows a shell line is written the same way |
| `just setup <host>` | First-run setup for a host: `.vault-pass`, `host_vars/<host>/vars.yml` and random vault secrets ([vault](#vault-secrets)) |
| `just deploy [tags] [flags]` | `site.yml` with `--vault-password-file .vault-pass`, optionally `--tags`, e.g. `just deploy immich`. Flags go after the tags: `just deploy '' --limit pinas -K` |
| `just teardown <host> [flags]` | `teardown.yml` for one host ([remove a service](#disable-or-remove-a-service)), e.g. `just teardown pi4 -e only=garage` |
| `just os-upgrade [host]` | `apt upgrade` on every server, or on one host ([software that is not a Docker image](#update-software-that-is-not-a-docker-image)) |
| `just preview [tags] [flags]` | The same with `--check --diff`, which changes nothing |
| `just platforms` | Checks every image in `versions.yml` has arm64 and x64 builds; needs Docker and network, not part of `check` |
| `just deps` | Installs the Ansible collections and roles in `requirements.yml` |

`--check` does not create directories, so on a first deploy a later step can fail with "not a directory". That is a preview limit, not a bug.

### Tags, `--limit` and `-K`

- **Tags** pick which roles run. Each role in `site.yml` has a tag with the role's name; `ansible-playbook site.yml --list-tags` lists them. `just deploy immich,pics` runs only those. The checks at the top of the playbook always run. `just deploy` and `just preview` stop with the list of tags when one matches no role (a typo, or `backup-status` for `backup_status`); plain `ansible-playbook --tags` would run no role and still exit successfully. A tag only selects a role; a role whose flag is false on the host is still skipped.
- **`--limit <host>`** restricts a run to one host (or a comma-separated list). Without it a run covers every host in `servers`.
- **`-K`** (`--ask-become-pass`) asks for the host's sudo password. It is needed only for a host's first deploy.

## Change a setting

Edit the file that owns the setting (below), then `just deploy <tag>`. Only changed services restart: compose-only services are recreated when their rendered file changes, and handlers cover Copyparty, Garage, Immich (a rotated SSO secret), pics, backup-status, cloudflared (new token), Homepage, containerd, the direct-link dnsmasq, netplan and storage (the fstab change and the USB udev rule).

| Setting | File |
|---|---|
| Used by one role | that role's `defaults/main.yml` |
| Shared by several roles, with a default | `group_vars/all/`: the topic file that fits (`flags.yml`, `data-dirs.yml`, `web-uis.yml` ...) or `defaults.yml` (change it for your hosts in `vars.yml`, not here) |
| Your value for every host (timezone, SSH keys, Cloudflare zones) | `group_vars/all/vars.yml`, mirrored in `vars.yml.example` |
| One host (its flags, drives, direct link, Docker data root, tunnel hostnames) | `host_vars/<host>/vars.yml`; the example `host_vars/vars.yml.example` serves every host |
| Secrets | a `vault.yml` ([vault](#vault-secrets)) |
| Image versions | `group_vars/all/versions.yml` |
| Computed from the above (`fast_drive`, `drive_mounts`, ...) | `group_vars/all/derived.yml`; not edited |

Options in `defaults/main.yml`, the shared defaults files and the example files have this comment shape: what it does in one sentence, then `Allowed: ... Default: ...` when not obvious, then `CAUTION: ...` where changing it later has a consequence. A role's options are named after the role or the tool it drives (`backup`'s are `restic_*`, `service_dumps_dir` and `rclone_config_dir`), and `ssh_authorized_keys` is listed in `group_vars/all/vars.yml.example` because nearly every owner changes it.

Service setup and gotchas are in [../docs/services.md](../docs/services.md); drives are in [../docs/storage.md](../docs/storage.md).

## Update service images

Every image and version is a line in `group_vars/all/versions.yml`; most have their release-notes link above them. To update one:

1. Read the release notes.
2. Edit that line (the registry's tags page lists the tags that exist).
3. `just preview <service>`, then `just deploy <service>`.

A floating tag (`latest`, `release`, `nightly`) doesn't move until you ask, because `docker_pull_policy` defaults to `missing`:

```bash
ansible-playbook site.yml --tags gitea -e docker_pull_policy=always --vault-password-file .vault-pass
```

Pin a floating tag to the version running on the host once it works: `docker inspect <container>` shows `org.opencontainers.image.version`, or ask the app (`docker exec gitea gitea --version`). Moving Immich to a newer version can run database migrations, so read its notes first. Its Postgres and Valkey are pinned by digest; change them only when Immich's notes say to. Caddy, Copyparty and backup-status build on the host and always rebuild; pics rebuilds only when its repository's commit changed, so `docker_pull_policy` doesn't apply to them.

## Update software that is not a Docker image

| What | How |
|---|---|
| Operating system packages: Docker Engine, Tailscale, restic, rclone, gocryptfs, the kernel, a Raspberry Pi's firmware | `just os-upgrade` (all hosts) or `just os-upgrade pinas`; add `-K` if the host asks for the sudo password. Deploys never upgrade these, so they change only when you run this |
| Reboot after a kernel or firmware upgrade | `sudo reboot` on the host. A host with `encrypted_folders` then needs `sudo /opt/services/scripts/unlock.sh` ([../docs/encryption.md](../docs/encryption.md)) |
| Zellij | Its version and checksum in `group_vars/all/versions.yml`, then `just deploy common` |
| Docker images | [Update service images](#update-service-images) |
| Stacks you run in Dockge | Dockge's own pull and update buttons; Ansible does not manage them |
| This repo's tools (collections, roles) | `just deps`; the linter versions are pinned at the top of `justfile` |

Do the upgrade at a quiet time: a Docker Engine upgrade restarts the containers. Tailscale keeps its login across upgrades.

## Disable or remove a service

Set `<name>_enabled: false` in `host_vars/<host>/vars.yml` (or delete the line) to stop deploying it. That alone does not stop what is running. To remove a service that is already on a host, tear it down, then leave the flag false so later runs don't bring it back.

`teardown.yml` runs every block on every host it reaches, so it refuses to run without `--limit <host>`.

```bash
ansible-playbook teardown.yml --limit pi4 -e only=garage --vault-password-file .vault-pass      # one service, data kept (names: the keys in group_vars/all/services.yml)
ansible-playbook teardown.yml --limit pi4 --vault-password-file .vault-pass                     # everything, data kept
ansible-playbook teardown.yml --limit pi4 -e remove_data=true --vault-password-file .vault-pass # also wipes data: no undo without a backup
```

Drive mounts, the restic password and Tailscale state are never touched. Also left: the plaintext service dumps and job logs on the backup drive (`<backup drive>/service-dumps` and `<backup drive>/logs`, or `/var/lib/backup-work` on a host with only the offsite backup; they hold a full database dump and Garage's node key), Docker volumes ([storage.md](../docs/storage.md)), Dockge stacks, the backup snapshots (the data stays restorable until retention prunes them), and your own `cloudflared_ingress` rule for the service, which you delete from `vars.yml`. A repo service's Caddy name goes when its flag is false and `just deploy caddy --limit <host>` has run; an app you run in Dockge carries its own labels. Verify a restore before `remove_data=true`; the paths it deletes are the `data` and `no_backup` settings of the service's entry in `group_vars/all/services.yml`.

Removing Tinyauth (`-e only=tinyauth`) leaves every protected name failing and, if `dockge_port` is `""`, Dockge without a login. To get Dockge's own login back, set `tinyauth_enabled: false` (or publish `dockge_port`) and run `just deploy dockge --limit <host>` ([services.md](../docs/services.md#ad-hoc-app-platform)).

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,defaults}`
2. `templates/docker-compose.yml.j2`: join the external `services` network. Take the image from a variable defined in `versions.yml`, one line such as `myservice_image: owner/myservice:1.2.3` (pin a version, or a digest if upstream has no versioned tag). Give the container a `container_name` and use that name for `container` in its `services.yml` entry and for a `cloudflared_ingress` service; set `restart: unless-stopped`; check the image has arm64 and x64 builds (`just platforms`).
3. `tasks/main.yml`: create the data dirs, then `import_role: compose_service` with `compose_service_name: myservice`. Copy `roles/gitea`. A service that restarts on config changes (like `copyparty`) writes its own tasks and handlers instead.
4. `defaults/main.yml`: settings only this role reads.
5. `group_vars/all/`: `myservice_enabled: false` in `flags.yml`, the data directory settings in `data-dirs.yml` and, for a web UI, `myservice_port` and `myservice_subdomain` in `web-uis.yml`, each with a comment. Values with no sensible default go in `vars.yml.example`.
6. `group_vars/all/services.yml`: one entry, e.g. `- {name: Myservice, key: myservice, compose: myservice, data: [myservice_data_dir]}` (a service with no data directories leaves `data` out). It lists the data directories (the backup must cover them, and teardown deletes them with `remove_data=true`) and, for a web UI, the Homepage tile and Caddy container. The comment at the top of the file describes each field.
7. `site.yml`: an `import_role` task with the tag `myservice` and `when: myservice_enabled | bool`.
8. Its secrets go in the matching `vault.yml.example`, and a row naming `roles/myservice` in the table in [../docs/services.md](../docs/services.md).
9. Optional: a public hostname needs a `cloudflared_ingress` rule; a live database needs `files/dump.sh` installed into `service_dump_scripts_dir` and `dump_required: true` in its entry (copy `roles/gitea`; see [../docs/backups.md](../docs/backups.md)); data outside the offsite backup goes in `restic_cloud_extra_rules`.
10. `just check` fails with the exact missing line if steps 5 to 8 are incomplete. Then `just deploy myservice`.

Teardown (`teardown.yml -e only=myservice`), backup coverage, the Homepage tile and the Caddy name come from that entry; the port and subdomain in step 5 give the tile its link, and the subdomain gives the service its Caddy name under `caddy_private_domains`.
