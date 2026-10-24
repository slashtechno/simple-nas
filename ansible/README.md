# NAS Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/nas/<service>/` on the host, all on the shared Docker network `nas-services`. Ansible runs on your Mac and SSHes into each host, which only needs SSH and Python. New to Ansible? Read [docs/ansible-terms.md](../docs/ansible-terms.md) first.

Files Ansible manages (`/opt/nas/*/docker-compose.yml`, cron jobs, rendered configs) are overwritten on the next run, so change them here. Everything else on the host is yours and Ansible leaves it alone. Restarting a container by hand is fine.

## Which files hold what

| File | In git | Holds | Create it |
|---|---|---|---|
| `inventory/hosts.yml` | no (addresses) | Hosts, groups (`nas`, `servers_general`), SSH user and key | Copy `hosts.yml.example` |
| `group_vars/all/vars.yml` | yes | Settings every server reads (timezone, SSH keys, backups, Cloudflare account) | Copy `vars.yml.example` |
| `group_vars/nas/vars.yml` | yes | NAS services on or off, their data paths, hostnames | Copy `vars.yml.example` |
| `host_vars/<host>/vars.yml` | yes | One host: its `drives`, direct link, `docker_data_root`, Dockge, Caddy and Cloudflared settings | Copy `host_vars/vars.yml.example`, keep only what the host needs |
| `group_vars/all/vault.yml` | no (secrets) | Secrets every host uses: Cloudflare token, restic password, rclone token | Copy `vault.yml.example`, fill in, encrypt |
| `group_vars/nas/vault.yml` | no (secrets) | NAS-only secrets (database passwords, Copyparty logins) | Same |
| `group_vars/all/versions.yml` | yes | Every image version | Already there |

Encrypt both vaults with the same password: `ansible-vault encrypt group_vars/all/vault.yml group_vars/nas/vault.yml`. Anything secret goes in a vault, never in `vars.yml`; `.gitignore` keeps `vault.yml` and `hosts.yml` out of git. A `servers_general` host that runs backups or a tunnel needs `group_vars/all/vault.yml`; one that uses no secret works without it.

## First-time setup

```bash
brew install ansible just uv   # uv runs the linters; Docker is only needed for `just tags`
cd ansible/
just deps
```

Then create the files in the table above, set up each new host ([docs/plans/multi-host.md](../docs/plans/multi-host.md) walks through pi4 and pi5), and run `just deploy '' --limit <host> -K`. The first deploy to a host needs its sudo password once; after that, the sudoers file the `common` role installs makes `-K` unnecessary.

## Using this repo for your own hosts

The tracked `vars.yml` files hold the repo owner's values (domains, SSH public key, timezone, drive UUIDs), kept in git so the owner's setup is reproducible. Anyone else who copies the repo replaces them:

