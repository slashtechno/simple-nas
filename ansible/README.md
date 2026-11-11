# Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/services/<compose dir>/` on the host, all on the shared Docker network `services` (Homebridge uses the host network for HomeKit discovery). Ansible runs on your Mac and SSHes into each host, which needs only SSH and Python. New to Ansible? The last section of [docs/glossary.md](../docs/glossary.md#ansible) lists the parts you will meet.

Ansible overwrites the files it manages (`/opt/services/*/docker-compose.yml`, cron jobs, rendered configs) on the next run, so change them here. Everything else on the host is yours, except the system files a role documents (fstab, udev rules, Docker and containerd config, cloud-init, netplan, dnsmasq, sudoers, the restic password file, `cmdline.txt`, the zram drop-ins, the terminal-tools block in `.bashrc`). Restarting a container by hand is fine.

Every service is opt-in: it runs on a host only when that host's `host_vars/<host>/vars.yml` sets `<name>_enabled: true`. Service flags default to false in `group_vars/all/defaults-flags.yml`; the base parts default on there: `storage_enabled`, `tailscale_enabled` and `pi_enabled` (`auto`: Raspberry Pi tuning on a Pi, skipped elsewhere). Groups never carry behaviour: hosts are listed under `servers` in `inventory/hosts.yml` and `site.yml` runs on all of them.

All commands run from `ansible/`.

## Task index

