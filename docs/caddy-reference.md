# Caddy

The optional reverse proxy (`caddy_enabled`). It watches Docker: a container's **labels** become Caddy configuration, and Caddy reloads on its own. An app joins when you add labels to its compose file and start it ([caddy-docker-proxy](https://github.com/lucaslorentz/caddy-docker-proxy)).

| I want to | Go to |
|---|---|
| Get `https://` names for my services | [Names for apps](#names-for-apps-caddy_private_domains) |
| Change a service's port or subdomain | [Ports and names](#ports-and-names) |
| Give an app of my own a name | [Label syntax](#label-syntax) |
| Put a name on the start page or another container | [Names of your own](#names-of-your-own) |
| Make a name public | [With cloudflared](#with-cloudflared) |
| A name does not work | [Gotchas](#gotchas-for-this-repo) |

## What `roles/caddy` deploys

- **Needs:** the `fast` drive role for its data. With `caddy_private_domains` it also needs `cloudflare_zones`, the Cloudflare token in the vault and a host joined to the tailnet.
- **Image:** built on the host from `roles/caddy/files/Dockerfile` (`caddy_version`, `caddy_docker_proxy_version` and `caddy_cloudflare_dns_version` in `versions.yml`). The first build compiles Caddy and takes 20+ minutes on a small host.
- **Listens** on ports 80 and 443 of the host. Behind cloudflared the host ports are not needed: cloudflared reaches `caddy:80` over the Docker network.
- **Data:** `caddy_data_dir` (`defaults-data-dirs.yml`). Losing it means Caddy issues its certificates again.
- **Joins** the `services` network (created by `roles/network` on every host) and mounts the Docker socket. `CADDY_INGRESS_NETWORKS` in its compose file names the network it watches. The compose file is `roles/caddy/templates/docker-compose.yml.j2`.

## Web addresses and HTTPS

Every service with a web UI listens on a host port (unless you set it to `""`, below). Any device on your tailnet reaches it at `http://<host's tailnet name>:<port>`. Tailscale already encrypts that traffic, so plain `http` needs no certificate. The Homepage lists every address ([services.md](./services.md#homepage)).

For `https://` names with real certificates, use Caddy with a private domain, below. Each service gets its own name.

One choice is yours: which service is the root of the server. Point a name at it with `caddy_sites`: Homepage for a launcher, Copyparty for a file server, Dockge for an app host.

### Names for apps: `caddy_private_domains`

For `https://<app>.<host>.<your domain>` with a Let's Encrypt certificate, tailnet only, with no port forwarding:

```yaml
caddy_enabled: true
caddy_private_domains: [<host>.example.com]
```

- **Cloudflare:** the domain must equal, or be a subdomain of, one domain in `cloudflare_zones`, and the Cloudflare token in the vault needs `Zone:DNS:Edit` on that zone ([ansible/README.md](../ansible/README.md#vault-secrets)).
- **DNS:** a deploy keeps two DNS-only records, `<host>.example.com` and `*.<host>.example.com`, pointing at the host's Tailscale address. Anyone off the tailnet gets an address they cannot reach.
- **Certificates:** one wildcard certificate per private domain from Let's Encrypt through the Cloudflare DNS challenge, so you open no router port.
- **Port 443:** Caddy needs it on the host. Tailscale keeps `tailscale serve` settings across reboots, so a host that serves on 443 through it needs `sudo tailscale serve reset` first.
- **Public names** are not this: they are `cloudflared_ingress` entries, and Cloudflare serves their certificate. For a service behind the login: [Reach a protected service from outside the tailnet](./auth-reference.md#reach-a-protected-service-from-outside-the-tailnet).

<details>
<summary>DNS records, certificates and the token in detail</summary>

- Every DNS record carries the comment `managed by simple-nas, caddy <host>`. A name that already has a record without it stops the deploy. The deploy deletes records with it for a domain not in the list. `--check` prints the plan.
- To delete the records, set the list to `[]` and run `just deploy caddy --limit <host>` before `teardown.yml -e only=caddy`. Teardown does not call Cloudflare.
- Every name under the wildcard uses one certificate, so public certificate logs list `*.<domain>`, not each service name. A name outside it (the bare domain, a `caddy_sites` name on another domain) has its own certificate.
- Caddy's Cloudflare token is in its compose file on the host, and Caddy sits next to the Docker socket. The compose files are in the offsite backup. It is the same vault token the tunnel uses: DNS edit on every zone plus the tunnel permission.

</details>

#### Service names

On a host that runs Caddy, every web service from this repo that you switch on gets `https://<subdomain>.<private domain>`, such as `https://immich.<host>.example.com`. A service qualifies if its `services.yml` entry has an `icon`, no fixed `port`, and a non-empty `<name>_subdomain`.

- The container names and ports are in [services.yml](../ansible/group_vars/all/services.yml), the `<key>_subdomain` settings in [defaults-ports-and-names.yml](../ansible/group_vars/all/defaults-ports-and-names.yml). A subdomain is a single label.
- Homebridge has no name: it runs on the host network. Gitea's links come from one address ([Gitea](./services.md#gitea)).
- With more than one domain in `caddy_private_domains`, Caddy serves a service with `own_login` (or with Tinyauth off) under every domain. One behind the login gets the first domain only, because the session cookie covers one parent domain ([Tinyauth](./services.md#tinyauth-login)). The Homepage links to the first.
- Crafty's panel serves a self-signed certificate. Caddy accepts it, and browsers see Caddy's.

#### Ports and names

Override them in `host_vars/<host>/vars.yml`. A setting you leave out keeps its default from [defaults-ports-and-names.yml](../ansible/group_vars/all/defaults-ports-and-names.yml).

```yaml
gitea_port: 3100             # host port: the http://<host>:<port> address and the Homepage fallback link
gitea_subdomain: code        # https://code.<host>.example.com
ntfy_subdomain: ""           # "" gives ntfy no name; it keeps http://<host>:<port>
dockge_port: ""              # "" publishes no host port; Dockge is then reachable only at its https name
```

- A port set to `""` publishes no host port for the web UI (Gitea's SSH port and Crafty's game ports are separate). The deploy stops if a service then has neither a port nor a name. The Cloudflare Tunnel is no exception: even a service the tunnel serves on its own keeps a host port.
- Keep the ports while you rely on them to get in when Caddy or Cloudflare is down.
- A changed port also needs the service's own tag (`just deploy gitea --limit <host>`).
- The names come from labels on the Caddy container, and the Homepage reads them when you deploy it.
- After any change here, run `just deploy caddy,homepage --limit <host>` (the Homepage on whichever host runs it). `just deploy caddy` runs only the Caddy role, so the `network` role (it creates the `services` network) must have run on the host once.
- Homepage links assume Caddy's HTTPS port is 443.

#### Names of your own

- **A container of this repo**, such as the root of the server as the start page, takes `caddy_sites`. That is a map of address to Caddy directives (`reverse_proxy` takes `container:port` on the `services` network).

  ```yaml
  caddy_sites:
    <host>.example.com: {reverse_proxy: "homepage:3000"}
    gh.<host>.example.com: {redir: "https://github.com{uri}"}   # gh.<host>.example.com/owner/repo opens github.com/owner/repo
  homepage_host: <host>.example.com   # Homepage refuses any other address
  ```

  - The domain itself or any name one label below it can be an address, so `<host>.example.com` can open the start page, Copyparty or Dockge.
  - `{import: tinyauth_forwarder}` as one of the directives puts that name behind the login ([Tinyauth](./services.md#tinyauth-login)).
  - Gitea, ntfy and similar apps build links from a configured base URL, so change that too.
- **An app of your own** takes a name with labels (see [Label syntax](#label-syntax)).

### Short name

A host with `caddy_private_domains` redirects `http://<host>` (302) to the first private domain, `https://<host>.example.com`.

- `<host>` is the host's name in the inventory, so give each host its MagicDNS short name there (the first label, such as `pi4`).
- Type `http://pi4` or `pi4/`, or the browser treats the text as a search. The redirect is plain http because no certificate can cover a name that is not a real domain.

## Label syntax

Labels go on the app's container, which must join the same `services` network. For the services of this repo, the Caddy container carries the labels instead. It holds one site per service from `web_services`, one per `caddy_sites` entry, and the short-name redirect ([names for apps](#names-for-apps-caddy_private_domains), [short name](#short-name)).

```yaml
services:
  whoami:
    image: traefik/whoami
    networks: [services]
    labels:
      caddy: whoami.example.com                    # site address
      caddy.reverse_proxy: "{{upstreams 80}}"      # port the app listens on inside the container

networks:
  services:
    external: true                                 # made by the host, not by this stack
```

A container of this repo carries no labels: its name comes from its `services.yml` entry or from `caddy_sites` ([above](#names-for-apps-caddy_private_domains)). For a name behind the login, add `caddy.import: tinyauth_forwarder` next to the other labels ([example](./auth-reference.md#protect-an-app-of-your-own)).

| Label | Becomes |
|---|---|
| `caddy: a.example.com` | A site block |
| `caddy: a.example.com, b.example.com` | One block for two hostnames |
| `caddy.reverse_proxy: "{{upstreams 8080}}"` | `reverse_proxy <container-ip>:8080` |
| `caddy.tls: internal` | Caddy's own CA instead of Let's Encrypt |
| `caddy.header: X-Frame-Options SAMEORIGIN` | A `header` directive |
| `caddy_0`, `caddy_1` (with matching `caddy_0.reverse_proxy`, ...) | Separate site blocks in one container |
| `caddy_ingress_network: name` | Use this network for `{{upstreams}}` on this container |

Dots mean nesting: `caddy.basic_auth.alice: <hash>` produces a `basic_auth` block. An empty value gives a directive with no arguments. This repo uses that for a backend with a self-signed certificate (`scheme: https` in `services.yml`).

## Gotchas for this repo

- **First step when a name does not work:** read the generated file: `docker exec caddy cat /config/caddy/Caddyfile.autosave`.
- **Shared network.** A stack must declare the external `services` network and join it. A container not on it is invisible to `{{upstreams}}`.
- **Jinja collision.** `{{upstreams}}` is also Jinja syntax. In any file rendered by Ansible, wrap it: `{% raw %}{{upstreams 80}}{% endraw %}`. Dockge stacks are plain files and need no escaping.
- **TLS.** Behind cloudflared, use an `http://` site address ([With cloudflared](#with-cloudflared)). Names under a `caddy_private_domains` entry get a certificate automatically. For any other name use `tls internal` unless the Cloudflare token covers its zone.
- **Docker socket.** Caddy mounts it ([glossary](./glossary.md#drives-and-docker)), so anything that can set labels on a container can publish a route.

<details>
<summary>Proxy headers, <code>caddy_sites</code> values, TLS, modes</summary>

- **Apps that trust proxy headers.** Caddy sends `X-Forwarded-For`, `-Proto` and `-Host`. An app that rejects requests unless it reads them (Copyparty's `rproxy` and `xff-src` in `roles/copyparty/templates/copyparty.conf.j2`) must be told to trust the proxy's network.
- **`caddy_sites` values.** Each directive becomes a label `caddy_N.<directive>`, so a value is one string and a dot in the key nests (`header.X-Frame-Options`). `{uri}` takes single braces, and write a `$` as `$$` (Compose reads it first).
- **Let's Encrypt HTTP-01** needs the internet to reach ports 80/443, which a LAN or tailnet does not allow. Use `tls internal` and trust Caddy's root CA on each device, or the DNS challenge above.
- **Modes.** The role runs the standalone mode (controller and server in one container). The controller/server split is for Swarm clusters.

</details>

## With cloudflared

You need no router port forwarding. A public hostname is an explicit entry in the host's `cloudflared_ingress`. There is no wildcard to Caddy, because every labeled container would become public. Any host that sets `cloudflared_enabled: true` runs its own tunnel with its own `cloudflared_ingress`. See [services.md](./services.md#cloudflare-add-a-public-hostname).

For a published app, point the entry at Caddy and write the app's label as `caddy: http://notes.example.com` (Cloudflare terminates TLS). An `http://` site address gets a plain `200` with no redirect, so you need no global `auto_https` label.
