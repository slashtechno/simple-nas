# Caddy

The optional reverse proxy: what `roles/caddy` deploys, the names and ports it serves, and the label syntax of caddy-docker-proxy ([project README](https://github.com/lucaslorentz/caddy-docker-proxy)).

## What it does

It watches Docker. A container's **labels** become Caddy configuration, and Caddy reloads on its own. Adding an app means adding labels to its compose file and starting it; nothing else to edit.

## What `roles/caddy` deploys

Runs on any host that sets `caddy_enabled: true`; needs the `fast` drive role for its data. With `caddy_private_domains` it also needs `cloudflare_zones`, the Cloudflare token in the vault and a host joined to the tailnet. The image is built on the host from `roles/caddy/files/Dockerfile`: Caddy, caddy-docker-proxy and the Cloudflare DNS plugin, each pinned in `versions.yml` (`caddy_version`, `caddy_docker_proxy_version`, `caddy_cloudflare_dns_version`). The first build compiles Caddy and takes a few minutes on a Pi.

Caddy listens on ports 80 and 443 of the host; `caddy_data_dir` is in `ansible/group_vars/all/defaults.yml`. Losing `caddy_data_dir` means certificates are issued again.

The container joins `services` (`docker_network`, created by `roles/network` on every server), has `CADDY_INGRESS_NETWORKS` set to it, and mounts the Docker socket. The compose file is `roles/caddy/templates/docker-compose.yml.j2`. Behind cloudflared the host ports are not needed: cloudflared reaches `caddy:80` over the Docker network.

## Web addresses and HTTPS

Every service with a web UI listens on a host port (unless you set it to `""`, below) and is reachable from any device on your tailnet at `http://<host's tailnet name>:<port>`. Tailscale already encrypts that traffic, so plain `http` needs no certificate. The Homepage lists every address ([services.md](./services.md#homepage)).

For `https://` names with real certificates, use Caddy with a private domain, below. Each service gets its own name; one choice is yours: which service is the root of the server. Point a name at it with `caddy_sites`: Homepage for a launcher, Copyparty for a file server, Dockge for an app host.

### Names for apps: `caddy_private_domains`

For `https://<app>.<host>.<your domain>` with a Let's Encrypt certificate, tailnet only, with no port forwarding:

```yaml
caddy_enabled: true
caddy_private_domains: [pi4.example.com]
```

- **Cloudflare:** the domain must equal, or be a subdomain of, one domain in `cloudflare_zones`, and the Cloudflare token in the vault needs `Zone:DNS:Edit` on that zone ([ansible/README.md](../ansible/README.md#vault-secrets)).
- **DNS:** a deploy keeps two DNS-only records, `pi4.example.com` and `*.pi4.example.com`, pointing at the host's Tailscale address. Anyone off the tailnet gets an address they cannot reach.
  - Every record carries the comment `managed by simple-nas, caddy <host>`.
  - A name that already has a record without it stops the deploy. Records with it for a domain not in the list are deleted.
  - `--check` prints the plan. To remove the records, set the list to `[]` and run `just deploy caddy --limit <host>` before `teardown.yml -e only=caddy`; teardown does not call Cloudflare.
- **Certificates:** Caddy asks Let's Encrypt for each name through the Cloudflare DNS challenge, so no port is opened. Names appear in public certificate logs.
- **Port 443:** Caddy needs it on the host. Tailscale keeps `tailscale serve` settings across reboots, so a host that serves on 443 through it needs `sudo tailscale serve reset` first.
- **Public names** do not use this: they are entries in `cloudflared_ingress`, and Cloudflare serves their certificate.
- **Secrets:** Caddy's token is in its compose file on the host (the compose files are in the offsite backup), and Caddy sits next to the Docker socket. It is the same vault token the tunnel uses, with DNS edit on every zone and the tunnel permission.

#### Service names

On a host that runs Caddy, every web service from this repo that is switched on (a `services.yml` entry with an `icon` and a non-empty `<name>_subdomain`) gets `https://<subdomain>.<private domain>`, for example `https://immich.pi4.example.com`.

- The container names and ports are in [services.yml](../ansible/group_vars/all/services.yml), the `<key>_subdomain` settings in [defaults.yml](../ansible/group_vars/all/defaults.yml). A subdomain is a single label.
- Homebridge has no name: it runs on the host network. Gitea has none by default (`gitea_subdomain: ""`): it builds links from `gitea_root_url`, a single address.
- With more than one domain in `caddy_private_domains`, a service with `own_login` (or with Tinyauth off) is served under every domain, and one behind the login under the first only, because the session cookie covers one parent domain ([Tinyauth](./services.md#tinyauth-login)). The Homepage links to the first.
- Crafty's panel serves a self-signed certificate; Caddy accepts it and browsers see Caddy's.

#### Ports and names

Override them in `host_vars/<host>/vars.yml`; a setting you leave out keeps its default from [defaults.yml](../ansible/group_vars/all/defaults.yml).

```yaml
gitea_port: 3100             # host port: the http://<host>:<port> address and the Homepage fallback link
gitea_subdomain: code        # https://code.pi4.example.com
ntfy_subdomain: ""           # "" gives ntfy no name; it keeps http://<host>:<port>
dockge_port: ""              # "" publishes no host port; Dockge is then reachable only at its https name
```

- A port set to `""` publishes no host port for the web UI (Gitea's SSH port and Crafty's game ports are separate). The deploy stops if a service then has neither a port nor a name; a service reached only through the Cloudflare Tunnel keeps its port.
- Keep the ports while you rely on them to get in when Caddy or Cloudflare is down.
- A changed port also needs the service's own tag (`just deploy gitea --limit <host>`).
- The names come from labels on the Caddy container, and the Homepage reads them when it is deployed. `just deploy caddy` runs only the Caddy role, so the `network` role (it creates the `services` network) must have run on the host once. After any change here, run `just deploy caddy,homepage --limit <host>` (the Homepage on whichever host runs it). Homepage links assume Caddy's HTTPS port is 443.

#### Names of your own

- **A container of this repo**, such as the root of the server as the start page, takes `caddy_sites`: a map of address to Caddy directives (`reverse_proxy` takes `container:port` on the `services` network).

  ```yaml
  caddy_sites:
    home.pi4.example.com: {reverse_proxy: "homepage:3000"}
    gh.pi4.example.com: {redir: "https://github.com{uri}"}   # gh.pi4.example.com/owner/repo opens github.com/owner/repo
  homepage_host: home.pi4.example.com   # Homepage refuses any other address
  ```

  - The domain itself or any name one label below it can be an address, so `pi4.example.com` can open the start page, Copyparty or Dockge.
  - `{import: tinyauth_forwarder}` as one of the directives puts that name behind the login ([Tinyauth](./services.md#tinyauth-login)).
  - Gitea, ntfy and similar apps build links from a configured base URL, so change that too.
- **An app of your own** takes a name with labels (see [Label syntax](#label-syntax)).

### Short name

A host with `caddy_private_domains` redirects `http://<host>` (302) to the first private domain: `http://pi4` to `https://pi4.example.com`.

- `<host>` is the host's name in the inventory, so give each host its MagicDNS short name there (the first label, such as `pi4`).
- Type `http://pi4` or `pi4/`, or the browser treats the text as a search. The redirect is plain http because no certificate can cover a name that is not a real domain.

## Label syntax

Labels go on the app's container, which must join the same `services` network. For the services of this repo, the Caddy container carries the labels instead (one site per service from `web_services`, one per `caddy_sites` entry, and the short-name redirect) ([names for apps](#names-for-apps-caddy_private_domains), [short name](#short-name)).

```yaml
services:
  whoami:
    image: traefik/whoami
    networks: [services]
    labels:
      caddy: whoami.example.com                    # site address
      caddy.reverse_proxy: "{{upstreams 80}}"      # port the app listens on inside the container
```

A container of this repo carries no labels: its name comes from its `services.yml` entry or from `caddy_sites` ([above](#names-for-apps-caddy_private_domains)). For a name behind the login, add `caddy.import: tinyauth_forwarder` next to the other labels ([Tinyauth](./services.md#tinyauth-login)).

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

- **Apps that trust proxy headers.** Caddy sends `X-Forwarded-For`, `-Proto` and `-Host`. An app that rejects requests unless it reads them (Copyparty's `rproxy` and `xff-src` in `roles/copyparty/templates/copyparty.conf.j2`) must be told to trust the proxy's network.
- **Jinja collision.** `{{upstreams}}` is also Jinja syntax. In any file rendered by Ansible, wrap it: `{% raw %}{{upstreams 80}}{% endraw %}`. Dockge stacks are plain files and need no escaping.
- **Shared network.** A stack must declare the external `services` network (`docker_network`) and join it; a container not on it is invisible to `{{upstreams}}`.
- **TLS.**
  - Let's Encrypt HTTP-01 needs the internet to reach ports 80/443 on the machine. On a LAN or tailnet that is not the case, so use `tls internal` and trust Caddy's root CA on each device.
  - Behind cloudflared, Cloudflare terminates TLS. Use `http://app.example.com` as the site address so Caddy does not attempt ACME.
  - Names under a `caddy_private_domains` entry get their certificate through the Cloudflare DNS challenge, which needs no open ports ([Web addresses and HTTPS](#web-addresses-and-https)). For a name outside those domains Caddy tries the same challenge; use `tls internal` unless the Cloudflare token covers its zone.
- **`caddy_sites` values.** Each directive becomes a label `caddy_N.<directive>`, so a value is one string and a dot in the key nests (`header.X-Frame-Options`); `{uri}` takes single braces, and a `$` is written `$$` (Compose reads it first).
- **Checking a site.** Read the generated file: `docker exec caddy cat /config/caddy/Caddyfile.autosave`.
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
