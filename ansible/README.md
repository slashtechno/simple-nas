# NAS Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/nas/<service>/` on the host, all on the shared Docker network `nas-services`. Ansible runs on your Mac and SSHes into each host, which only needs SSH and Python. New to Ansible? Read [docs/ansible-terms.md](../docs/ansible-terms.md) first.

Files Ansible manages (`/opt/nas/*/docker-compose.yml`, cron jobs, rendered configs) are overwritten on the next run, so change them here. Everything else on the host is yours and Ansible leaves it alone. Restarting a container by hand is fine.

## First-time setup

```bash
brew install ansible just uv   # uv runs the linters; Docker is only needed for `just tags`
cd ansible/
just deps
cp inventory/hosts.yml.example inventory/hosts.yml    # one entry per host, under the group `nas` or `servers_general`
cp group_vars/all/vars.yml.example group_vars/all/vars.yml
cp group_vars/nas/vars.yml.example group_vars/nas/vars.yml
mkdir host_vars/<host>                                # named after the host in the inventory
cp host_vars/vars.yml.example host_vars/<host>/vars.yml   # keep only the options that host needs
cp group_vars/all/vault.yml.example group_vars/all/vault.yml   # secrets every host uses
cp group_vars/nas/vault.yml.example group_vars/nas/vault.yml   # NAS-only secrets
# fill in both with real secrets, then encrypt them (same password):
ansible-vault encrypt group_vars/all/vault.yml group_vars/nas/vault.yml
```

`group_vars/all/vault.yml` is read by every host, so a `servers_general` host that runs backups or a tunnel needs it; a host that uses no secret is fine without it. The first deploy to a new host needs the sudo password once: `just deploy '' --limit <host> -K`. After that, the sudoers file the `common` role installs makes it unnecessary.

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
| One host (its drives, direct link, Docker data root, Dockge and Caddy flags) | `host_vars/<host>/vars.yml`; the example `host_vars/vars.yml.example` serves every host |
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

Set `<name>_enabled: false` in `group_vars/nas/vars.yml` (or in `host_vars/<host>/vars.yml` for Dockge and Caddy) to stop deploying it. To remove one that is already on a host, tear it down first, then set the flag so later runs don't bring it back:

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
8. A live database needs `files/dump.sh`, installed into `service_dump_scripts_dir` (copy `roles/gitea`; see [../docs/backups.md](../docs/backups.md)). Plain files need nothing; add the data dir to `restic_cloud_extra_paths` to send it offsite.
9. `just deploy myservice`
