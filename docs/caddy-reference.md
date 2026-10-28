# caddy-docker-proxy reference

Label syntax for the optional reverse proxy. Source: the [project README](https://github.com/lucaslorentz/caddy-docker-proxy). Deployed by `roles/caddy` on a host that sets `caddy_enabled: true`.

## What it does

It watches Docker. A container's **labels** become Caddy configuration, and Caddy reloads on its own. Adding an app means adding labels to its compose file and starting it; nothing else to edit.

## What `roles/caddy` deploys

Runs on any host that sets `caddy_enabled: true`; needs the `fast` drive role for its data. With `caddy_private_domains` it also needs `cloudflare_zones`, the Cloudflare token in the vault and a host joined to the tailnet. The image is built on the host from `roles/caddy/files/Dockerfile`: Caddy, caddy-docker-proxy and the Cloudflare DNS plugin, each pinned in `versions.yml` (`caddy_version`, `caddy_docker_proxy_version`, `caddy_cloudflare_dns_version`). The first build compiles Caddy and takes a few minutes on a Pi.

Caddy listens on ports 80 and 443 of the host; `caddy_data_dir` is in `ansible/group_vars/all/defaults.yml`. Losing `caddy_data_dir` means certificates are issued again.

The container joins `services` (`docker_network`, created by `roles/network` on every server), has `CADDY_INGRESS_NETWORKS` set to it, and mounts the Docker socket. The compose file is `roles/caddy/templates/docker-compose.yml.j2`. Behind cloudflared the host ports are not needed: cloudflared reaches `caddy:80` over the Docker network.

## Label syntax

Labels go on the app's container, which must join the same `services` network. For the services of this repo, the Caddy container carries the labels instead (one site per service from `web_services`, one per `caddy_sites` entry (its keys are the directives, written as `caddy_N.<directive>`), and the short-name redirects) ([networking.md](./networking.md#names-for-apps-caddy_private_domains), [short name](./networking.md#short-name)).

```yaml
services:
  whoami:
    image: traefik/whoami
    networks: [services]
    labels:
      caddy: whoami.example.com                    # site address
      caddy.reverse_proxy: "{{upstreams 80}}"      # port the app listens on inside the container
```

| Label | Becomes |
|---|---|
| `caddy: a.example.com` | A site block |
| `caddy: a.example.com, b.example.com` | One block for two hostnames |
| `caddy.reverse_proxy: "{{upstreams 8080}}"` | `reverse_proxy <container-ip>:8080` |
| `caddy.tls: internal` | Caddy's own CA instead of Let's Encrypt |
| `caddy.header: X-Frame-Options SAMEORIGIN` | A `header` directive |
| `caddy_0`, `caddy_1` (with matching `caddy_0.reverse_proxy`, ...) | Separate site blocks in one container |
| `caddy_ingress_network: name` | Use this network for `{{upstreams}}` on this container |

Dots mean nesting: `caddy.basic_auth.alice: <hash>` produces a `basic_auth` block. An empty value gives a directive with no arguments. This repo uses that for a backend with a self-signed certificate (`scheme: https` in `web_services.yml`). The README has no basic-auth example; check the generated Caddyfile before relying on it.

## Gotchas for this repo

- **Apps that trust proxy headers.** Caddy sends `X-Forwarded-For`, `-Proto` and `-Host`. An app that rejects requests unless it reads them (Copyparty's `rproxy` and `xff-src` in `roles/copyparty/templates/copyparty.conf.j2`) must be told to trust the proxy's network.
- **Jinja collision.** `{{upstreams}}` is also Jinja syntax. In any file rendered by Ansible, wrap it: `{% raw %}{{upstreams 80}}{% endraw %}`. Dockge stacks are plain files and need no escaping.
- **Shared network.** A stack must declare the external `services` network (`docker_network`) and join it; a container not on it is invisible to `{{upstreams}}`.
- **TLS.**
  - Let's Encrypt HTTP-01 needs the internet to reach ports 80/443 on the machine. On a LAN or tailnet that is not the case, so use `tls internal` and trust Caddy's root CA on each device.
  - Behind cloudflared, Cloudflare terminates TLS. Use `http://app.example.com` as the site address so Caddy does not attempt ACME.
  - Names under a `caddy_private_domains` entry get their certificate through the Cloudflare DNS challenge, which needs no open ports ([networking.md](./networking.md#web-addresses-and-https)). For a name outside those domains Caddy tries the same challenge; use `tls internal` unless the Cloudflare token covers its zone.
- **`caddy_sites` values.** Keys are flat and a dot nests (`header.X-Frame-Options`); `{uri}` takes single braces; an argument with spaces needs backticks. If a change has no effect, read the generated file: `docker exec caddy cat /config/caddy/Caddyfile.autosave`.
- **Docker socket.** The proxy has full control of Docker through it. Anything that can set labels on a container can publish a route.
- **Modes.** The role runs the standalone mode (controller and server in one container). The controller/server split is for Swarm clusters.

## With cloudflared

No router port forwarding is needed. A public hostname is an explicit entry in the host's `cloudflared_ingress`; there is no wildcard to Caddy, because every labeled container would become public. Any host that sets `cloudflared_enabled: true` runs its own tunnel with its own `cloudflared_ingress`; see [services.md](./services.md#cloudflare-add-a-public-hostname).

For a published app, point the entry at Caddy and use an `http://` site address, since Cloudflare terminates TLS:

```yaml
labels:
  caddy: http://notes.example.com
  caddy.reverse_proxy: "{{upstreams 3000}}"
```

An `http://` site address gets a plain `200` with no redirect, so no global `auto_https` label is needed.
