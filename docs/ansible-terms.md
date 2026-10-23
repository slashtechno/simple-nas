# Ansible terms used in this repo

What Ansible does: you describe the desired state in YAML, and a run makes the Pi match it. Each step checks first and skips itself when already correct, so running a playbook twice is safe and brings a drifted Pi back to the defined state.

This is a reference for what the repo actually uses, not a tutorial. For operating the repo, see [ansible/README.md](../ansible/README.md).

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
- `host_key_checking = False`: skips the SSH host-key prompt. Acceptable for one known Pi.
- `become = True`, `become_method = sudo`: every task runs as root, so tasks don't repeat `become: true`.
- `pipelining = True`: faster deploys over SSH.

The inventory is `groups → hosts → connection vars`. `servers` is the parent of `nas` and `servers_general`; the first play in `site.yml` runs on `hosts: servers`, the second on `hosts: nas`. A host key (`pi4`) is a nickname that also names its `host_vars/pi4/` directory. `ansible_host`, `ansible_user` and `ansible_ssh_private_key_file` tell Ansible how to SSH in.

`requirements.yml` installs:

- Collections (bundles of modules): `community.general`, `community.docker`, `ansible.posix` and `artis3n.tailscale`.
- One role, `geerlingguy.docker`, which installs Docker itself.

## 2. Playbooks

A playbook is a list of plays. Each play runs roles or tasks against a group of hosts. `site.yml` has one play:

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
- **`when`**: `immich_enabled | default(true)` means "use the flag if set, otherwise true". This is how `<service>_enabled: false` skips a service. Core services default to true, opt-in ones (pics, crafty, garage) to false.
- **`roles:` vs `tasks:`**: `site.yml` is all roles. `teardown.yml` is tasks, one `block:` per service sharing one `tags:`, mostly through `teardown_service.yml`. Its play-level `remove_data: false` is what `-e remove_data=true` overrides.

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
- `find`: search for files into a registered variable (Garage's first-deploy check, cloudflared's credential migration)
- `git`: clone a repo (pics, through `github_clone`)

System:
- `apt`: install packages
- `community.general.timezone`: set the timezone
- `community.general.nmcli`: NetworkManager settings (the direct Ethernet link)
- `ansible.posix.mount`: manage an `fstab` entry and mount it
- `cron`: manage one crontab entry, identified by its `name:`. Re-running updates it instead of duplicating it, and `teardown.yml` removes it by name.
- `systemd`: control or query a unit

Docker:
- `docker_network`: create the shared `nas-services` network
- `docker_compose_v2`: `docker compose up`/`down` for a `project_src:` directory
- `docker_container_exec`: run a command in a running container (Garage reloads Caddy this way)

Flow and escape hatches:
- `assert`: fail early with a message (the storage role's drive checks)
- `set_fact`: set a variable mid-play
- `import_role`, `import_tasks`: pull in a role or task file when the playbook is parsed, so `--tags` still select tasks inside it. This repo uses these.
- `include_role`: the same at run time, where tags don't reach inside. Used only where a role is called mid-task: tailscale calls `artis3n.tailscale.machine`, and pics calls `github_clone`.
- `command`: run one binary, no shell features
- `shell`: full shell, used where a pipe is needed (cloudflared's `find | cp`)

Dedicated modules check state and change only what's wrong. `command` and `shell` run every time, so they carry `changed_when` or `failed_when` to say when something really changed. The Tailscale Funnel tasks show it: a read-only `funnel status --json` task (`changed_when: false`, `check_mode: false`) runs first, and the enable and disable tasks fire only when the state differs.

## 5. Task keywords

Keywords any task can carry:

- **`when:`**: run conditionally, with filters such as `| bool` and `| default(x)`.
- **`loop:`**: repeat once per list item.
- **`register:`**: capture a result. Garage sets `garage_is_first_deploy` from the registered `meta/` listing.
- **`changed_when:`, `failed_when:`**: override what counts as changed or failed. The restic-init task fails only if it errored and the message wasn't "already exists", so re-running is harmless.
- **`notify:` and handlers**: a changed task triggers a named handler, which runs once at the end of the play. If a rendered `docker-compose.yml` is byte-identical to the one on the Pi, nothing is notified and the container isn't touched.
- **`ignore_errors: true`**: keep going after a failure (teardown of a project that may not exist, migrating credentials that may not exist).
- **`become_user:`**: escalate to a specific user. restic-init runs as `ansible_user` because that user's home holds `.restic-password`.
- **`environment:`**: set environment variables for one task only (restic's repo and password file, git's token).
- **`block:`**: group tasks under one `tags:` or `when:`.

## 6. Variables and vault

Config comes from these sources, lowest precedence first:

1. `roles/*/defaults/main.yml`: a role's own settings, such as `crafty_panel_port`.
2. `group_vars/all/vars.yml`: settings every server reads (timezone, base paths).
3. `group_vars/nas/`: loaded for hosts in the `nas` group. `vars.yml` holds enabled flags, paths and non-secret settings, `versions.yml` every image version, `derived.yml` values computed from the others (not edited), `vault.yml` secrets.
4. `host_vars/<host>/vars.yml`: one host's settings, such as the direct link. Beats group values.

`vault.yml` is encrypted with `ansible-vault` (AES256) and decrypted in memory when `--ask-vault-pass` is given. A host only loads the vault files of its own groups, so a server outside `nas` needs no vault password.

`vars.yml` refers to secrets by passthrough, e.g. `copyparty_pass: "{{ vault_copyparty_pass }}"`. This is a convention, not an Ansible rule. Templates use `{{ copyparty_pass }}` without knowing it is secret, and `vars.yml` stays safe to commit because the values exist only in the encrypted file.

Edit the vault with `ansible-vault edit group_vars/nas/vault.yml`. Nothing can read or change it without the vault password.
