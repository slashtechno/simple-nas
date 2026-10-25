# Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/services/<service>/` on the host, all on the shared Docker network `services`. Ansible runs on your Mac and SSHes into each host, which only needs SSH and Python. New to Ansible? Read [docs/ansible-terms.md](../docs/ansible-terms.md) first.

Files Ansible manages (`/opt/services/*/docker-compose.yml`, cron jobs, rendered configs) are overwritten on the next run, so change them here. Everything else on the host is yours and Ansible leaves it alone. Restarting a container by hand is fine.

Everything is opt-in. A service runs on a host only when that host's `host_vars/<host>/vars.yml` sets `<name>_enabled: true`. Every service flag defaults to false (`storage_enabled`, which mounts the drives, defaults to true). Groups never carry behaviour: hosts are listed under `servers` in `inventory/hosts.yml`, and `site.yml` runs on all of them.

All commands below run from `ansible/`.

## Task index

| I want to | Edit | Then run |
|---|---|---|
| Deploy everything to one host | nothing | `just deploy '' --limit <host> -K` |
| Turn a service on for a host | `<name>_enabled: true` in `host_vars/<host>/vars.yml`, plus the drive roles and vault entries the service needs ([services](../docs/services.md)) | `just deploy <name> --limit <host>` |
| Stop deploying a service | set the flag to `false` (or delete it) | `ansible-playbook teardown.yml --tags <name> --limit <host> --vault-password-file .vault-pass` ([remove a service](#disable-or-remove-a-service)) |
| Change a setting | the file that owns it ([change a setting](#change-a-setting)) | `just deploy <tag>` |
| Look up a setting, its default and every override | nothing | `grep -rn "^<name>:" group_vars host_vars roles/*/defaults` |
| Add or change a secret | `ansible-vault edit host_vars/<host>/vault.yml` (or `group_vars/all/vault.yml`) | `just deploy <tag>` |
| Update a service's image | its line in `group_vars/all/versions.yml` | `just preview <tag>`, then `just deploy <tag>` ([update images](#update-service-images)) |
| Add a host | [add a host](#add-a-host) | `just deploy '' --limit <host> -K` |
| Add a drive or move data | [docs/storage.md](../docs/storage.md) | `just deploy storage --limit <host>` |
| Give services `https://` names, or change a port or name | `caddy_private_domains` (every service then gets a name), `<name>_subdomain`, `<name>_port`, and `caddy_sites` for the root of the server, in `host_vars/<host>/vars.yml` ([HTTPS](../docs/networking.md#web-addresses-and-https)) | `just deploy caddy,homepage --limit <host>`, plus the service's tag |
| See what is running | nothing | `just status`, or open the Homepage |
| Add a public hostname | `cloudflared_ingress` in `host_vars/<host>/vars.yml` ([services](../docs/services.md#cloudflare-add-a-public-hostname)) | `just deploy cloudflared --limit <host>` |
| Add a new service to the repo | [add a new service](#add-a-new-service) | `just check`, then `just deploy <name>` |
| Preview without changing anything | nothing | `just preview <tag> --limit <host>` |
| Check my edits before committing | nothing | `just check` |
| Restore from a backup | nothing | [docs/backups.md](../docs/backups.md) |

## Which files hold what

| File | In git | Holds | Create it |
|---|---|---|---|
| `inventory/hosts.yml` | no (addresses) | The hosts under `servers`, with SSH address, user and key | Copy `hosts.yml.example` |
| `group_vars/all/defaults.yml` | yes | Every shared setting with its default; all `<name>_enabled` flags, all false | Already there; not edited |
| `group_vars/all/vars.yml` | yes | Your values that apply to every host (timezone, SSH keys, Cloudflare zones, Gitea and pics URLs) | Copy `vars.yml.example` |
| `host_vars/<host>/vars.yml` | yes | One host: its `<name>_enabled` flags, `drives`, data paths, direct link, tunnel hostnames, backup repository | Copy `host_vars/vars.yml.example`, keep only what the host needs |
| `group_vars/all/vault.yml` | no (secrets) | Secrets shared by hosts: Cloudflare token and account, restic password, rclone token, ntfy token | Copy `vault.yml.example`, fill in, encrypt |
| `host_vars/<host>/vault.yml` | no (secrets) | One host's service secrets (database passwords, Copyparty logins, Garage keys) | Copy `host_vars/vault.yml.example`, keep the keys its services use, encrypt |
| `group_vars/all/versions.yml` | yes | Every image version | Already there |
| `group_vars/all/web_services.yml` | yes | The web UIs: Homepage tile, host port, Caddy container and port | Already there |

Every setting has a comment and its default in `group_vars/all/defaults.yml` (shared settings) or `roles/<role>/defaults/main.yml` (one role's). Read the file; nothing is generated. `just check` only verifies that vault names and settings with no default appear in the example files.

A value is taken from the last of these that sets it: a role's `defaults/main.yml`, `group_vars/all/defaults.yml`, `group_vars/all/vars.yml`, `host_vars/<host>/vars.yml`.

## Vault (secrets)

A vault file is a YAML file encrypted with `ansible-vault`. Ansible decrypts it in memory with the password in `ansible/.vault-pass` (one line, nothing else; the file is gitignored, so `chmod 600` it and keep the password in your password manager too). `just deploy` and `just preview` pass `--vault-password-file .vault-pass`; type the same flag when you run `ansible-playbook` yourself. Use the same password for every vault file.

Secrets live in `vault_*` variables inside a vault file. Templates and defaults read them through a plain name, for example `copyparty_pass` is `"{{ vault_copyparty_pass }}"`, so the committed files never hold a secret.

```bash
cp host_vars/vault.yml.example host_vars/<host>/vault.yml   # keep only the keys your services use
ansible-vault encrypt host_vars/<host>/vault.yml            # first time
ansible-vault edit host_vars/<host>/vault.yml               # later changes
```

`.gitignore` keeps every `vault.yml` and `inventory/hosts.yml` out of git. A name in both a host's vault and the shared vault takes the host's value. What each service needs is listed in [docs/services.md](../docs/services.md); the names and meanings are in `group_vars/all/vault.yml.example` and `host_vars/vault.yml.example`. Keep a copy of the vault files and their password somewhere that is not the Pi: restoring a backup needs `vault_restic_password` ([docs/backups.md](../docs/backups.md)).

## First-time setup

```bash
brew install ansible just uv   # uv runs the linters; Docker is only needed for `just tags`. The ansible package includes passlib and bcrypt, which hash the ntfy and Garage passwords
cd ansible/
just deps
```

Then create the files in the table above and [add each host](#add-a-host). The first deploy to a host needs its sudo password once (`-K`); the sudoers file the `common` role installs makes `-K` unnecessary afterwards.

## Add a host

1. Make sure the host runs a Debian-family OS (Raspberry Pi OS, Debian, Ubuntu) with SSH and Python, and that your SSH key is on it. Ubuntu Server and Ubuntu Desktop work (Desktop uses more RAM and needs a keyboard-free setup, so install it only if you want one); skip Docker's snap, since the deploy installs Docker from apt and stops if it finds the snap. The direct link works with NetworkManager or netplan ([docs/networking.md](../docs/networking.md)).
2. In `inventory/hosts.yml`, add it under `servers: hosts:` with `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file`. The key you give it (for example `pinas`) is its nickname and names its `host_vars` directory.
3. Create `host_vars/<host>/vars.yml` from `host_vars/vars.yml.example`. Set `drives` (each drive's UUID, mount point, filesystem and roles; see [docs/storage.md](../docs/storage.md)) and the `<name>_enabled` flags for what the host should run. A service that stores data needs the drive roles it uses; the deploy stops with a message naming a missing role.
4. Create `host_vars/<host>/vault.yml` from `host_vars/vault.yml.example`, keep the keys the enabled services use, and encrypt it. Shared secrets (Cloudflare, restic) go in `group_vars/all/vault.yml`.
5. Run `just deploy '' --limit <host> -K`. Join Tailscale once by hand afterwards: `sudo tailscale up` ([docs/networking.md](../docs/networking.md)). Then set `ansible_host` to the host's tailnet name (`<host>.<tailnet>.ts.net`): it works from anywhere, and the Homepage and the service links use it.
6. Optional, by hand, Raspberry Pi OS only (the `rpi-connect` packages come from the Raspberry Pi repository, not Ubuntu or Debian): Raspberry Pi Connect (remote shell from a browser). Ansible leaves it alone because its sign-in needs a short-lived per-device key. On Lite: `sudo apt install rpi-connect-lite`, `loginctl enable-linger`, `rpi-connect on`, `rpi-connect signin`, and open the URL it prints. To remove it, run `rpi-connect signout` and delete the device on connect.raspberrypi.com.

## Using this repo for your own hosts

The tracked `vars.yml` files hold the repo owner's values (domains, SSH public key, timezone, drive UUIDs), kept in git so the owner's setup is reproducible. Anyone else who copies the repo replaces them:

1. Overwrite `group_vars/all/vars.yml` with `vars.yml.example` and delete the existing `host_vars/<host>/` directories.
2. Replace at least `ssh_authorized_keys` (the owner's key would otherwise be added to your hosts), `timezone`, the Gitea and Cloudflare values, and `restic_cloud_repository`.
3. Create `inventory/hosts.yml`, the vaults and your own `host_vars/<host>/` files as in the table.

## Commands

[`just`](https://just.systems) is a plain command runner. Run `just` in `ansible/` to list the recipes; each is a short shell snippet in `justfile`.

| Command | Does |
|---|---|
| `just check` | `lint`, `syntax`, `vars`, `links` and `test`; run before committing (CI runs it too) |
| `just lint` | ansible-lint, shellcheck on shipped scripts, ruff on the dashboard. Skipped rules and their reasons: `.ansible-lint` |
| `just syntax` | Both playbooks parse |
| `just vars` | Fails if a vault name or a setting with no default is missing from its example file |
| `just links` | Fails if a `file.md#anchor` link or an in-page anchor in the docs points nowhere |
| `just test` | Renders every template with the example vars and shellchecks the scripts. Fails on an undefined variable or a key in a `vars.yml` that no example or role default declares |
| `just deploy [tags] [flags]` | `site.yml` with `--vault-password-file .vault-pass`, optionally `--tags`, e.g. `just deploy immich`. Flags go after the tags: `just deploy '' --limit pinas -K` |
| `just status [host]` | `docker ps` on every server, or on one host |
| `just preview [tags] [flags]` | The same with `--check --diff`, which changes nothing |
| `just tags <image> [filter] [count]` | Lists an image's tags, e.g. `just tags dxflrs/garage '^v2\.'`. Needs Docker running on your Mac. Optional: the registry's tags page shows the same list |
| `just deps` | Installs the Ansible collections and roles in `requirements.yml` |

`--check` does not create directories, so on a first deploy a later step can fail with "not a directory". That is a preview limit, not a bug.

### Tags, `--limit` and `-K`

- **Tags** pick which roles run. Each role in `site.yml` has a tag with the role's name: `storage`, `common`, `tailscale`, `network`, `immich`, `copyparty`, `gitea`, `homebridge`, `pics`, `crafty`, `dockge`, `homepage`, `caddy`, `cloudflared`, `garage`, `backup`, `ntfy`, `backup_status`. `just deploy immich,pics` runs only those. The checks at the top of the playbook always run. A tag that matches no role (a typo, or `backup-status` for `backup_status`) runs nothing and still exits successfully. A tag only selects a role; a role whose flag is false on the host is still skipped.
- **`--limit <host>`** restricts a run to one host (or a comma-separated list). Without it a run covers every host in `servers`.
- **`-K`** (`--ask-become-pass`) asks for the host's sudo password. It is needed only for a host's first deploy.

## Change a setting

Edit the file that owns the setting (below), then `just deploy <tag>`. Only changed services restart: compose-only services are recreated when their rendered file changes, and handlers cover Copyparty, Garage, pics, backup-status, cloudflared (new token), containerd, the direct-link dnsmasq and storage (udev rules).

| Setting | File |
|---|---|
| Used by one role | that role's `defaults/main.yml` |
| Shared by several roles, with a default | `group_vars/all/defaults.yml` (change it for your hosts in `vars.yml`, not here) |
| Your value for every host (timezone, SSH keys, Cloudflare zones) | `group_vars/all/vars.yml`, mirrored in `vars.yml.example` |
| One host (its flags, drives, direct link, Docker data root, tunnel hostnames) | `host_vars/<host>/vars.yml`; the example `host_vars/vars.yml.example` serves every host |
| Secrets | a `vault.yml` ([vault](#vault-secrets)) |
| Image versions | `group_vars/all/versions.yml` |
| Computed from the above (`fast_drive`, `drive_mounts`, ...) | the last section of `group_vars/all/defaults.yml`; not edited |

Options in `defaults/main.yml`, `defaults.yml` and the example files have this comment shape: what it does in one sentence, then `Allowed: ... Default: ...` when not obvious, then `CAUTION: ...` where changing it later has a consequence. Options private to a role start with the role name.

Service setup and gotchas are in [../docs/services.md](../docs/services.md); drives are in [../docs/storage.md](../docs/storage.md).

## Update service images

Every image and version is a line in `group_vars/all/versions.yml`, with its release-notes link above it. To update one:

1. Read the release notes.
2. Edit that line (`just tags <image>` lists the tags that exist).
3. `just preview <service>`, then `just deploy <service>`.

A floating tag (`latest`, `release`, `nightly`) doesn't move until you ask, because deploys use `pull: missing`:

```bash
ansible-playbook site.yml --tags gitea -e docker_pull_policy=always --vault-password-file .vault-pass
```

Pin a floating tag to the version running on the host once it works: `docker inspect <container>` shows `org.opencontainers.image.version`, or ask the app (`docker exec gitea gitea --version`). Moving Immich to a newer version can run database migrations, so read its notes first. Its Postgres and Valkey are pinned by digest; change them only when Immich's notes say to. Copyparty and backup-status build on the host and always rebuild, so `docker_pull_policy` doesn't apply to them.

## Disable or remove a service

Set `<name>_enabled: false` in `host_vars/<host>/vars.yml` (or delete the line) to stop deploying it. That alone does not stop what is running. To remove a service that is already on a host, tear it down, then leave the flag false so later runs don't bring it back.

`teardown.yml` runs every block on every host it reaches, so it refuses to run without `--limit <host>`.

```bash
ansible-playbook teardown.yml --limit pi4 --tags garage --vault-password-file .vault-pass       # one service, data kept
ansible-playbook teardown.yml --limit pi4 --vault-password-file .vault-pass                     # everything, data kept
ansible-playbook teardown.yml --limit pi4 -e remove_data=true --vault-password-file .vault-pass # also wipes data: no undo without a backup
```

Drive mounts, the restic password and Tailscale state are never touched.

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,defaults}`
2. `templates/docker-compose.yml.j2`: join the external `services` network. Take the image from a variable defined in `versions.yml`.
3. `tasks/main.yml`: create the data dirs, then `import_role: compose_service` with `compose_service_name: myservice`. Copy `roles/gitea`. A service that restarts on config changes (like `copyparty`) writes its own tasks and handlers instead.
4. `defaults/main.yml`: settings only this role reads. Shared values (the data dir, the `myservice_enabled` flag, the ports used in `cloudflared_ingress`) go in `group_vars/all/defaults.yml` with a comment; values with no sensible default go in `vars.yml.example`.
5. `site.yml`: add an `import_role` task with a tag and `when: myservice_enabled | bool`.
6. `teardown.yml`: add an entry using `import_tasks: teardown_service.yml` with `service` and `data_paths`.
7. A public hostname needs a `cloudflared_ingress` rule.
8. A live database needs `files/dump.sh`, installed into `service_dump_scripts_dir` (copy `roles/gitea`; see [../docs/backups.md](../docs/backups.md)). Plain files need nothing; add the data dir to `restic_cloud_rules` to send it offsite.
9. A web UI gets a line in `group_vars/all/web_services.yml` (Homepage tile and Caddy name) and its `myservice_port` and `myservice_subdomain` in `group_vars/all/defaults.yml`.
10. Add its secrets to the matching `vault.yml.example`, and a row to the services table in [../docs/services.md](../docs/services.md).
11. `just check`, then `just deploy myservice`.
