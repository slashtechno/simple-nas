# NAS Ansible playbooks

Each service is a role with its own Docker Compose project at `/opt/nas/<service>/` on the Pi, all on the shared Docker network `nas-services`. Ansible runs on your Mac and SSHes into the Pi, which only needs SSH and Python. New to Ansible? Read [docs/ansible-terms.md](../docs/ansible-terms.md) first.

Ansible owns what it deploys; you own everything else. Files it manages (`/opt/nas/*/docker-compose.yml`, cron jobs, rendered configs) are overwritten on the next run, so change them here. Anything outside that, such as SSH keys or manually installed packages, is yours and Ansible leaves it alone. Restarting a container by hand is fine.

## First-time setup

```bash
brew install ansible just uv   # uv runs the linters; Docker is only needed for `just tags`
cd ansible/
just deps
cp inventory/hosts.yml.example inventory/hosts.yml    # set each host's address and username
cp group_vars/all/vars.yml.example group_vars/all/vars.yml
cp group_vars/nas/vars.yml.example group_vars/nas/vars.yml
mkdir host_vars/<host>                                # named after the host in the inventory
cp host_vars/vars.yml.example host_vars/<host>/vars.yml   # keep only the options that host needs
cp group_vars/nas/vault.yml.example group_vars/nas/vault.yml
# fill in vault.yml with real secrets, then encrypt it:
ansible-vault encrypt group_vars/nas/vault.yml
```

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

Edit the file that owns the setting (below), then `just deploy <tag>`. Only changed services restart: compose-only services are recreated when their rendered file changes, and handlers cover Copyparty, Garage, pics, backup-status, cloudflared (new token), network and storage.

| Setting | File |
|---|---|
| Used by one role | that role's `defaults/main.yml` |
| Every server (timezone, base paths) | `group_vars/all/vars.yml`, mirrored in `vars.yml.example` |
| The NAS group (services, drives, backups) | `group_vars/nas/vars.yml`, mirrored in `vars.yml.example` |
| One host (direct link) | `host_vars/<host>/vars.yml`; the example `host_vars/vars.yml.example` serves every host |
| Secrets | a `vault.yml` next to the file they belong with |
| Image versions | `group_vars/all/versions.yml` |
| Computed from the above | `group_vars/nas/derived.yml`; not edited |

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

Pin a floating tag to the version running on the Pi once it works: `docker inspect <container>` shows `org.opencontainers.image.version`, or ask the app (`docker exec gitea gitea --version`). Moving Immich to a newer version can run database migrations, so read its notes first. Its Postgres and Valkey are pinned by digest; change them only when Immich's notes say to. Copyparty and backup-status build on the Pi and always rebuild, so `docker_pull_policy` doesn't apply to them.

## Disable or remove a service

Set `<name>_enabled: false` in `vars.yml` to stop deploying it (the flags are at the top of the file). To remove one that is already on the Pi, tear it down first, then set the flag so later runs don't bring it back:

```bash
ansible-playbook teardown.yml --tags garage --ask-vault-pass       # one service, data kept
ansible-playbook teardown.yml --ask-vault-pass                     # everything, data kept
ansible-playbook teardown.yml -e remove_data=true --ask-vault-pass # also wipes data: no undo without a backup
```

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,defaults}`
2. `templates/docker-compose.yml.j2`: join the external `nas-services` network. Take the image from a variable defined in `versions.yml`.
3. `tasks/main.yml`: create the data dirs, then `import_role: compose_service` with `compose_service_name: myservice`. Copy `roles/gitea`. A service that restarts on config changes (like `copyparty`) writes its own tasks and handlers instead.
4. `defaults/main.yml`: settings only this role reads. Shared values (data dirs, enabled flags, ports used in `cloudflared_ingress`) go in `group_vars/nas/vars.yml` and `vars.yml.example`.
5. `site.yml`: add `- role: myservice` with a tag and `when: myservice_enabled | default(false)` (opt-in; `true` only for core services).
6. `teardown.yml`: add an entry using `import_tasks: teardown_service.yml` with `service` and `data_paths`.
7. A public hostname needs a `cloudflared_ingress` rule.
8. A live database needs `files/dump.sh`, installed into `service_dump_scripts_dir` (copy `roles/gitea`; see [../docs/backups.md](../docs/backups.md)). Plain files need nothing; add the data dir to `restic_cloud_extra_paths` to send it offsite.
9. `just deploy myservice`