1. Overwrite each tracked `vars.yml` with its `vars.yml.example` (`group_vars/all`, `group_vars/nas`) and delete `host_vars/pi4/`.
2. Replace at least `ssh_authorized_keys` (the owner's key would otherwise be added to your hosts), `timezone`, the Gitea and Cloudflare hostnames, and `restic_cloud_repository`.
3. Create `inventory/hosts.yml`, the vaults and your own `host_vars/<host>/vars.yml` as in the table.

## Commands

[`just`](https://just.systems) is a plain command runner. Run `just` in `ansible/` to list the recipes; each is a short shell snippet in `justfile`.

| Command | Does |
|---|---|
| `just check` | Everything below; run before committing (CI runs it too) |
| `just lint` | ansible-lint, shellcheck on shipped scripts, ruff on the dashboard. Skipped rules and their reasons: `.ansible-lint` |
| `just syntax` | Both playbooks parse |
| `just test` | Renders every template with the example vars and shellchecks the scripts. Fails on an undefined variable or a key in a `vars.yml` missing from its example |
| `just deploy [tags] [flags]` | `site.yml` with `--ask-vault-pass`, optionally `--tags`, e.g. `just deploy immich`. Flags go after the tags: `just deploy '' --limit pi5 -K` |
| `just preview [tags] [flags]` | The same with `--check --diff`, which changes nothing |
| `just tags <image> [filter] [count]` | Lists an image's tags, e.g. `just tags dxflrs/garage '^v2\.'`. Needs Docker running on your Mac. Optional: the registry's tags page shows the same list |

`--check` does not create directories, so on a first deploy a later step can fail with "not a directory". That is a preview limit, not a bug.

## Change a setting

Edit the file that owns the setting (below), then `just deploy <tag>`. Only changed services restart: compose-only services are recreated when their rendered file changes, and handlers cover Copyparty, Garage, pics, backup-status, cloudflared (new token), containerd, the direct-link dnsmasq and storage (udev rules).

| Setting | File |
|---|---|
| Used by one role | that role's `defaults/main.yml` |
| Every server (timezone, base paths) | `group_vars/all/vars.yml`, mirrored in `vars.yml.example` |
| The NAS group (services, backups) | `group_vars/nas/vars.yml`, mirrored in `vars.yml.example` |
| One host (its drives, direct link, Docker data root, Dockge, Caddy and Cloudflared settings) | `host_vars/<host>/vars.yml`; the example `host_vars/vars.yml.example` serves every host |
| Secrets | a `vault.yml` next to the file they belong with |
| Image versions | `group_vars/all/versions.yml` |
| Computed from the above | `group_vars/all/derived.yml`; not edited |

Options in `defaults/main.yml` and the example files have this comment shape: what it does in one sentence, then `Allowed: ... Default: ...` when not obvious, then `CAUTION: ...` where changing it later has a consequence. Options private to a role start with the role name.

Service setup and gotchas are in [../docs/services.md](../docs/services.md); drives are in [../docs/storage.md](../docs/storage.md).

## Update service images

Every image and version is a line in `group_vars/all/versions.yml`, with its release-notes link above it. To update one:

1. Read the release notes.
2. Edit that line (`just tags <image>` lists the tags that exist).
3. `just preview <service>`, then `just deploy <service>`.

A floating tag (`latest`, `release`, `nightly`) doesn't move until you ask, because deploys use `pull: missing`:

```bash
ansible-playbook site.yml --tags gitea -e docker_pull_policy=always --ask-vault-pass
```

Pin a floating tag to the version running on the host once it works: `docker inspect <container>` shows `org.opencontainers.image.version`, or ask the app (`docker exec gitea gitea --version`). Moving Immich to a newer version can run database migrations, so read its notes first. Its Postgres and Valkey are pinned by digest; change them only when Immich's notes say to. Copyparty and backup-status build on the host and always rebuild, so `docker_pull_policy` doesn't apply to them.

## Disable or remove a service

Set `<name>_enabled: false` in `group_vars/nas/vars.yml` (or in `host_vars/<host>/vars.yml` for Dockge, Caddy and Cloudflared on a general server) to stop deploying it. To remove one that is already on a host, tear it down first, then set the flag so later runs don't bring it back:

```bash
ansible-playbook teardown.yml --tags garage --ask-vault-pass       # one service, data kept
ansible-playbook teardown.yml --tags dockge --limit <host>         # a general-server service
ansible-playbook teardown.yml --ask-vault-pass                     # everything, data kept
ansible-playbook teardown.yml -e remove_data=true --ask-vault-pass # also wipes data: no undo without a backup
```

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,defaults}`
2. `templates/docker-compose.yml.j2`: join the external `nas-services` network. Take the image from a variable defined in `versions.yml`.
3. `tasks/main.yml`: create the data dirs, then `import_role: compose_service` with `compose_service_name: myservice`. Copy `roles/gitea`. A service that restarts on config changes (like `copyparty`) writes its own tasks and handlers instead.
4. `defaults/main.yml`: settings only this role reads. Shared values (data dirs, enabled flags, ports used in `cloudflared_ingress`) go in `group_vars/nas/vars.yml` and `vars.yml.example`.
5. `site.yml`: add `- role: myservice` with a tag and `when: myservice_enabled | default(false)` (opt-in; `true` only for core services), in the play for the group it runs on (`nas` or `servers_general`).
6. `teardown.yml`: add an entry using `import_tasks: teardown_service.yml` with `service` and `data_paths`, in the play for the group the service runs on.
7. A public hostname needs a `cloudflared_ingress` rule.
8. A live database needs `files/dump.sh`, installed into `service_dump_scripts_dir` (copy `roles/gitea`; see [../docs/backups.md](../docs/backups.md)). Plain files need nothing; add the data dir to `restic_cloud_rules` to send it offsite.
9. `just deploy myservice`
