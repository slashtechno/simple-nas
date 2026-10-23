# Simple NAS

A self-hosted NAS on a Raspberry Pi 4, deployed by Ansible. Two drives, a Pi, and a handful of Docker services.

- **Immich**: photo library (Google Photos alternative)
- **Copyparty**: file sharing
- **Gitea**: Git server
- **Homebridge**: HomeKit bridge
- **pics**: photo gallery
- **Garage**: S3-compatible object storage (opt-in)
- **Crafty Controller**: Minecraft servers (opt-in)
- **Backup status**: read-only backup dashboard
- **Cloudflare Tunnel**: public hostnames without port forwarding
- **Tailscale**: private remote access

```
Raspberry Pi 4
├─ 64GB microSD    (OS)
├─ 500GB SSD       (/mnt/t7: primary data)
└─ 500GB HDD       (/mnt/backup: backups)

Internet → Cloudflare Tunnel
  ├─ immich.example.com    → Immich      (:2283)
  ├─ gitea.example.com     → Gitea       (:3000)
  ├─ copyparty.example.com → Copyparty   (:3923)
  └─ s3.example.com        → Garage S3   (:3900)
```

To set up and deploy, start with [ansible/README.md](./ansible/README.md).

## Backups

Fully automated: daily local, weekly cloud, weekly integrity check, plus a read-only status dashboard. Schedules, what is covered and restore steps are in [docs/backups.md](./docs/backups.md).

## Docs

| Doc | Covers |
|---|---|
| [ansible/README.md](./ansible/README.md) | Setup, `just` commands, changing settings, updating images, adding a service |
| `ansible/roles/` | One role per service |
| `ansible/group_vars/`, `ansible/host_vars/` | Settings (`vars.yml`) for all servers, the NAS group and single hosts; image versions (`versions.yml`); secrets (`vault.yml`) |
| `ansible/tests/`, `.github/workflows/` | The render test and the CI that runs `just check` |
| [docs/ansible-terms.md](./docs/ansible-terms.md) | Every Ansible concept and config key this repo uses |
| [docs/services.md](./docs/services.md) | Per-service setup and gotchas, including the direct Ethernet link |
| [docs/storage.md](./docs/storage.md) | Drive roles, adding or replacing a drive |
| [docs/networking.md](./docs/networking.md) | Recovering a Pi that dropped off the network, and how it picks a network |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | Cheat sheet for the optional caddy-docker-proxy reverse proxy |
| [docs/backups.md](./docs/backups.md) | Schedules, restore, backup-drive failures |
| [docs/plans/drive-migration.md](./docs/plans/drive-migration.md) | Planned drive upgrade and the backup steps that follow it |
| [docs/plans/encryption.md](./docs/plans/encryption.md) | Planned encryption at rest (not started) |
| [docs/plans/multi-host.md](./docs/plans/multi-host.md) | Moving the NAS to pi5, then managing several servers from this repo (not started) |
| [docs/dumps/](./docs/dumps/) | Decisions log and deferred work from the maintainability refactor |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |
