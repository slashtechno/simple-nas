# Ansible terms used in this repo

You describe the desired state in YAML, and a run makes each host match it. Each step checks first and skips itself when already correct, so running a playbook twice is safe and puts a drifted host back to the defined state.

This lists what the repo uses. For operating the repo, see [ansible/README.md](../ansible/README.md).

## 1. Files that make Ansible work

| File | Role |
|---|---|
| `ansible.cfg` | Project settings, read automatically from this directory |
| `inventory/hosts.yml` | Who to run against |
| `group_vars/all/`, `host_vars/<host>/` | What values to run with: every host (`defaults.yml`, `vars.yml`, `versions.yml`, `vault.yml`), or one host (`vars.yml`, `vault.yml`) |
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

The inventory is `groups → hosts → connection vars`. This repo has one group, `servers`, and both playbooks run on it. The group carries no settings; what a host runs is set in its own `host_vars/<host>/vars.yml`. A host key (`pi4`) is a nickname that also names its `host_vars/pi4/` directory. `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file` tell Ansible how to SSH in.

`requirements.yml` installs:

- Collections (bundles of modules): `community.general`, `community.docker`, `ansible.posix` and `artis3n.tailscale`.
- One role, `geerlingguy.docker`, which installs Docker itself.

## 2. Playbooks

A playbook is a list of plays. Each play runs roles or tasks against a group of hosts. `site.yml` is one play over `servers`. Each service is a task that imports a role, and the task's `when` is the service's flag:

```yaml
- name: Deploy immich
  ansible.builtin.import_role:
    name: immich
  tags: [immich]
  when: immich_enabled | bool
```

- **`tags`**: run a subset, e.g. `--tags immich` or `--tags backup,storage`.
- **`when`**: `immich_enabled | bool` is true only on a host whose `host_vars` set `immich_enabled: true`. Every flag defaults to false in `group_vars/all/defaults.yml`, so a service is skipped unless a host asks for it.
- **`import_role` vs `include_role`**: see section 4. This repo uses `import_role` so `--tags` reach inside the role.
- **`pre_tasks`**: run before the others. `site.yml` uses them to check the OS and that Docker is not a snap; they carry `tags: [always]`.
- **`teardown.yml`** is one play of tasks, one entry per service with its own `tags:`, mostly through `teardown_service.yml`. It refuses to run without `--limit`. The play-level `remove_data: false` is what `-e remove_data=true` overrides.

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
- `docker_network`: create the shared Docker network (`docker_network`, named `services`)
- `docker_compose_v2`: `docker compose up`/`down` for a `project_src:` directory
- `docker_container`: remove or run one container outside compose (cloudflared removes a leftover init container)

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
2. `group_vars/all/defaults.yml`: settings several roles share, each with a default, including every `<name>_enabled` flag (all false). Not edited per host.
3. `group_vars/all/vars.yml`: your values that apply to every host (timezone, SSH keys, Cloudflare zones). `versions.yml` holds every image and tool version, `vault.yml` the secrets hosts share (Cloudflare token and account, restic password, rclone token, ntfy token).
4. `host_vars/<host>/vars.yml`: one host's settings, such as its flags, `drives` and the direct link. Beats everything above. `host_vars/<host>/vault.yml` holds that host's service secrets.

Every shared setting and its default is in `ansible/group_vars/all/defaults.yml`; a setting only one role uses is in that role's `defaults/main.yml`. Vault names are in the two `vault.yml.example` files.

`vault.yml` is encrypted with `ansible-vault` (AES256) and decrypted in memory when `--ask-vault-pass` is given. A host loads `group_vars/all/vault.yml` and its own `host_vars/<host>/vault.yml`. A key defined in both takes the host's value.

Settings refer to secrets by passthrough, e.g. `copyparty_pass: "{{ vault_copyparty_pass }}"` in `defaults.yml`. This is a convention, not an Ansible rule. Templates use `{{ copyparty_pass }}` without knowing it is secret, and the committed files stay safe because the values exist only in the encrypted file.

Edit a vault with `ansible-vault edit host_vars/<host>/vault.yml` (or `group_vars/all/vault.yml`). Nothing can read or change it without the vault password.

## 7. Jinja: the less common expressions

Values in `{{ ... }}` are Jinja2. A `|` passes the value on its left through a filter, like a shell pipe. Most of the repo uses only `{{ name }}`, `| bool`, `| length` and `| default(x)`. These are the others, with where to find an example:

| Expression | Means | Used in |
|---|---|---|
| `{{ undef(hint='...') }}` | "No default: the owner must set this." Reading the variable before it is set stops the run and prints the hint. The setting is listed in `vars.yml.example`. | `pics_repo`, `gitea_*` in `group_vars/all/defaults.yml` |
| `x \| mandatory('message')` | Stops the run with that message if `x` is missing. Used so an unclaimed drive role names what to add. | `fast_drive`, `primary_drive`, `backup_drive` in `group_vars/all/defaults.yml` |
| `a \| combine(b)` | Merges two dictionaries; `b` wins. | `docker_daemon_options` in `group_vars/all/defaults.yml` |
| `list \| map(attribute='x')` | The `x` of every item in a list of dictionaries. | `roles/storage/tasks/main.yml` |
| `list \| selectattr('x')` | Keeps the items whose `x` is true. | `roles/storage/tasks/main.yml` |
| `a \| difference(b)`, `a \| intersect(b)` | Items of `a` not in `b`; items in both. | `roles/cloudflared/tasks/main.yml` |
| `dict \| dict2items` | A dictionary as a list of `key` / `value` pairs, so it can be looped over. | `roles/cloudflared/tasks/main.yml` |
| `list \| flatten` | A list of lists as one list. | `roles/cloudflared/tasks/main.yml` |
| `names \| map('extract', hostvars)` | Looks each host name up in `hostvars`, the variables of every host in the inventory. | `roles/cloudflared/tasks/main.yml` |
| `a if cond else b` | Picks `a` or `b`. | many templates |
| `{% if %}`, `{% for %}` | Template logic in `.j2` files; the `{% %}` lines produce no output. | `roles/*/templates/` |

To try an expression without deploying: `ansible localhost -m debug -a "msg={{ ['a','b'] | difference(['a']) }}"`.
