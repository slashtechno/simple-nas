# Simple NAS

Ansible playbooks that turn a Raspberry Pi, or any Debian-family machine, into a home server running Docker services, with their data on the drives plugged into it.

Runs on arm64 (tested on Raspberry Pi 4 and 5) and on x64, the 64-bit Intel/AMD PCs (a mini PC, an old laptop; not yet deployed end to end on one). Every image pinned in `versions.yml` has both builds (Caddy is built on the host from the official multi-arch `caddy` images): `just platforms` in `ansible/` checks that after a version change.

Every server gets Docker and the base packages; Tailscale and the drive mounts are on by default. Everything else is opt-in per host ([ansible/README.md](./ansible/README.md)). Hosts are listed under `servers` in `ansible/inventory/hosts.yml`; the example is `ansible/inventory/hosts.yml.example`.

The services are listed, with what each one is and needs, in [docs/services.md](./docs/services.md#services). A drive role (`fast`, `primary`, `backup`) is a job a drive in the host's `drives` list is given: [docs/storage.md](./docs/storage.md). A vault entry is a secret in an encrypted `vault.yml`: [ansible/README.md](./ansible/README.md#vault-secrets).

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

A drive can fill several roles, so a host needs just two: an SSD with `roles: [fast, primary]` and a second drive with `roles: [backup]`. A third drive (a bigger one for photos and files) can be added later by moving the `primary` role and its data to it. A backup on the same drive as the data is not a backup, so keep `backup` on a separate drive.

The one-, two- and three-drive layouts are written out in [docs/storage.md](./docs/storage.md#examples).

</details>

To set up and deploy, start with [ansible/README.md](./ansible/README.md).

## Daily use

- **Find everything:** with `homepage_enabled` on one host, its page lists every service with a host port or a Caddy name, on every host, with a dot for whether each answers ([docs/services.md](./docs/services.md#homepage)).
- **Choose what the server opens to:** `caddy_private_domains` gives each web service with a subdomain its own `https://` name with a real certificate; `caddy_sites` adds sites: the root of the server (the Homepage, Copyparty, Dockge) or a redirect ([docs/caddy-reference.md](./docs/caddy-reference.md#web-addresses-and-https)).
- **See what runs:** `just status` in `ansible/` lists the containers on every server.
- **Backups:** the Backups tile and the ntfy alerts; [docs/backups.md](./docs/backups.md).
- **Change something:** edit the host's `vars.yml`, then `just preview` and `just deploy` ([ansible/README.md](./ansible/README.md#commands)).

## Backups

Fully automated once enabled: daily local, weekly cloud (configs and dumps; photos only if you add them), weekly integrity check, plus a read-only status dashboard. Schedules, what is covered and restore steps are in [docs/backups.md](./docs/backups.md).

## Docs

| Doc | Covers |
|---|---|
| [ansible/README.md](./ansible/README.md) | Task index, which files hold what, setup, adding a host, `just` commands, vault, updating images, adding a service |
| [TODO.md](./TODO.md) | The owner's list: work that waits for time or hardware |
| `ansible/roles/` | One role per service, plus the base and shared task roles |
| `ansible/group_vars/`, `ansible/host_vars/` | Shared defaults (`defaults.yml`), the owner's values (`vars.yml`), image versions (`versions.yml`), secrets (`vault.yml`, not in git). The `vars.yml` files hold the owner's values: replace them if you copy the repo ([ansible/README.md](./ansible/README.md#using-this-repo-for-your-own-hosts)) |
| `ansible/tests/`, `.github/workflows/` | The render test and the CI that runs `just check` |
| [docs/ansible-terms.md](./docs/ansible-terms.md) | The Ansible terms and files this repo uses |
| [docs/services.md](./docs/services.md) | Per-service setup and gotchas, including the ad-hoc app platform |
| [docs/storage.md](./docs/storage.md) | Drive roles, adding or replacing a drive, Docker's data root, plugged-in USB drives |
| [docs/encryption.md](./docs/encryption.md) | Folders stored encrypted with gocryptfs: what they protect, first setup, unlocking after a boot, backups while locked |
| [docs/networking.md](./docs/networking.md) | Recovering a Pi that dropped off the network, how it picks a network, the direct Ethernet link |
| [docs/caddy-reference.md](./docs/caddy-reference.md) | The optional Caddy reverse proxy: names, ports, HTTPS and label syntax |
| [docs/auth-reference.md](./docs/auth-reference.md) | The optional Tinyauth login: users, two-factor codes, sign in with GitHub or Google, OpenID Connect, Tailscale, sessions |
| [docs/backups.md](./docs/backups.md) | Schedules, restore, backup-drive failures |
| [AGENTS.md](./AGENTS.md) | Rules for AI agents (not for humans) |

Active plans are in `plans/` and research notes go in `docs/research/` (created when there is one). Finished plans are deleted and stay in git history: `git log --diff-filter=D --name-only -- 'plans/*' 'docs/plans/*'`. They record decisions for work that is not built, are not kept current with the code, and say so at the top. Everything else under `docs/` describes how the repo works.
