# Ansible Terms & Config Keys Used In This Repo

A reference for every Ansible concept, module, and config key this project actually
uses — not a general Ansible tutorial, just what's here and why.

---

## 1. The files that make Ansible work at all

| File | Role |
|---|---|
| `ansible.cfg` | Project-level settings, read automatically when running `ansible-playbook` from this directory |
| `inventory/hosts.yml` | *Who* to run against |
| `group_vars/nas/vars.yml` + `vault.yml` | *What values* to run with |
| `requirements.yml` | *What dependencies* (collections/roles) must be installed first |
| `site.yml` / `teardown.yml` | *What to do* — the playbooks |
| `roles/*/` | *How* to do each piece |

### `ansible.cfg` keys used here

- `roles_path = ~/.ansible/roles:roles` — where to look for roles referenced by name
  (like `geerlingguy.docker`), searched in order. `~/.ansible/roles` holds
  Galaxy-installed roles (not committed to git); `roles` is this repo's own custom
  roles.
- `host_key_checking = False` — skip the interactive SSH host-key confirmation
  prompt. Reasonable for a single known Pi you already trust.
- `become = True` / `become_method = sudo` under `[privilege_escalation]` — every
  task runs as root via `sudo`, globally, without needing `become: true` on each
  task. `become` is a generic privilege-escalation abstraction (works with `sudo`,
  `su`, `doas`, etc.) — setting it once here means switching escalation methods
  later is a one-line change, not an edit to every role.

### Inventory (`inventory/hosts.yml`)

A YAML tree of `groups → hosts → connection vars`. `nas:` is the group name
(matched by `hosts: nas` in `site.yml`); the host key (`pi`/`pi4`) is just a
display nickname, not a real hostname. `ansible_host`, `ansible_user`,
`ansible_ssh_private_key_file` are "magic" variables Ansible reads to know how to
SSH in — this file has zero application config, purely connection info.

### `requirements.yml`

Declares two kinds of dependency Ansible Galaxy can install:

- **`collections:`** — bundles of modules (the verbs tasks call). This repo pulls
  in `community.general` (generic system modules), `community.docker`
  (Docker/Compose modules), and `ansible.posix` (POSIX-specific modules like
  `mount`).
- **`roles:`** — whole pre-built roles, not just modules. `geerlingguy.docker` (a
  widely-used community role that installs Docker itself) and `artis3n.tailscale`
  (installs/configures Tailscale) are used wholesale instead of hand-rolling that
  logic.

---

## 2. The playbooks: `site.yml` and `teardown.yml`

A playbook is a list of **plays**; each play targets a set of hosts and runs a
list of **roles** or **tasks** against them. `site.yml` has one play:

```yaml
- name: Deploy NAS
  hosts: nas          # the inventory group to target
  become: true        # escalate to root for every task in this play
  roles:
    - role: immich
      tags: [immich]
      when: immich_enabled | default(true)
```

Three keywords do the work:

- **`tags`** — run a subset: `ansible-playbook site.yml --tags immich` runs only
  the `immich` role. This is what makes `--tags homebridge` or
  `--tags backup,storage` possible instead of redeploying everything.
- **`when`** — a per-role conditional. `immich_enabled | default(true)` reads as
  "use `immich_enabled` if set, otherwise default to `true`." This is the
  mechanism behind "set `<service>_enabled: false` to skip a service."
- **`roles:`** vs `tasks:` — `site.yml` is 100% role-based; all real work lives
  inside each role. `teardown.yml` uses `tasks:` and `block:` instead, because
  teardown logic is more ad hoc per-service than a reusable deploy unit. Each
  `block:` groups a few tasks under one `tags:`, and `remove_data: false`
  (settable via `-e remove_data=true`) is a play-level `vars:` default every
  task's `when: remove_data | bool` reads.

---

## 3. Role anatomy

Every role in `roles/` follows Ansible's fixed directory convention:

