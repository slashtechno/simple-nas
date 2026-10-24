# Simple NAS

Ansible playbooks that set up Raspberry Pis (any Debian-family host) as home servers that run Docker services on the drives plugged into them.

Every server gets Docker, Tailscale, the drive mounts and the base packages. Everything else is opt-in: a service is deployed on a host only when that host sets `<name>_enabled: true` in `ansible/host_vars/<host>/vars.yml`. Every flag defaults to false. Hosts are listed under `servers` in `ansible/inventory/hosts.yml`; the example is `ansible/inventory/hosts.yml.example`.

The services are listed, with what each one is and needs, in [docs/services.md](./docs/services.md#services). A drive role (`fast`, `primary`, `backup`) is a job a drive in the host's `drives` list is given: [docs/storage.md](./docs/storage.md). A vault entry is a secret in an encrypted `vault.yml`: [ansible/README.md](./ansible/README.md#vault-secrets).

```
A host
├─ root drive      (OS)
├─ fast drive      (Docker data, databases, configs)
├─ primary drive   (photos, files)     the fast and primary roles can share one drive
└─ backup drive    (restic repo, dumps, logs)

Internet → Cloudflare Tunnel (hostnames come from cloudflared_ingress)
  ├─ <host-a>.example.com  → a service on the Docker network
  └─ <host-b>.example.com  → another service on the Docker network
```

<details>
<summary>Only two drives? That works: one for data, one for backups.</summary>

A drive can fill several roles, so a host needs just two: an SSD with `roles: [fast, primary]` and a second drive with `roles: [backup]`. A third drive (a bigger one for photos and files) can be added later by moving the `primary` role to it. A backup on the same drive as the data is not a backup, so keep `backup` on a separate drive.

```yaml
drives:
  - { uuid: "your-ssd-uuid",    mount: /mnt/ssd,    fstype: ext4, options: "defaults,nofail", roles: [fast, primary] }
  - { uuid: "your-backup-uuid", mount: /mnt/backup, fstype: ext4, options: "defaults,nofail", roles: [backup] }
```

More examples: [docs/storage.md](./docs/storage.md#examples).

</details>

To set up and deploy, start with [ansible/README.md](./ansible/README.md).

## Backups

Fully automated once enabled: daily local, weekly cloud, weekly integrity check, plus a read-only status dashboard. Schedules, what is covered and restore steps are in [docs/backups.md](./docs/backups.md).

## Docs

| Doc | Covers |
|---|---|
| [ansible/README.md](./ansible/README.md) | Task index, which files hold what, setup, adding a host, `just` commands, vault, updating images, adding a service |
| [TODO.md](./TODO.md) | The owner's list: work that waits for time or hardware |
| `ansible/roles/` | One role per service |
| `ansible/group_vars/`, `ansible/host_vars/` | Shared defaults (`defaults.yml`), the owner's values (`vars.yml`), image versions (`versions.yml`), secrets (`vault.yml`, not in git). The `vars.yml` files hold the owner's values: replace them if you copy the repo ([ansible/README.md](./ansible/README.md#using-this-repo-for-your-own-hosts)) |
| `ansible/tests/`, `.github/workflows/` | The render test and the CI that runs `just check` |
| [docs/ansible-terms.md](./docs/ansible-terms.md) | Every Ansible concept and config key this repo uses |
| [docs/services.md](./docs/services.md) | Per-service setup and gotchas, including the ad-hoc app platform |
| [docs/storage.md](./docs/storage.md) | Drive roles, adding or replacing a drive, Docker's data root, plugged-in USB drives |
| [docs/networking.md](./docs/networking.md) | Recovering a Pi that dropped off the network, how it picks a network, the direct Ethernet link |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | Cheat sheet for the optional caddy-docker-proxy reverse proxy |
| [docs/backups.md](./docs/backups.md) | Schedules, restore, backup-drive failures |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |

The owner's to-do list is `TODO.md`. The active plan is in `plans/` and research notes are in `docs/research/`. Finished plans are deleted and stay in git history: `git log --diff-filter=D --name-only -- 'plans/*' 'docs/plans/*'`. They record decisions for work that is not built, are not kept current with the code, and say so at the top. Everything else under `docs/` describes how the repo works now.
