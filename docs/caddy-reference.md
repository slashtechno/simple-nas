# caddy-docker-proxy reference

A cheat sheet for the optional reverse proxy in [plans/multi-host.md](./plans/multi-host.md). Source: the [project README](https://github.com/lucaslorentz/caddy-docker-proxy). Deployed by `roles/caddy` (opt-in: `caddy_enabled`).

## What it does

It watches Docker. A container's **labels** become Caddy configuration, and Caddy reloads on its own. Adding an app means adding labels to its compose file and starting it; nothing else to edit.

## Run it

```yaml
services:
  caddy:
    image: lucaslorentz/caddy-docker-proxy:2.13.1-alpine   # pinned in versions.yml
    ports:
      - 80:80
      - 443:443/tcp
      - 443:443/udp
    environment:
      - CADDY_INGRESS_NETWORKS=nas-services
    networks:
      - nas-services
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - caddy_data:/data        # certificates; losing it means re-issuing them
    restart: unless-stopped

networks:
  nas-services:
    external: true              # the network role creates it on every server

volumes:
  caddy_data: {}
```

The README shows `ci-alpine`, a CI build with no stability guarantee. Use a version tag. With cloudflared in front you can skip ports 80 and 443 on the host and let cloudflared reach `caddy:80` over the Docker network.

## Label syntax

Labels go on the app's container, which must join the same `nas-services` network.

```yaml
services:
  whoami:
    image: traefik/whoami
    networks: [nas-services]
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

Dots mean nesting: `caddy.basic_auth.alice: <hash>` produces a `basic_auth` block. The README has no basic-auth example, so check that one against the output of the Caddyfile it generates.

## Gotchas for this repo

- **Jinja collision.** `{{upstreams}}` is also Jinja syntax. In any file rendered by Ansible, wrap it: `{% raw %}{{upstreams 80}}{% endraw %}`. Dockge stacks are plain files and need no escaping.
- **Shared network.** Every stack declares the external `nas-services` network (`nas_network`). A container not on it is invisible to `{{upstreams}}`.
- **TLS.**
  - Let's Encrypt HTTP-01 needs the internet to reach ports 80/443 on the machine. On a LAN or tailnet that is not the case, so use `tls internal` and trust Caddy's root CA on each device.
  - Behind cloudflared, Cloudflare terminates TLS. Use `http://app.example.com` as the site address so Caddy does not attempt ACME.
  - Avoid custom Caddy builds with DNS-challenge plugins. They add a build to maintain.
- **Docker socket.** The proxy has full control of Docker through it. It is on a trusted home host, but anything that can set labels can publish a route.
- **Modes.** The default (standalone: controller and server in one container) is the one to use. The controller/server split is for Swarm clusters.

## With cloudflared

No router port forwarding is needed. Public hostnames are explicit entries in `cloudflared_ingress` (see "Public hostnames for ad-hoc apps" in the [multi-host plan](./plans/multi-host.md)); a wildcard to Caddy was considered and not chosen, because every labeled container would become public.

For a published app, point the entry at Caddy and use an `http://` site address, since Cloudflare terminates TLS:

```yaml
labels:
  caddy: http://notes.example.com
  caddy.reverse_proxy: "{{upstreams 3000}}"
```

Tested on pi5 (2026-10-23): a container with `caddy: http://whoami.test` and `caddy.reverse_proxy: "{{upstreams 80}}"` answered `200` over plain HTTP with no redirect, so no global `auto_https` label is needed as long as the site address starts with `http://`.
