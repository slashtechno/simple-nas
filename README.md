# Simple NAS

Ansible playbooks that turn a Raspberry Pi, or any Debian-family machine, into a home server running Docker services, with their data on the drives plugged into it.

Runs on arm64 (tested on Raspberry Pi 4 and 5) and on x64, the 64-bit Intel/AMD PCs (a mini PC, an old laptop). Every pinned image has both builds; `just platforms` in `ansible/` checks that after a version change.

**New here?** [docs/quick-start.md](./docs/quick-start.md) takes a fresh clone to a complete server.

Every part is switched on per host except `common` and `network`, which always run: [ansible/README.md](./ansible/README.md). The services and what each needs: [docs/services.md](./docs/services.md#services). Drive roles: [docs/storage.md](./docs/storage.md).

```
A host
├─ root drive      (OS)
├─ fast drive      (databases, configs)
├─ primary drive   (photos, files)     the fast and primary roles can share one drive
└─ backup drive    (restic repo, dumps, logs)

Internet → Cloudflare Tunnel (hostnames come from cloudflared_ingress)
  ├─ <host-a>.example.com  → a service on the Docker network
  └─ <host-b>.example.com  → another service on the Docker network
```

<details>
<summary>Only two drives? That works: one for data, one for backups.</summary>

A drive can fill several roles, so two are enough (`[fast, primary]` and `[backup]`); the layouts are in [docs/storage.md](./docs/storage.md#examples).

</details>

To set up and deploy: [quick-start](./docs/quick-start.md) for a complete server, [ansible/README.md](./ansible/README.md) for the commands and files.

## Docs

| Doc | Covers |
|---|---|
| [docs/quick-start.md](./docs/quick-start.md) | A fresh clone to a complete server, in order |
| [ansible/README.md](./ansible/README.md) | Task index, which files hold what, adding a host, `just` commands, vault, updating images, adding a service |
| [TODO.md](./TODO.md) | The owner's list: work that waits for time or hardware |
| `ansible/roles/` | One role per service, plus the base and shared task roles |
| `ansible/group_vars/`, `ansible/host_vars/` | Shared defaults (`defaults.yml` and the topic files beside it), the owner's values (`vars.yml`), image versions (`versions.yml`), secrets (`vault.yml`, not in git). The `vars.yml` files hold the owner's values: replace them if you copy the repo ([ansible/README.md](./ansible/README.md#using-this-repo-for-your-own-hosts)) |
| `ansible/tests/`, `.github/workflows/` | The render test and the CI that runs `just check` |
| [docs/glossary.md](./docs/glossary.md) | Plain definitions of the backup, Docker, drive, login and web terms the docs use |
| [docs/ansible-terms.md](./docs/ansible-terms.md) | The Ansible terms and files this repo uses |
| [docs/services.md](./docs/services.md) | Per-service setup and gotchas, including the ad-hoc app platform |
| [docs/storage.md](./docs/storage.md) | Drive roles, adding or replacing a drive, Docker's data root, plugged-in USB drives |
| [docs/encryption.md](./docs/encryption.md) | Folders stored encrypted with gocryptfs: what they protect, first setup, unlocking after a boot, backups while locked |
| [docs/networking.md](./docs/networking.md) | Recovering a Pi that dropped off the network, how it picks a network, the direct Ethernet link |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | The optional Caddy reverse proxy: names, ports, HTTPS and label syntax |
| [docs/auth-reference.md](./docs/auth-reference.md) | The optional Tinyauth login: users, two-factor codes, sign in with GitHub or Google, OpenID Connect, Tailscale, sessions |
| [docs/backups.md](./docs/backups.md) | Schedules, restore, backup-drive failures |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |

Active plans are in `plans/` and research notes go in `docs/research/` ([settings-structure.md](./docs/research/settings-structure.md) is the first). Finished plans are deleted and stay in git history: `git log --diff-filter=D --name-only -- 'plans/*' 'docs/plans/*'`. They record decisions for work that is not built, are not kept current with the code, and say so at the top. Everything else under `docs/` describes how the repo works.