| Directory | Purpose | Used here? |
|---|---|---|
| `tasks/main.yml` | The actual steps | Always |
| `handlers/main.yml` | Tasks that only run when *notified* | Most roles |
| `templates/*.j2` | Jinja2 files rendered with variables | Most roles |
| `files/*` | Static files copied verbatim, no templating | Some roles |
| `defaults/main.yml` | Role's own fallback variable values (lowest precedence) | Only `tailscale/` |
| `meta/main.yml` | Role dependencies (run automatically before this role) | Only `common/` |

`templates/` vs `files/` is a real distinction: `ansible.builtin.template` runs
the file through Jinja2 first (so `{{ variable }}` gets substituted), while
`ansible.builtin.copy` with `src:` pointing into `files/` copies bytes as-is.
That's why `copyparty/files/Dockerfile` is static (no Ansible variables in it)
while `copyparty/templates/copyparty.conf.j2` interpolates `{{ copyparty_user }}`
and loops over `vault_copyparty_collab_users`. Using `copy` on a file containing
`{{ }}` just copies that literal text — it does not error, it silently fails to
substitute.

`meta/main.yml` (only `common/`) declares a **role dependency**:

```yaml
dependencies:
  - role: geerlingguy.docker
    vars: {docker_users: ["{{ ansible_user }}"], ...}
```

This means "before running `common`'s own tasks, run this entire other role
first, with these variables." It's how `site.yml` gets Docker installed without
ever mentioning Docker installation itself.

---

## 4. The modules (the actual verbs)

Every task calls exactly one module — the thing that does work, as opposed to
Ansible's own control-flow keywords (`when`, `loop`, `notify`, etc., see below).

**Files & directories**

- `ansible.builtin.file` — create/own/permission a directory or file, or delete
  one (`state: absent`, used throughout `teardown.yml`)
- `ansible.builtin.copy` — push a static file (or literal `content:` string, as
  used for `.restic-password`) to the remote host
- `ansible.builtin.template` — render a `.j2` Jinja2 file with variables
  substituted, then push it
- `ansible.builtin.find` — search for files matching a pattern, return results
  into a `register`ed variable (garage's "is this the first deploy" check;
  cloudflared's credential migration)

**System / OS**

- `ansible.builtin.apt` — install Debian/Ubuntu packages (Raspberry Pi OS is
  Debian-based)
- `community.general.timezone` — set the system timezone declaratively
- `ansible.posix.mount` — manage an `/etc/fstab` entry *and* actually
  mount/unmount it in one module
- `ansible.builtin.cron` — manage one crontab entry idempotently, identified by
  its `name:` (becomes a `#Ansible: <name>` comment marker — how re-running
  updates the same entry instead of duplicating it, and how `teardown.yml`'s
  `state: absent` finds the right line to remove)
- `ansible.builtin.systemd` — control/query a systemd unit (used for
  `daemon_reload: true` after installing the drive auto-remount service)

**Docker**

- `community.docker.docker_network` — create the shared `nas-services` bridge
  network
- `community.docker.docker_compose_v2` — the Ansible-native equivalent of
  `docker compose up`/`down`/`restart`, driven by a `project_src:` directory
  containing a `docker-compose.yml`
- `community.docker.docker_container_exec` — run a command inside an
  already-running container (Garage role uses this to `caddy reload` without
  restarting the whole Caddy container)

**Escape hatches**

- `ansible.builtin.command` — run one binary with arguments, no shell features
  (pipes, `&&`, env expansion) unless added explicitly
- `ansible.builtin.shell` — full shell semantics, used once (cloudflared's
  credential-migration `find | cp` pipeline) because `command` can't pipe
- `ansible.builtin.include_role` — pull in a role by name from inside a task
  list rather than a play's `roles:` list (tailscale role uses this to invoke
  the Galaxy-installed `artis3n.tailscale.tailscale` role)

`command`/`shell` are "escape hatches" because Ansible's philosophy is that a
dedicated module is idempotent by construction — it checks current state and
only changes what's wrong — while `command`/`shell` just run a binary every
time, blind to whether anything needed changing. That's why nearly every
`command`/`shell` task here pairs with `changed_when`/`failed_when` — manually
bolting idempotency onto a tool that doesn't have it natively. The Tailscale
Funnel tasks are the clearest case: there's no dedicated Funnel module, so
`command` is the only option, and `changed_when: true` is an honest admission
that Ansible can't know whether toggling funnel actually changed anything.

