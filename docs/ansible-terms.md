# Ansible terms used in this repo

You describe the desired state in YAML, and a run makes each host match it. Each step checks first and skips itself when already correct, so running a playbook twice is safe and puts a drifted host back to the defined state.

This lists what the repo uses. For operating the repo, see [ansible/README.md](../ansible/README.md).

## 1. Files that make Ansible work

| File | Role |
|---|---|
| `ansible.cfg` | Project settings, read automatically from this directory |
| `inventory/hosts.yml` | Who to run against |
| `group_vars/all/`, `group_vars/nas/`, `host_vars/<host>/` | What values to run with: every server, the NAS group, one host (`vars.yml`, `versions.yml`, `derived.yml`, `vault.yml`) |
| `requirements.yml` | Collections and roles to install first (`just deps`) |
| `site.yml`, `teardown.yml` | The playbooks |
| `roles/*/` | How to deploy each piece |

`ansible.cfg` keys:

- `roles_path = ~/.ansible/roles:roles`: where role names are looked up, in order. The first is Galaxy-installed roles (not committed), the second is this repo's.
- `host_key_checking = False`: skips the SSH host-key prompt.
- `become = True`, `become_method = sudo`: every task runs as root.
- `inventory = inventory/hosts.yml`: the default inventory.
- `interpreter_python = /usr/bin/python3`: fixed so Ansible does not warn about discovering Python.
- `pipelining = True`: faster deploys over SSH.

The inventory is `groups → hosts → connection vars`. `servers` is the parent of `nas` and `servers_general`. The plays in `site.yml` run on `servers` (base roles), `nas` (services and backups) and `servers_general` (Dockge, Caddy). A host key (`pi4`) is a nickname that also names its `host_vars/pi4/` directory. `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file` tell Ansible how to SSH in.

`requirements.yml` installs:

- Collections (bundles of modules): `community.general`, `community.docker`, `ansible.posix` and `artis3n.tailscale`.
- One role, `geerlingguy.docker`, which installs Docker itself.

## 2. Playbooks

A playbook is a list of plays. Each play runs roles or tasks against a group of hosts. `site.yml` has three plays; the one for the `nas` group looks like this (abridged):

```yaml
- name: Deploy NAS
  hosts: nas
  become: true
  roles:
    - role: immich
      tags: [immich]
      when: immich_enabled | default(true)
```

- **`tags`**: run a subset, e.g. `--tags immich` or `--tags backup,storage`.
- **`when`**: `immich_enabled | default(true)` means "use the flag if set, otherwise true". This is how `<service>_enabled: false` skips a service. Core services default to true, opt-in ones (pics, crafty, garage, caddy) to false.
- **`roles:` vs `tasks:`**: `site.yml` is all roles. `teardown.yml` is tasks, one entry per service with its own `tags:`, mostly through `teardown_service.yml`, in one play for `nas` and one for `servers_general`. The play-level `remove_data: false` is what `-e remove_data=true` overrides.

## 3. Role anatomy

| Directory | Purpose | Used here |
|---|---|---|
| `tasks/main.yml` | The steps | Always |
| `handlers/main.yml` | Tasks that run only when notified | Some roles |
| `templates/*.j2` | Jinja2 files rendered with variables | Most roles |
| `files/*` | Static files copied as-is | Some roles |
| `defaults/main.yml` | The role's own fallback values (lowest precedence) | Roles with settings only they read |
| `meta/main.yml` | Roles to run first | Only `common/` |

`template` substitutes `{{ variable }}`; `copy` from `files/` copies the bytes unchanged. Using `copy` on a file containing `{{ }}` doesn't error, it silently leaves the text as is. That is why Dockerfiles get their base image through `ARG` and compose `build.args` rather than a variable.

`common/meta/main.yml` makes `geerlingguy.docker` run before `common`'s own tasks, which is how Docker gets installed without `site.yml` mentioning it.

## 4. Modules

Every task calls one module.

