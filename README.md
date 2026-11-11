# Simple NAS

Ansible playbooks that turn a Raspberry Pi, or any Debian-family machine, into a home server. Its Docker services keep their data on the plugged-in drives.

Runs on arm64 (tested on Raspberry Pi 4 and 5) and on x64, the 64-bit Intel/AMD PCs (a mini PC, an old laptop). Every pinned image has both builds. `just platforms` in `ansible/` checks that after a version change.

**New here?** [docs/quick-start.md](./docs/quick-start.md) takes a fresh clone to a complete server.

You switch on every part per host, except `common` and `network`, which always run: [ansible/README.md](./ansible/README.md). The services and what each needs: [docs/services.md](./docs/services.md#services). Drive roles: [docs/storage.md](./docs/storage.md).

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

A drive can fill several roles, so two are enough (`[fast, primary]` and `[backup]`). The layouts are in [docs/storage.md](./docs/storage.md#examples).

</details>

To set up and deploy: [quick-start](./docs/quick-start.md) for a complete server, or [ansible/README.md](./ansible/README.md) for commands and files.

## Docs

| Start here | |
|---|---|
| [docs/quick-start.md](./docs/quick-start.md) | A fresh clone to a complete server |
| [ansible/README.md](./ansible/README.md) | Task index, files, `just` commands, vault, adding a host or service |
| [docs/services.md](./docs/services.md) | Each service: what it needs and its gotchas |

| When something happens | |
|---|---|
| [docs/backups.md](./docs/backups.md) | Schedules, restore, a dead or disconnected backup drive |
| [docs/storage.md](./docs/storage.md) | Add or replace a drive, a drive that will not mount, drive wear |
| [docs/networking.md](./docs/networking.md) | A Pi that dropped off the network |
| [docs/memory.md](./docs/memory.md) | A host short of RAM |
| [docs/encryption.md](./docs/encryption.md) | Encrypted folders: set up, unlock after a boot |
| [unlock-page/README.md](./unlock-page/README.md) | Unlock from a browser (an optional standalone app, not an Ansible role) |

| Reference | |
|---|---|
| [docs/glossary.md](./docs/glossary.md) | The words the docs use, plus the Ansible parts you meet when editing |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | Caddy: names, ports, HTTPS, label syntax |
| [docs/auth-reference.md](./docs/auth-reference.md) | Tinyauth: users, 2FA, sign in with GitHub or Google, OIDC |
| [TODO.md](./TODO.md) | The owner's list of work waiting on time or hardware |
| `.github/workflows/` | CI: runs `just check` on every push |
| `ansible/roles/`, `ansible/group_vars/`, `ansible/host_vars/`, `ansible/tests/` | One role per service. Shared defaults, the owner's values and secrets (`vars.yml` files are the owner's: replace them if you copy the repo, [see how](./ansible/README.md#using-this-repo-for-your-own-hosts)). The render test |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |

Plans for unfinished work are in `plans/`. Each plan is deleted when its work is done (git history keeps it). Everything else under `docs/` describes how the repo works.
