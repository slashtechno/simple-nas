# NAS Ansible Playbooks

Each service is a separate role with its own Docker Compose project at `/opt/nas/<service>/` on the Pi, all connected via a shared Docker network (`nas-services`).

Ansible runs **on your Mac** and SSHes into the Pi. The Pi only needs SSH access and Python.

---

## Ansible concepts (new to Ansible — read this first)

**What Ansible does:** You describe the desired state in YAML files on your Mac. Running a playbook makes the Pi match that state. It's not a script that runs top-to-bottom once — it checks each step and skips it if it's already correct.

**Idempotency:** Running the same playbook twice is safe and expected. The second run no-ops on everything that's already correct. This means you can always re-run to bring the Pi back to the desired state after something drifts.

**Roles:** A role is a self-contained unit for one service — its own tasks, templates, files, and handlers. `roles/immich/` knows everything about deploying Immich and nothing about anything else. Adding a new service = adding a new role.

**Handlers:** A handler is a task that only runs when triggered by another task via `notify:`. The key property: it runs **once at the end**, no matter how many tasks triggered it. Used for restarts — e.g. "if the Copyparty config changed, restart Copyparty." If nothing changed, the handler never fires and the service is never disrupted.

**Vault:** Sensitive values (passwords, API tokens) live in `group_vars/nas/vault.yml`, encrypted with `ansible-vault`. The file looks like `vars.yml` but is stored as ciphertext. You decrypt it at run time with `--ask-vault-pass`.

**Is this like NixOS — should I avoid changing things directly on the Pi?**

Not as strict. The rule is: **Ansible owns what it deploys; you own everything else.**

- Files Ansible manages (`/opt/nas/*/docker-compose.yml`, cron jobs, config files it renders) — change these through Ansible, or the next playbook run will overwrite your edit.
- Everything else (SSH keys, packages you install manually, files outside `/opt/nas/`) — direct changes are fine and Ansible won't touch them.

If you SSH in and manually restart a container or tweak something temporarily, that's fine. Just know that re-running the relevant playbook tag will bring it back to the defined state.

---

## First-time setup

```bash
brew install ansible
cd ansible/

ansible-galaxy collection install -r requirements.yml
ansible-galaxy role install -r requirements.yml

cp inventory/hosts.yml.example inventory/hosts.yml    # set your Pi's IP and username
cp group_vars/nas/vars.yml.example group_vars/nas/vars.yml
cp group_vars/nas/vault.yml.example group_vars/nas/vault.yml
# fill in vault.yml with real secrets, then encrypt it:
ansible-vault encrypt group_vars/nas/vault.yml
```

---

## Deploy

```bash
# Everything
ansible-playbook site.yml --ask-vault-pass

# One service only
ansible-playbook site.yml --tags immich --ask-vault-pass
```

---

## Disable a service

Set `<name>_enabled: false` in `group_vars/nas/vars.yml` and re-run. The service won't be deployed or started. All enabled flags are at the top of `vars.yml`.

```yaml
immich_enabled: false   # skip Immich entirely
garage_enabled: false   # Garage is off by default — needs manual init after first deploy
```

If you previously deployed the service and want to remove it from the Pi, run teardown first:
```bash
ansible-playbook teardown.yml --tags immich --ask-vault-pass
```
Then set `immich_enabled: false` so future runs don't redeploy it.

---

## Update configuration

Edit `group_vars/nas/vars.yml` (or `vault.yml` for secrets), then re-run with the relevant tag. Only changed services restart — handlers ensure a restart only fires if a config file actually changed.

```bash
ansible-playbook site.yml --tags <service> --ask-vault-pass
```

### Copyparty: add users or change volume layout

The built-in config template is `roles/copyparty/files/copyparty.conf.template.default`. At container startup, `entrypoint.sh` renders it into `/cfg/copyparty.conf` (substituting `$COPYPARTY_USER` / `$COPYPARTY_PASS`). That rendered file is ephemeral — never edit it directly.

To customize beyond username/password:
1. Copy the `.default` file to `/mnt/t7/docker/copyparty_config/copyparty.conf.template` on the Pi
2. Edit it — the entrypoint uses yours instead of the built-in one; `${COPYPARTY_USER}` substitution still works
3. Re-run `--tags copyparty`

### Cloudflare: add a public hostname for a new service

In `vars.yml`:
```yaml
cloudflared_ingress:
  - hostname: newservice.example.com
    service: "http://newservice:8080"
```
Then: `ansible-playbook site.yml --tags cloudflared --ask-vault-pass`

### Tailscale Funnel

In `vars.yml`:
```yaml
tailscale_funnel_enabled: true   # exposes Copyparty at your ts.net hostname
```
Then: `ansible-playbook site.yml --tags tailscale --ask-vault-pass`

---

## Remove services

```bash
# Stop and remove one service (data kept)
ansible-playbook teardown.yml --tags garage --ask-vault-pass

# Remove everything (data kept)
ansible-playbook teardown.yml --ask-vault-pass

# Remove everything AND wipe data (DESTRUCTIVE — no undo without a backup)
ansible-playbook teardown.yml -e remove_data=true --ask-vault-pass
```

---

## Add a new service

1. `mkdir -p roles/myservice/{tasks,templates,handlers,files}`
2. `roles/myservice/tasks/main.yml` — create dir, render compose, start
3. `roles/myservice/templates/docker-compose.yml.j2` — join `nas-services` external network
4. `roles/myservice/handlers/main.yml` — restart on config change
5. Add vars to `group_vars/nas/vars.yml`
6. Add `- role: myservice` + tag + `when: myservice_enabled | default(true)` to `site.yml`
7. Add a `cloudflared_ingress` rule if it needs a public hostname
8. `ansible-playbook site.yml --tags myservice --ask-vault-pass`

---

## Garage S3 post-setup

Set `garage_enabled: true` in `vars.yml`, fill in the vault entries (`vault_garage_rpc_secret`, `vault_garage_admin_token`, `vault_garage_webui_user`, `vault_garage_webui_pass`), then deploy:

```bash
ansible-playbook site.yml --tags garage,cloudflared --ask-vault-pass
```

The compose file passes `--single-node` to Garage (v2.3+), so the cluster auto-initializes — no layout commands needed. Open `https://garage.example.com` and log in with the web UI credentials. Use the web UI to create buckets and access keys.

When connecting an app to Garage, use:
- **Endpoint**: `https://s3.example.com`
- **Region**: `garage`
- **Access key / secret**: from the web UI

---

## Useful commands

```bash
# View logs for a service
ssh yourname@your-pi "docker logs -f copyparty"

# Dry-run (shows what would change, touches nothing)
ansible-playbook site.yml --check --ask-vault-pass

# Edit encrypted secrets
ansible-vault edit group_vars/nas/vault.yml
```