Files:
- `file`: create, own or permission a path, or delete it (`state: absent`)
- `copy`: push a static file or a literal `content:` string
- `template`: render a `.j2` file, then push it
- `find`: search for files into a registered variable (Garage's first-deploy check)
- `git`: clone a repo (pics, through `github_clone`)
- `get_url`, `unarchive`: download and unpack a release (zellij)
- `lineinfile`: set one line in a file (containerd's `config.toml`)
- `ansible.posix.authorized_key`: add SSH public keys
- `stat`: check whether a path exists

System:
- `apt`: install packages
- `community.general.timezone`: set the timezone
- `community.general.nmcli`: NetworkManager settings (the direct Ethernet link)
- `ansible.posix.mount`: manage an `fstab` entry and mount it
- `cron`: manage one crontab entry, identified by its `name:`. Re-running updates it instead of duplicating it, and `teardown.yml` removes it by name.
- `systemd`, `systemd_service`: control or query a unit

Docker:
- `docker_network`: create the shared `nas-services` network
- `docker_compose_v2`: `docker compose up`/`down` for a `project_src:` directory
- `docker_container`: remove or run one container outside compose (cloudflared removes a leftover init container)
- `docker_container_exec`: run a command in a running container (Garage reloads Caddy this way)

Flow and escape hatches:
- `uri`: call an HTTP API (the cloudflared role calls Cloudflare's)
- `assert`: fail early with a message (the storage role's drive checks)
- `set_fact`: set a variable mid-play
- `import_role`, `import_tasks`: pull in a role or task file when the playbook is parsed, so `--tags` still select tasks inside it. This repo uses these.
- `include_role`: the same at run time, where tags don't reach inside. Used only where a role is called mid-task: tailscale calls `artis3n.tailscale.machine`, and pics calls `github_clone`.
- `command`: run one binary, no shell features
- `shell`: full shell, for when a pipe is needed (no role uses it)

Dedicated modules check state and change only what's wrong. `command` and `shell` run every time, so they carry `changed_when` or `failed_when` to say when something really changed. The Tailscale Funnel tasks show it: a read-only `funnel status --json` task (`changed_when: false`, `check_mode: false`) runs first, and the enable and disable tasks fire only when the state differs.

## 5. Task keywords

Keywords any task can carry:

- **`when:`**: run conditionally, with filters such as `| bool` and `| default(x)`.
- **`loop:`**: repeat once per list item.
- **`register:`**: capture a result. Garage sets `garage_is_first_deploy` from the registered `meta/` listing.
- **`changed_when:`, `failed_when:`**: override what counts as changed or failed. The restic-init task fails only if it errored and the message wasn't "already exists", so re-running is harmless.
- **`notify:` and handlers**: a changed task triggers a named handler, which runs once at the end of the play. If a rendered `docker-compose.yml` is byte-identical to the one on the Pi, nothing is notified and the container isn't touched.
- **`ignore_errors: true`**: keep going after a failure (teardown of a project that may not exist). Each use carries a `noqa` comment saying why.
- **`delegate_to: localhost`**: run a task on your Mac instead of the host (the Cloudflare API calls).
- **`check_mode: false`**: run a read-only task even under `--check`.
- **`become_user:`**: escalate to a specific user. restic-init runs as `ansible_user` because that user's home holds `.restic-password`.
- **`environment:`**: set environment variables for one task only (restic's repo and password file, git's token).
- **`block:`**: group tasks under one `tags:` or `when:`.

## 6. Variables and vault

Config comes from these sources, lowest precedence first:

1. `roles/*/defaults/main.yml`: a role's own settings, such as `crafty_panel_port`.
2. `group_vars/all/`: loaded for every host. `vars.yml` holds settings every server reads (timezone, base paths, SSH keys, Docker options, `drives: []`), `versions.yml` every image and tool version, `derived.yml` values computed from the others (`fast_drive`, `primary_drive`, `backup_drive`, `docker_daemon_options`), `vault.yml` the secrets every host needs (Cloudflare token and account, restic password, rclone token). Backup settings (`restic_*`) are here too.
3. `group_vars/nas/`: loaded for hosts in the `nas` group. `vars.yml` holds enabled flags, paths and non-secret settings, `vault.yml` secrets.
4. `host_vars/<host>/vars.yml`: one host's settings, such as `drives` and the direct link. Beats group values.

`vault.yml` is encrypted with `ansible-vault` (AES256) and decrypted in memory when `--ask-vault-pass` is given. A host loads the vault files of `all` and of its own groups. A key defined in both takes the group's value.

`vars.yml` refers to secrets by passthrough, e.g. `copyparty_pass: "{{ vault_copyparty_pass }}"`. This is a convention, not an Ansible rule. Templates use `{{ copyparty_pass }}` without knowing it is secret, and `vars.yml` stays safe to commit because the values exist only in the encrypted file.

Edit a vault with `ansible-vault edit group_vars/nas/vault.yml` (or `group_vars/all/vault.yml`). Nothing can read or change it without the vault password.
