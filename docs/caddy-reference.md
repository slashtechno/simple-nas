# caddy-docker-proxy reference

A cheat sheet for the optional reverse proxy in [plans/multi-host.md](./plans/multi-host.md). Source: the [project README](https://github.com/lucaslorentz/caddy-docker-proxy). Not deployed yet.

## What it does

It watches Docker. A container's **labels** become Caddy configuration, and Caddy reloads on its own. Adding an app means adding labels to its compose file and starting it; nothing else to edit.

## Run it

```yaml
services:
  caddy:
    image: lucaslorentz/caddy-docker-proxy:2.13.1-alpine   # pin it; put the version in versions.yml
    ports:
      - 80:80
      - 443:443/tcp
      - 443:443/udp
    environment:
      - CADDY_INGRESS_NETWORKS=caddy
    networks:
      - caddy
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
      - caddy_data:/data        # certificates; losing it means re-issuing them
    restart: unless-stopped

networks:
  caddy:
    external: true              # create once: docker network create caddy

volumes:
  caddy_data: {}
```

The README shows `ci-alpine`, a CI build with no stability guarantee. Use a version tag. With cloudflared in front you can skip ports 80 and 443 on the host and let cloudflared reach `caddy:80` over the Docker network.

## Label syntax

Labels go on the app's container, which must join the same `caddy` network.

```yaml
services:
  whoami:
    image: traefik/whoami
    networks: [caddy]
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
- **Shared network.** Every stack declares the external `caddy` network. A container not on it is invisible to `{{upstreams}}`.
- **TLS.**
  - Let's Encrypt HTTP-01 needs the internet to reach ports 80/443 on the machine. On a LAN or tailnet that is not the case, so use `tls internal` and trust Caddy's root CA on each device.
  - Behind cloudflared, Cloudflare terminates TLS. Use `http://app.example.com` as the site address so Caddy does not attempt ACME.
  - Avoid custom Caddy builds with DNS-challenge plugins. They add a build to maintain.
- **Docker socket.** The proxy has full control of Docker through it. It is on a trusted home host, but anything that can set labels can publish a route.
- **Modes.** The default (standalone: controller and server in one container) is the one to use. The controller/server split is for Swarm clusters.

## With cloudflared

No router port forwarding is needed. See "Public hostnames for ad-hoc apps" in the [multi-host plan](./plans/multi-host.md). The short version for a wildcard setup:

```yaml
# tunnel ingress (one rule, set once by Ansible)
- hostname: "*.apps-domain.example"
  service: http://caddy:80
```

```yaml
# on the Caddy container: turn off automatic HTTPS once.
# cloudflared sends plain HTTP, so Caddy's redirect to HTTPS would loop.
labels:
  caddy.auto_https: "off"
```

`caddy.auto_https: "off"` is inferred from the README's rule that a label with no nesting becomes a global option (its example is `caddy.email`). The README does not show this exact line, so confirm it in the generated Caddyfile when it is first built. Quote `off`: unquoted, YAML reads it as the boolean `false`.

```yaml
# each app: labels only
labels:
  caddy: notes.apps-domain.example
  caddy.reverse_proxy: "{{upstreams 3000}}"
```

- Every labeled app becomes public. Use a **dedicated domain** and put Cloudflare Access on the whole domain; Access on a wildcard under the NAS's domain would also gate Immich and WebDAV.
- The free Universal certificate covers one subdomain level: `notes.apps-domain.example` works, `notes.apps.example.com` does not.
