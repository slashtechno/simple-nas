# One Tinyauth for several hosts

> **Status: research note, not built, not kept current.** The deploy runs one Tinyauth per host ([auth-reference.md](../auth-reference.md#several-hosts)). Take rules from AGENTS.md and the code, not from this note.

## Why it is not built

- **Cookie reach.** Tinyauth sets the session cookie on the parent of its own address and has no setting to override it (v5.2.0). `auth.pinas.example.com` covers `*.pinas.example.com` only. One instance for pi4 and pinas needs an address above both (`auth.example.com`), served by one host's Caddy through `caddy_sites`, and every protected name must sit under `example.com`. The cookie is then sent to every subdomain of `example.com`, public ones included.
- **Blast radius.** Every protected service on every host depends on the one instance: if its host is down, Dockge, Dozzle, Scrutiny and the rest lock out. The services with their own login (Immich, Gitea, Copyparty, ntfy), published ports, SSH and backups keep working. Its data directory then holds the sessions for all hosts.
- **Gain.** One password prompt less. Shared users already give the same credentials on both hosts.

## Design if it is wanted

Copy the `ntfy_server` pattern: `tinyauth_server` names the host whose Tinyauth is used (default empty: this host's own).

- The named host publishes its Tinyauth with `tinyauth_port`. The other host's Caddy snippet uses `forward_auth http://<ansible_host of that host>:<tinyauth_port>` (the tailnet encrypts it, as for ntfy alerts) instead of `tinyauth:3000`.
- A check, like `check_ntfy_server.yml`: the named host is in the inventory, has `tinyauth_enabled`, and has `tinyauth_port` set; the consuming host's first private domain shares the parent of the auth host's address.
- Tinyauth needs `TINYAUTH_AUTH_TRUSTEDPROXIES` for the other host's Caddy address if IP rules or the Tailscale login are used; the `X-Forwarded-Host` and `X-Forwarded-Proto` headers come from Caddy's `forward_auth` as is.
- Render test: a second inventory host whose Caddy compose carries that `forward_auth` address, and a failing case for a named host without Tinyauth.
