# Backup status dashboard + DRY pass on hardcoded infra values

## Context

We designed a read-only "Snapshot Deck" web dashboard (validated as a Pico.css-based
artifact mockup) for viewing restic backup status/snapshots and getting copy-paste SSH
commands for restore/delete — no server-side execution, no auth needed because the
Docker container only ever gets **read-only** access to the restic repo and password
file. While scoping that dashboard's Ansible role, the user flagged that the existing
`backup` role's shell scripts hardcode paths (`/mnt/backup`, `/mnt/t7`) that already have
named vars (`backup_drive`, `main_drive`) elsewhere in the repo — and asked to fix that
properly (turn the scripts into real Jinja templates) rather than have the new role add
a third source of truth for the same paths. A repo-wide scan (user-approved full scope)
turned up the same class of duplication in five other roles' compose templates and in
`teardown.yml`, plus a stale AI-instructions doc — all included in this pass.

## Approach

**Convention already in this repo**: no role has its own `defaults/main.yml`; every
cross-role path/port lives once in `ansible/group_vars/nas/vars.yml(.example)` and is
referenced by `{{ var }}` everywhere it's needed. This plan extends that same file — it
does not introduce a new pattern.

### 1. New vars in `ansible/group_vars/nas/vars.yml` and `.example` (add alongside existing `--- Storage ---` section)

```yaml
restic_repo_path: "{{ backup_drive }}/restic-repo"
restic_cloud_repository: "rclone:gdrive-nas:/pi-nas-backups"
restic_password_file: "/home/{{ ansible_user }}/.restic-password"
backup_logs_dir: "{{ backup_drive }}/logs"
service_dumps_dir: "{{ backup_drive }}/service-dumps"

gitea_port: 3000
copyparty_port: 3923
direct_link_iface: eth0

backup_status_enabled: true
backup_status_port: 8091
```

(`vars.yml` is the user's real, non-gitignored file — same additions go in both it and
`.example`, matching how every other var pair already exists in both files.)

### 2. `backup` role — templatize the scripts, dedupe against the vars above