---

## 5. Task-level control-flow keywords

Not modules — keywords any task can carry, controlling whether/how the module
runs:

- **`when:`** — conditional execution. Uses Jinja filters like `| bool`
  (coerce to true/false) and `| default(x)` (fallback if undefined).
- **`loop:`** — run the same task once per item in a list (storage role's
  directory-creation task; copyparty's account rendering over
  `vault_copyparty_collab_users`).
- **`register:`** — capture a task's result into a variable for later tasks.
  Garage's first-deploy detection: `register: garage_meta_contents` →
  `set_fact: garage_is_first_deploy: "{{ garage_meta_contents.matched == 0 }}"`.
- **`changed_when:` / `failed_when:`** — override Ansible's default idea of
  "did this succeed / change anything," as a Jinja condition against the
  `register`ed result. Example — the restic-init task:
  `failed_when: [restic_init.rc != 0, "'already exists' not in restic_init.stderr"]`
  — fail only if it errored *and* the error wasn't just "already initialized."
  This is how re-running against an already-initialized repo stays a harmless
  no-op.
- **`notify:` + handlers** — a task can `notify: Restart Gitea`; the named
  handler only fires once, at the end of the play, and only if some notifying
  task reported `changed`. This is why editing vars and re-running only
  restarts what actually changed — if a rendered `docker-compose.yml` is
  byte-identical to what's already there, nothing notifies, and the running
  container is left untouched.
- **`ignore_errors: true`** — swallow a task failure and keep going (teardown's
  "down a compose project that might not exist"; cloudflared's "migrate old
  credentials if the old location happens to exist").
- **`become_user:`** — like `become`, but escalates to a specific non-root user
  (restic-init runs as `ansible_user`, not root, because that's whose home
  directory holds `.restic-password`).
- **`environment:`** — set process environment variables for just one task
  (passing `RESTIC_PASSWORD_FILE`/`RESTIC_REPOSITORY` into `restic init` without
  polluting the whole shell).
- **`block:`** — group several tasks to share one `tags:`/`when:` without
  repeating it per task (every per-service section of `teardown.yml`).

---

## 6. Variables and Vault — where config actually lives

Ansible has a variable-precedence system; this repo exercises three tiers:

1. **`roles/*/defaults/main.yml`** — lowest precedence, a role's own fallback
   (only `tailscale/` defines any: `tailscale_args`, `tailscale_funnel_enabled`,
   `tailscale_funnel_port`).
2. **`group_vars/nas/vars.yml`** — this project's actual config file, auto-loaded
   for any host in the `nas` group, no explicit include needed. Every
   `<service>_enabled`, every path (`main_drive`, `gitea_data_dir`,
   `homebridge_config_dir`, ...), every non-secret setting lives here.
3. **`group_vars/nas/vault.yml`** — same auto-loading mechanism, but the file is
   encrypted at rest with `ansible-vault` (AES256). Only decrypted in-memory at
   run time, when `--ask-vault-pass` is passed.

### The `vault_*` indirection pattern

Variables consumed by templates/tasks are named without the `vault_` prefix
(e.g. `copyparty_pass: "{{ vault_copyparty_pass }}"` in `vars.yml`), and each
one-line passthrough points at the encrypted value in `vault.yml`. This is a
convention, not an Ansible requirement — it buys two things:

- Templates never need to know *which* variables are secret; they just use
  `{{ copyparty_pass }}` like any other var.
- `vars.yml` stays safe to commit even though it *references* secrets, because
  the actual values only exist in the encrypted file.

This is also why `vault.yml` can't be edited by anything other than someone
holding the vault password — `ansible-vault`'s security model is that the
encrypted file is opaque without it, including to tooling operating on the
repo. There's no "edit the encrypted file programmatically" path that skips
decryption — that's the same property that makes it safe to commit to git.