| I want to | Do | Then run |
|---|---|---|
| Set up a new server | [quick-start](../docs/quick-start.md), then [add a host](#add-a-host) | `just deploy '' --limit <host> -K` |
| Turn a service on | `<name>_enabled: true` in `host_vars/<host>/vars.yml`, plus its drive roles and vault entries ([services](../docs/services.md)) | `just deploy <name> --limit <host>` (with Caddy names also `caddy,homepage`) |
| Stop or remove a service | flag `false`, then [tear it down](#disable-or-remove-a-service) | `just teardown <host> -e only=<name>` |
| Change a setting | the file that owns it ([table below](#which-files-hold-what)) | `just deploy <tag>` |
| Find a setting, its default and overrides | nothing | `just settings <word>` (or `grep -rn "^<name>:" group_vars host_vars roles/*/defaults`) |
| Add or change a secret | `just edit vault` | `just deploy <tag>` |
| Update a service's image | its line in `versions.yml` ([how](#update-service-images)) | `just preview <tag>`, then `just deploy <tag>` |
| Update the OS, Docker or Tailscale | nothing | `just os-upgrade [host]` ([details](#update-software-that-is-not-a-docker-image)) |
| Add a drive, replace one, or move a service's data | [docs/storage.md](../docs/storage.md) | `just deploy storage --limit <host>` |
| Add a host, or run several | [add a host](#add-a-host) | `just deploy '' --limit <host> -K` |
| Give services `https://` names, or change a port | `caddy_private_domains`, `<name>_subdomain`, `<name>_port` ([HTTPS](../docs/caddy-reference.md#web-addresses-and-https)) | `just deploy caddy,homepage --limit <host>` and the service's tag |
| Add a public hostname | `cloudflared_ingress` ([how](../docs/services.md#cloudflare-add-a-public-hostname)) | `just deploy cloudflared --limit <host>` |
| Encrypt a folder | `encrypted_folders` ([docs/encryption.md](../docs/encryption.md)) | `just deploy encryption,backup --limit <host>`, then [set up the folder](../docs/encryption.md#set-up-a-folder) |
| Add a new service to the repo | [add a new service](#add-a-new-service) | `just check`, then `just deploy <name>` |
| Preview, or check my edits | nothing | `just preview <tag> --limit <host>`; `just check` |
| Restore from a backup, or recover after a disaster | nothing | [docs/backups.md](../docs/backups.md) |

## Which files hold what

| File | In git | Holds |
|---|---|---|
| `inventory/hosts.yml` | no | The hosts under `servers`: SSH address, user, key. Copy `hosts.yml.example`. |
| `group_vars/all/defaults.yml`, `defaults-<topic>.yml` | yes | Every shared setting with its default and a comment. A setting is in exactly one. Not edited: override in `vars.yml`. |
| `roles/<role>/defaults/main.yml` | yes | Settings only that role reads. |
| `group_vars/all/vars.yml` | yes | Your values for every host: timezone, SSH keys, Cloudflare zones, Gitea and pics URLs. Copy `vars.yml.example`. |
| `host_vars/<host>/vars.yml` | yes | One host: `<name>_enabled` flags, `drives`, data paths, tunnel hostnames, backup repository. Copy `host_vars/vars.yml.example`, keep what the host needs. |
| `group_vars/all/vault.yml`, `host_vars/<host>/vault.yml` | no | Secrets: shared (Cloudflare token, restic password, ntfy token) and per host (database passwords, logins). Copy the `.example`, fill in, encrypt. |
| `group_vars/all/versions.yml` | yes | Every image version. |
| `group_vars/all/services.yml` | yes | One entry per service: settings prefix, compose directory, data directories (backup coverage and teardown) and, for a web UI, the Homepage tile and Caddy container. |
| `group_vars/all/derived.yml` | yes | Values worked out from the settings (`fast_drive`, `drive_mounts`, ...). Not settings; not edited. |

Read a setting's file for its comment (what it does, `Allowed:`, `Default:`, `CAUTION:` where changing it later has a consequence); nothing is generated.

**Which value wins** (the last one set): a role's `defaults/main.yml`, the shared defaults files, `group_vars/all/vars.yml`, `host_vars/<host>/vars.yml`. Files in `group_vars/all/` load in name order, and the defaults files sort before `vars.yml`; `just check` enforces that.

A deploy restarts only what changed: compose services are recreated when their rendered file changes, and handlers cover the rest (Copyparty, Garage, pics, cloudflared, Homepage, containerd, dnsmasq, netplan, storage).

## Vault (secrets)

A vault file is YAML encrypted with `ansible-vault`, holding `vault_*` variables. Templates read them through a plain name (`copyparty_password` is `"{{ vault_copyparty_password }}"`), so committed files never hold a secret.

- **Password:** `ansible/.vault-pass` (one line; gitignored; `chmod 600`). Keep it in your password manager too: the restic backups cannot be read without it. Use one password for every vault file.
- **Names:** a login's user and password sit together: `vault_<service>_user` and `vault_<service>_password`. Other secrets end in `_token`, `_key` or `_oidc_secret`. Names are flat (`vault_ntfy_token`, not `vault.ntfy.token`): Ansible replaces a dict instead of merging it, so a host file holding one key would hide the others.
- **Host over shared:** a name in both a host's vault and the shared vault takes the host's value.
- **Where to look:** each service's needs are in [docs/services.md](../docs/services.md); names and meanings are in the two `vault.yml.example` files.
- **Copies:** keep the vault files and their password somewhere that is not the Pi: a restore needs `vault_restic_password` ([docs/backups.md](../docs/backups.md)).

```bash
just setup <host>   # .vault-pass, host_vars/<host>/vars.yml, both vaults with random values; safe to rerun (adds only what is missing)
just edit vault     # add the secrets it listed, or change one later
```

`just setup` never prints a secret, then lists the secrets it cannot generate (account names, Cloudflare, GitHub, Google Drive, lists such as `vault_copyparty_collab_users`).

<details>
<summary>Without <code>just setup</code>, and checking a vault is encrypted</summary>

Put a password in `.vault-pass`, copy `host_vars/vault.yml.example` to `host_vars/<host>/vault.yml` (and `group_vars/all/vault.yml.example` to `group_vars/all/vault.yml`), keep the keys your services use, and run `ansible-vault encrypt --vault-password-file .vault-pass <file>`.

A vault you forget to encrypt still deploys, with its secrets in plain text on your computer: `head -1 <file>` must print a line starting with `$ANSIBLE_VAULT`. `.gitignore` keeps every `vault.yml` and `inventory/hosts.yml` out of git.

</details>

## First-time setup

```bash
brew install ansible just uv rclone   # rclone only for the Google Drive backup; uv runs the linters and `just edit`; Docker only for `just platforms`
cd ansible/
just deps
```

Then create the files in the table above and [add each host](#add-a-host). The first deploy to a host needs its sudo password once (`-K`); the sudoers file `common` installs makes `-K` unnecessary afterwards.

## Add a host

The same steps add a second or third host: each has its own `host_vars/<host>/` directory, values every host shares go in `group_vars/all/vars.yml`, and `--limit <host>` aims a deploy at one.

1. Check the host:
   - Debian-family OS: Raspberry Pi OS, Debian 12 or newer, or Ubuntu. (Debian 11 is too old: its restic 0.11 cannot read the `- !` backup rules.)
   - SSH and Python are installed and your SSH key is on it. No Docker snap (the deploy stops if it finds one).
   - Enough RAM for what you switch on: Immich, Crafty and Gitea are the largest, and a build (pics, Caddy) needs more than the running service. See [memory.md](../docs/memory.md).
2. In `inventory/hosts.yml`, add it under `servers: hosts:` with `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file`. The key (for example `pinas`) is its nickname and names its `host_vars` directory.
3. `just setup <host>`. Set `drives` ([docs/storage.md](../docs/storage.md)) and the `<name>_enabled` flags the host should run, and add the secrets `just setup` listed for them.
4. `just deploy '' --limit <host> -K`.
5. Join the tailnet once by hand: `sudo tailscale up`. With `caddy_private_domains` set, Caddy stops this first deploy until you have joined: join, then deploy again.
6. Reboot once (`sudo reboot`): the drive guard ([storage.md](../docs/storage.md#how-a-drive-is-mounted)) is armed only at boot, and on a Raspberry Pi so is the memory cgroup.
7. Set `ansible_host` to the host's tailnet name (`<host>.<tailnet>.ts.net`). It works from anywhere, and Homepage and the service links use it.

<details>
<summary>Optional: Raspberry Pi Connect (remote shell from a browser)</summary>

Raspberry Pi OS only; Ansible leaves it alone because its sign-in needs a short-lived per-device key. Install (Lite): `sudo apt install rpi-connect-lite`, `loginctl enable-linger`, `rpi-connect on`, `rpi-connect signin`, then open the URL it prints. Remove: `rpi-connect signout`, then delete the device on connect.raspberrypi.com.

</details>

## Pick what you use

Every part is a switch in `host_vars/<host>/vars.yml`; a service you leave off is not touched (on a Raspberry Pi, `pi_enabled: auto` still edits the kernel command line; set it to `false` to skip). The `common` role ([what it does](../docs/services.md#every-host)) and the `network` role (the shared Docker network and the direct link) always run. Three example hosts:

- **Everything:** turn on the services in [docs/services.md](../docs/services.md).
- **Bare minimum:** `tailscale_enabled: true` (the default; `pi_enabled` is `auto`, so a Pi also gets its memory cgroup), `backup_local_enabled: true` and `drives:`. No service containers; run your own software however you like and still get the drives, remote access and backups.
- **Dockge and Cloudflare:** `dockge_enabled: true` and `cloudflared_enabled: true` with your own `cloudflared_ingress`, a `drives` entry with the `fast` role (Dockge keeps its stacks there) and `backup_local_enabled: true` with a drive whose roles include `backup`. You write the compose stacks in Dockge; Ansible keeps Docker, the tunnel and the backups.

To add your own service as a fork, follow [Add a new service](#add-a-new-service).

## Using this repo for your own hosts

The tracked `vars.yml` files hold the repo owner's values (domains, SSH public key, timezone, drive UUIDs). If you copy the repo, replace them:

1. Copy `group_vars/all/vars.yml.example` over `group_vars/all/vars.yml` and delete any existing `host_vars/<host>/` directories.
2. Replace at least `ssh_authorized_keys` (the owner's key would otherwise be added to your hosts), `timezone`, and the Cloudflare, Gitea and pics values; set `restic_cloud_repository` in each host's `vars.yml` that turns the offsite backup on.
3. Create `inventory/hosts.yml`, the vaults and your own `host_vars/<host>/` files as in the table.

## Commands

[`just`](https://just.systems) is a plain command runner; `just` lists the recipes, each a short shell snippet in `justfile`.

| Command | Does |
|---|---|
| `just check` | Everything CI runs; run before committing ([what it runs](#what-just-check-runs)) |
| `just settings [word]` | Every setting with its default and whether a host sets it (needs `uv` for colour; `python3 tools/settings.py` otherwise) |
| `just edit [vars\|vault] [--host H \| --all]` | Opens a vars or vault file in `$EDITOR`, decrypting and re-encrypting a vault (needs `uv`; `ansible-vault edit --vault-password-file .vault-pass <file>` always works) |
| `just setup <host>` | First-run setup for a host ([vault](#vault-secrets)) |
| `just deploy [tags] [flags]` | `site.yml`, e.g. `just deploy immich` or `just deploy '' --limit pinas -K` |
| `just preview [tags] [flags]` | The same with `--check --diff`, which changes nothing |
| `just teardown <host> [flags]` | `teardown.yml` for one host ([remove a service](#disable-or-remove-a-service)) |
| `just os-upgrade [host]` | `apt upgrade` on every server or one host |
| `just platforms` | Checks every pinned image has arm64 and x64 builds (needs Docker and network; not part of `check`) |
| `just deps` | Installs the collections and roles in `requirements.yml` |

- **Tags** pick roles: each role in `site.yml` has a tag of its name (`ansible-playbook site.yml --list-tags`), and `just deploy immich,pics` runs only those. A tag only selects a role; one whose flag is false on the host is still skipped. A tag that matches no role stops `just deploy` and `just preview` with the list of tags.
- **`--limit <host>`** restricts a run to one host (or a comma-separated list); without it a run covers every host.
- **`-K`** asks for the host's sudo password; only a first deploy needs it.
- `--check` does not create directories, so on a first deploy a later step can fail with "not a directory": a preview limit, not a bug.

### What `just check` runs

- `_lint`: ansible-lint, shellcheck and ruff (skipped rules and reasons are in `.ansible-lint`).
- `_syntax`: both playbooks parse.
- `_vars`: every vault name and every setting with no default appears in its example file; no setting has a default in two files; the defaults files sort before `vars.yml`; `group_vars/all/` holds only the expected files.
- `_links`: every `file.md#anchor` names a heading.
- `_precedence`: `vars.yml` beats the defaults, a host's vars beat `vars.yml`, and `versions.yml` loads after `vars.yml`.
- `_test`: renders every template with the example vars and shellchecks the scripts, then checks each drive layout. It fails on an undefined variable, an undeclared key in a `vars.yml`, or a service missing from its flag, port or subdomain setting, `site.yml`, `services.yml` or `docs/services.md`.

## Update service images

Every image version is a line in `group_vars/all/versions.yml`, most with a release-notes link above. To update one: read the notes, edit the line (the registry's tags page lists what exists), `just preview <service>`, then `just deploy <service>`.

- A floating tag (`latest`, `release`, `nightly`) does not move until you ask: `ansible-playbook site.yml --tags gitea -e docker_pull_policy=always --vault-password-file .vault-pass`. Pin it to the running version once it works (`docker inspect <container>` shows `org.opencontainers.image.version`).
- Moving Immich to a newer version can run database migrations; read its notes first. Its Postgres and Valkey are pinned by digest: change them only when Immich's notes say to.
- Caddy, Copyparty and backup-status build on the host and always rebuild; pics rebuilds when its repository's commit changed. `docker_pull_policy` does not apply to them.

## Update software that is not a Docker image

| What | How |
|---|---|
| OS packages (Docker Engine, Tailscale, restic, rclone, gocryptfs, kernel, Pi firmware) | `just os-upgrade [host]` (add `-K` if asked). Deploys never upgrade these. |
| After a kernel or firmware upgrade, or a Pi or zram setting change | `sudo reboot`; containers with a memory limit then need `-e docker_recreate=always` ([memory.md](../docs/memory.md#memory-limits)); a host with `encrypted_folders` needs `sudo /opt/services/scripts/unlock.sh` ([encryption.md](../docs/encryption.md)) |
| Zellij | Its version and checksum in `versions.yml`, then `just deploy common` |
| Stacks you run in Dockge | Dockge's own update buttons; Ansible does not manage them |
| This repo's tools | `just deps`; linter versions are pinned at the top of `justfile` |

Upgrade at a quiet time: a Docker Engine upgrade restarts the containers. Tailscale keeps its login.

## Disable or remove a service

Set `<name>_enabled: false` (or delete the line) to stop deploying it. That alone does not stop what is running: tear it down, then leave the flag false so later runs do not bring it back. `teardown.yml` refuses to run without `--limit <host>`.

```bash
ansible-playbook teardown.yml --limit <host> -e only=garage --vault-password-file .vault-pass   # one service, data kept (names: the keys in services.yml)
ansible-playbook teardown.yml --limit <host> --vault-password-file .vault-pass                  # everything the repo deployed, data kept
ansible-playbook teardown.yml --limit <host> -e remove_data=true -e confirm_remove_data=<host> --vault-password-file .vault-pass   # also wipes data: no undo without a backup
```

`remove_data=true` stops unless `confirm_remove_data` is the host's inventory name, and unless no folder to delete is, or holds, an [encrypted folder](../docs/encryption.md#turning-it-off). The paths it deletes are the `data` and `no_backup` fields of the service's entry in `services.yml`; verify a restore first.

**Never touched:** drive mounts, the restic password, Tailscale state and login, SSH keys, the sudoers file, installed packages, the timezone, Docker and containerd configuration, encrypted folders (ciphertext, `gocryptfs.conf`, master key, your scripts), Docker volumes, Dockge stacks, backup snapshots (restorable until retention prunes them), and the dumps and logs on the backup drive (`service-dumps`, `logs`; they hold a full database dump and Garage's node key).

**Removed only without `only`:** the journald, cloud-init and zram drop-ins, the memory cgroup arguments in the Pi's kernel command line (these take effect at the next boot), the terminal tools, the sleep masks, and Tailscale's apt source and key.

**Yours to clean up:** the service's `cloudflared_ingress` rule in `vars.yml`, and its Caddy name (gone once the flag is false and `just deploy caddy --limit <host>` has run).

Removing Tinyauth (`-e only=tinyauth`) leaves every protected name failing and, if `dockge_port` is `""`, Dockge without a login: Dockge's recovery is in [services.md](../docs/services.md#ad-hoc-app-platform).

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,defaults}`
2. `templates/docker-compose.yml.j2`: join the external `services` network, set `container_name` (use it for `container` in the `services.yml` entry and for a `cloudflared_ingress` service) and `restart: unless-stopped`, and take the image from a variable in `versions.yml` (`myservice_image: owner/myservice:1.2.3`; pin a version, or a digest if upstream has no versioned tag). Check the image has arm64 and x64 builds (`just platforms`).
3. `tasks/main.yml`: create the data dirs, then `import_role: compose_service` with `compose_service_name: myservice` (copy `roles/gitea`). A service that builds its own image or restarts on config changes writes its own tasks instead: copy `roles/backup_status`, the smallest.
4. `defaults/main.yml`: settings only this role reads.
5. `group_vars/all/`: `myservice_enabled: false` in `defaults-flags.yml`, the data directories in `defaults-data-dirs.yml` and, for a web UI, `myservice_port` and `myservice_subdomain` in `defaults-ports-and-names.yml`, each with a comment. A value with no sensible default goes in `vars.yml.example`.
6. `group_vars/all/services.yml`: one entry, e.g. `- {name: Myservice, key: myservice, compose: myservice, data: [myservice_data_dir]}` (no `data` if it has no data directories). The comment at the top of the file describes each field.
7. `site.yml`: an `import_role` task with the tag `myservice` and `when: myservice_enabled | bool`.
8. Its secrets go in the matching `vault.yml.example`, and a row naming `roles/myservice` in the table in [docs/services.md](../docs/services.md).
9. Optional: a public hostname needs a `cloudflared_ingress` rule; a live database needs `files/dump.sh` and `dump_required: true` in its entry (copy `roles/gitea`; [backups.md](../docs/backups.md)); data outside the offsite backup goes in `restic_cloud_extra_rules`.
10. `just check` fails with the exact missing line if steps 5 to 8 are incomplete. Then `just deploy myservice`.

Teardown, backup coverage, the Homepage tile and the Caddy name all come from the `services.yml` entry; the port and subdomain give the tile its link and the service its Caddy name under `caddy_private_domains`.