- `ansible/roles/backup/tasks/main.yml`: swap the four inline concatenations
  (`{{ backup_drive }}/restic-repo`, `/home/{{ ansible_user }}/.restic-password`,
  `{{ backup_drive }}/logs/...`) for `{{ restic_repo_path }}`, `{{ restic_password_file }}`,
  `{{ backup_logs_dir }}`. Change the "Deploy backup scripts" task: split into a
  `template` loop for the four scripts below and a `copy` loop for `restore-services.sh`
  (unaffected — it doesn't hardcode any drive paths).

- **`backup-restic-local.sh` → `backup-restic-local.sh.j2`** (move `files/` → `templates/`):
  - `/mnt/backup` → `{{ backup_drive }}`, `/mnt/t7` → `{{ main_drive }}`, log path →
    `{{ backup_logs_dir }}`, service-dumps arg → `{{ service_dumps_dir }}`.
  - Exclude list currently re-derives paths that already have vars — replace
    `/mnt/t7/docker/gitea/ssh` → `{{ gitea_data_dir }}/ssh`,
    `/mnt/t7/docker/immich_postgres` → `{{ immich_db_data_location }}`,
    `/mnt/t7/docker/copyparty_config/copyparty` → `{{ copyparty_config_dir }}/copyparty`.
    This is a real bug fix, not just cosmetic: today if `gitea_data_dir` ever changed,
    this exclude list would silently stop matching it.
  - Simplify the `RESTIC_PASSWORD_FILE` root/sudo-detection fallback (~20 lines) down to
    `export RESTIC_PASSWORD_FILE="${RESTIC_PASSWORD_FILE:-{{ restic_password_file }}}"` —
    that dance existed only because the script couldn't know its real deployed path;
    now Ansible bakes it in directly, while the env-var override stays for manual runs.

- **`backup-restic-cloud.sh` → `backup-restic-cloud.sh.j2`**:
  - `/mnt/backup` → `{{ backup_drive }}`, cloud repo string → `{{ restic_cloud_repository }}`,
    log/service-dumps paths → `{{ backup_logs_dir }}` / `{{ service_dumps_dir }}`.
  - Delete the `.env`-file-parsing block for `DB_DATA_LOCATION`/`GITEA__database__PATH`
    (confirmed dead: those keys don't match this repo's real var names, so the skip
    logic never actually matched anything). Replace with a plain skip-list built directly
    from `{{ immich_db_data_location }}` and `{{ gitea_data_dir }}`.

- **`backup-services.sh` → `backup-services.sh.j2`**: `DUMP_DIR` default → `{{ service_dumps_dir }}`,
  mountpoint check → `{{ backup_drive }}`.

- **`backup-paths.txt.j2`** (already a template): replace the two lines that reconstruct
  `{{ main_drive }}/docker/gitea` and `{{ main_drive }}/docker/copyparty_config` with
  `{{ gitea_data_dir }}` / `{{ copyparty_config_dir }}` — same values today, one source
  of truth going forward.

- **`copyparty-funnel.sh` → `copyparty-funnel.sh.j2`**: port default `3923` → `{{ copyparty_port }}`.
  Read the current file in full during implementation (only a one-line snippet was seen
  so far) to confirm whether it should reference `copyparty_port` or `tailscale_funnel_port`.

### 3. New `ansible/roles/backup-status/` role (the dashboard itself)

```
files/
  app.py            # Python 3.14 stdlib http.server — no framework. Serves index.html +
                     #   pico.min.css statically; GET /api/status and GET /api/snapshots
                     #   shell out to `restic --no-lock snapshots --json` / `stats` and
                     #   parse the mount/log state, short in-process cache (~30-60s).
  index.html         # the validated Snapshot Deck markup, wired to fetch() the two
                     #   endpoints instead of the mockup's inline demo data.
  pico.min.css       # already vendored during the mockup phase.
  Dockerfile         # multi-stage: `FROM restic/restic AS restic` → copy /usr/bin/restic;
                     #   final stage `python:3.14-slim`, non-root user, COPY app.py + assets.
templates/
  docker-compose.yml.j2   # joins {{ nas_network }}; volumes:
                           #   {{ backup_drive }}:/data/backup:ro
                           #   {{ restic_password_file }}:/data/restic-password:ro
                           # env: NAS_SSH_USER={{ ansible_user }}, RESTIC_REPO_PATH=/data/backup/restic-repo,
                           #   BACKUP_LOGS_DIR=/data/backup/logs, RESTIC_PASSWORD_FILE=/data/restic-password
                           # ports: "{{ backup_status_port }}:8080"
tasks/main.yml       # mirrors ansible/roles/gitea/tasks/main.yml: create dir, template
                     #   compose, docker_compose_v2 (state: present), notify handler.
handlers/main.yml    # read roles/gitea/handlers/main.yml first to match its exact
                     #   restart-on-template-change pattern before writing this.
```

Single volume mount (`backup_drive`, not three separate mounts) because the repo, logs,
and service-dumps dir all already live under it — one `:ro` bind covers the mount-check,
snapshot listing, and log parsing. The app never touches `main_drive`, never gets a
writable mount, and the compose file has no `cloudflared_ingress` entry (Tailscale-only,
matching `homebridge`'s existing precedent).

Add to `ansible/site.yml`: `- role: backup-status` / `tags: [backup-status]` /
`when: backup_status_enabled | default(true)`, placed after the `backup` role.

### 4. Other roles — `nas_network` and port dedup

Replace the hardcoded `nas-services` network name (both the top-level `networks:` key
and each service's `networks:` list entry) with `{{ nas_network }}` in:
`immich`, `gitea`, `cloudflared`, `garage`, `copyparty` compose templates. Same pattern
repeated 5 times — fix identically in each, no per-file variation needed.

In `gitea/templates/docker-compose.yml.j2`: `"2222:22"` → `"{{ gitea_ssh_port }}:22"`
(the SSH port var already exists and is already used two lines above for the env var —
only the port mapping was missed); `"3000:3000"` → `"{{ gitea_port }}:3000"` (new var).
Leave `GITEA_INSTANCE_URL: "http://gitea:3000"` and `GITEA_RUNNER_NAME` alone — the
former addresses the container's actual internal listen port (unrelated to the host
mapping), the latter has no clear var to introduce.

In `copyparty/templates/docker-compose.yml.j2`: `"3923:3923"` → `"{{ copyparty_port }}:3923"`.

### 5. `ansible/teardown.yml`

- Replace repeated `"{{ nas_base_dir }}/cloudflared"` with `{{ cloudflared_dir }}`.
- Replace hardcoded `ifname: eth0` with `{{ direct_link_iface }}` (also update
  `ansible/roles/network/tasks/main.yml`'s matching `eth0` references to the same var —
  both files currently hardcode the same literal independently).
- Leave `"Wired connection 1"` as a literal — it's NetworkManager's own default profile
  name, not something this project defines or controls, so there's no var to extract.

### 6. Docs

- `.github/copilot-instructions.md`: delete outright — it describes a pre-Ansible
  `.env`/`scripts/` layout that no longer exists anywhere in the repo, so it would only
  actively mislead an agent reading it, not usefully guide one.
- `BACKUPS.md`: the four `ssh pi@your-pi-ip` examples imply a literal default username
  of `pi`, which contradicts the repo's own stated fact that Pi OS forces a custom
  username — change to an illustrative placeholder (e.g. `ssh your-user@your-pi-ip`).

## Verification

- `ansible-lint` / `ansible-playbook --syntax-check site.yml` after the var and template
  changes — confirms no Jinja typos before touching the Pi.
- `ansible-playbook site.yml --tags backup --check` (dry run) to confirm the retemplated
  backup scripts render with the expected paths substituted.
- Deploy `--tags backup,backup-status` for real, then on the Pi: manually run
  `bash /opt/nas/scripts/backup-restic-local.sh` and confirm it completes and excludes
  the right paths (`docker exec`/`ls` to spot-check), and load
  `http://<pi-tailscale-host>:{{ backup_status_port }}` to confirm the dashboard shows
  real snapshot data and the SSH-command modal substitutes the real host/user.
- Redeploy the 5 other roles (`--tags immich,gitea,cloudflared,garage,copyparty --check`
  first) to confirm the `nas_network` rename doesn't change any running container's
  actual network membership (value is identical today — `nas-services` — so this should
  be a no-op diff, just a template-source change).
