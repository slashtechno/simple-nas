# Simple NAS

Ansible playbooks that set up Raspberry Pis (any Debian-family host) as a NAS and as general Docker servers. The NAS runs Docker services on the drives plugged into it; the inventory lists the hosts and their groups.

NAS services (group `nas`):

- **Immich**: photo library (Google Photos alternative)
- **Copyparty**: file sharing
- **Gitea**: Git server
- **Homebridge**: HomeKit bridge
- **pics**: photo gallery (opt-in)
- **Garage**: S3-compatible object storage (opt-in)
- **Crafty Controller**: Minecraft servers (opt-in)
- **Backup status**: read-only backup dashboard
- **Cloudflare Tunnel**: public hostnames without port forwarding
- **Tailscale**: private remote access, installed on every server

General servers (group `servers_general`) get **Dockge** (web UI for compose stacks) and, opt-in, **Caddy** (names for apps).

Every server also gets Docker, Tailscale, drive mounts and the base packages. Which hosts exist is set in `ansible/inventory/hosts.yml`; the example is `ansible/inventory/hosts.yml.example`.

```
NAS host
├─ microSD         (OS)
├─ fast drive      (Docker data, databases, configs)
├─ primary drive   (photos, files)     the fast and primary roles can share one drive
└─ backup drive    (restic repo, dumps, logs)

Internet → Cloudflare Tunnel (hostnames come from cloudflared_ingress)
  ├─ immich.example.com    → Immich      (:2283)
  ├─ gitea.example.com     → Gitea       (:3000)
  ├─ copyparty.example.com → Copyparty   (:3923)
  └─ s3.example.com        → Garage S3   (:3900)
```

Drive roles are explained in [docs/storage.md](./docs/storage.md).

<details>
<summary>Only two drives? That works: one for data, one for backups.</summary>

A drive can fill several roles, so the NAS needs just two: an SSD with `roles: [fast, primary]` and a second drive with `roles: [backup]`. A third drive (a bigger one for photos and files) can be added later by moving the `primary` role to it. A backup on the same drive as the data is not a backup, so keep `backup` on a separate drive.

```yaml
drives:
  - { uuid: "your-ssd-uuid",    mount: /mnt/t7,     fstype: ext4, options: "defaults,nofail", roles: [fast, primary] }
  - { uuid: "your-backup-uuid", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

More examples, including general servers: [docs/storage.md](./docs/storage.md#examples).

</details>

To set up and deploy, start with [ansible/README.md](./ansible/README.md).

## Backups

Fully automated: daily local, weekly cloud, weekly integrity check, plus a read-only status dashboard. Schedules, what is covered and restore steps are in [docs/backups.md](./docs/backups.md).

## Docs

| Doc | Covers |
|---|---|
| [ansible/README.md](./ansible/README.md) | Which files hold what, setup, `just` commands, changing settings, updating images, adding a service |
| `ansible/roles/` | One role per service |
| `ansible/group_vars/`, `ansible/host_vars/` | Settings (`vars.yml`) for all servers, the NAS group and single hosts; image versions (`versions.yml`); secrets (`vault.yml`, not in git). The `vars.yml` files hold the owner's values: replace them if you copy the repo ([ansible/README.md](./ansible/README.md#using-this-repo-for-your-own-hosts)) |
| `ansible/tests/`, `.github/workflows/` | The render test and the CI that runs `just check` |
| [docs/ansible-terms.md](./docs/ansible-terms.md) | Every Ansible concept and config key this repo uses |
| [docs/services.md](./docs/services.md) | Per-service setup and gotchas, including the ad-hoc app platform and the direct Ethernet link |
| [docs/storage.md](./docs/storage.md) | Drive roles, adding or replacing a drive, Docker's data root, plugged-in USB drives |
| [docs/networking.md](./docs/networking.md) | Recovering a Pi that dropped off the network, and how it picks a network |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | Cheat sheet for the optional caddy-docker-proxy reverse proxy |
| [docs/backups.md](./docs/backups.md) | Schedules, restore, backup-drive failures |
| [docs/plans/drive-migration.md](./docs/plans/drive-migration.md) | Checklist for the planned drive upgrade and the backup steps that follow it |
| [docs/plans/encryption.md](./docs/plans/encryption.md) | Planned encryption at rest (not started) |
| [docs/plans/multi-host.md](./docs/plans/multi-host.md) | Step-by-step cutover: NAS to pi5, pi4 to a general server, hostnames |
| [docs/dumps/](./docs/dumps/) | Decisions log and deferred work from the maintainability refactor |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |
