# Networking

Wifi profiles are managed on the host with `nmcli`, not by Ansible. Ansible sets up the shared Docker network and the direct Ethernet link.

## If a Pi drops off the network

Work down the list; stop when you can reach it.

1. **Tailscale.** If the Pi is online by any route (home wifi, a phone hotspot), `ssh user@<tailscale name>` reaches it from anywhere. Disable key expiry for each server in the Tailscale admin console; a headless Pi with an expired node key (180 days by default) locks you out.
2. **Direct Ethernet link**, if enabled: cable between laptop and Pi; see [Direct Ethernet link](#direct-ethernet-link).
3. **Local console:** monitor and keyboard.

Once logged in:

```bash
nmcli con show                 # saved profiles, and which are active
nmcli con up "<home profile>"  # switch to home wifi
nmcli device wifi list         # networks the Pi can see right now
```

## How the Pi picks a network

- NetworkManager's `autoconnect-priority` chooses among saved networks that are in range. It does not check for internet: with home wifi up and the ISP down, the Pi stays on home wifi.
- Autoconnect does not replace an already active profile (NetworkManager docs), so a Pi on a hotspot stays there when home wifi returns; run `nmcli con up "<home profile>"` over Tailscale.
- There is no switch-back automation. If one is needed, the options are a NetworkManager dispatcher script (`/etc/NetworkManager/dispatcher.d/`, root-owned, run with the interface name and an event such as `up`) or a systemd timer running `nmcli device wifi rescan` and `nmcli con up`.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, alongside wifi.

## Rules for changing network config

- Do not change the connection Ansible is using without a way back in (Tailscale or Ethernet).
- Run `just preview network --limit <host>` first.

## What `roles/network` does

- Creates the shared Docker network `docker_network` (`services`) on every host.
- If `/etc/cloud/cloud.cfg.d` exists, writes `99-disable-network-config.cfg` (`network: {config: disabled}`) so cloud-init, which configures a machine once at first boot, cannot rewrite the network config later.
- Sets up the direct Ethernet link when `direct_link_enabled` is true. The `direct_link_*` settings and their defaults are in `ansible/group_vars/all/defaults.yml`; override them in the host's `vars.yml`.
- Does not edit `/etc/netplan/90-NM-*.yaml`, which NetworkManager generates.
- The direct link uses whichever network stack the host runs. With NetworkManager running (Raspberry Pi OS, Ubuntu Desktop) it is an `nmcli` profile named `direct-link`, and the default Ethernet profile must be named `Wired connection 1` (the name on those systems); on a host where it has another name, the link's disable and revert steps fail. Without NetworkManager (Ubuntu Server, which renders netplan with systemd-networkd) it is `/etc/netplan/60-direct-link.yaml`, which overrides the port's DHCP from the installer's file, and the deploy runs `netplan apply`. A host with neither stops with a message.
- The Ubuntu Server installer writes its own netplan file and a cloud-init file that already disables cloud-init's network config; Raspberry Pi Imager and Ubuntu's Raspberry Pi images use cloud-init at first boot. Either way the file `roles/network` writes makes cloud-init leave the network alone afterwards.

## Web addresses and HTTPS

Every service with a web UI listens on a host port and is reachable from any device on your tailnet at `http://<host's tailnet name>:<port>`. Tailscale already encrypts that traffic, so plain `http` needs no certificate. The Homepage lists every address ([services.md](./services.md#homepage)).

For `https://` names with real certificates, use Caddy with a private domain, below. Each service gets its own name; one choice is yours: which service is the root of the server. Point a name at it with `caddy_sites`: Homepage for a launcher, Copyparty for a file server, Dockge for an app host.

### Names for apps: `caddy_private_domains`

For `https://<app>.<host>.<your domain>` with a Let's Encrypt certificate, tailnet only, with no port forwarding:

```yaml
caddy_enabled: true
caddy_private_domains: [pi4.example.com]
```

- The domain must contain one from `cloudflare_zones`, and the Cloudflare token in the vault needs `Zone:DNS:Edit` on that zone ([ansible/README.md](../ansible/README.md#vault-secrets)).
- A deploy keeps two DNS-only records, `pi4.example.com` and `*.pi4.example.com`, pointing at the host's Tailscale address. Anyone off the tailnet gets an address they cannot reach. Every record carries the comment `managed by simple-nas, caddy <host>`; a name that already has a record without it stops the deploy, and records with it for a domain that is not in the list are deleted. `--check` prints the plan.
- Caddy asks Let's Encrypt for each name through the Cloudflare DNS challenge, so no port is opened. Names appear in public certificate logs.
- On a host that runs Caddy, every service from this repo that is switched on gets `https://<subdomain>.<private domain>`, for example `https://immich.pi4.example.com`. The subdomains and their container ports are in [web_services.yml](../ansible/group_vars/all/web_services.yml) and the `*_subdomain` settings in [defaults.yml](../ansible/group_vars/all/defaults.yml). Homebridge has no name: it runs on the host network. Gitea has none by default (`gitea_subdomain: ""`): it builds links from `gitea_root_url`, a single address.
- Override ports and names in `host_vars/<host>/vars.yml`; any setting you leave out keeps its default from [defaults.yml](../ansible/group_vars/all/defaults.yml). A changed port also needs the service's own tag (`just deploy gitea --limit <host>`). A port set to `""` publishes no host port, so the service answers only at its Caddy name; the deploy stops if a service has neither. Keep the ports while you rely on them to get in when Caddy or Cloudflare is down:

  ```yaml
  gitea_port: 3100             # host port: the http://<host>:<port> address and the Homepage fallback link
  gitea_subdomain: code        # https://code.pi4.example.com
  ntfy_subdomain: ""           # "" gives ntfy no name; it keeps http://<host>:<port>
  dockge_port: ""              # "" publishes no host port; Dockge is then reachable only at its https name
  ```

  The names come from the labels on the Caddy container, and the Homepage reads them when it is deployed, so run `just deploy caddy,homepage --limit <host>` after any of these changes (the Homepage on whichever host runs it). Homepage links assume Caddy's HTTPS port is 443. A subdomain is a single label. The container ports in `web_services.yml` are fixed by the images and are not settings. With more than one domain in `caddy_private_domains`, each service is served under every domain and the Homepage links to the first. Crafty's panel serves a self-signed certificate; Caddy accepts it and browsers see Caddy's.
- A name of your own for a container of this repo, such as the root of the server as the start page, takes `caddy_sites`, a map of name to `container:port` on the `services` network:

  ```yaml
  caddy_sites: {home.pi4.example.com: "homepage:3000"}
  homepage_host: home.pi4.example.com   # Homepage refuses any other address
  ```

  Gitea, ntfy and similar apps build links from a configured base URL, so change that too.
- An app of your own takes a name with labels: `caddy: webtop.pi4.example.com` and `caddy.reverse_proxy: "{{upstreams 3000}}"` ([caddy-reference.md](./caddy-reference.md)).
- Caddy needs port 443 on the host. Tailscale keeps `tailscale serve` settings across reboots, so a host that serves on 443 through it needs `sudo tailscale serve reset` first.
- To remove the records, set the list to `[]` and deploy before `teardown.yml --tags caddy`; teardown does not call Cloudflare.
- Public names do not use this: they are entries in `cloudflared_ingress`, and Cloudflare serves their certificate.
- Both the bare name and any name one label below it (`app.pi4.example.com`) can be a `caddy_sites` address, so `pi4.example.com` itself can open the start page, Copyparty or Dockge.
- Caddy's token is in its compose file on the host (the compose files are in the offsite backup), and Caddy sits next to the Docker socket. It is the same vault token the tunnel uses, with DNS edit on every zone and the tunnel permission.

### Short names

A host with `caddy_private_domains` answers its short names on port 80 and redirects them (302) to the first private domain: `http://pi4` to `https://pi4.example.com`, and `http://webtop.pi4` to `https://webtop.pi4.example.com`. The short name is the host's name in the inventory, so give each host its MagicDNS name there; any other name gets short names that never resolve. It covers every service and every app you label in Dockge; nothing is listed per service.

- `pi4` resolves through MagicDNS, so `http://pi4/` works as is.
- `webtop.pi4` needs the domain as a Tailscale search domain, set by hand in the admin console (DNS, Search domains, add `example.com`). Ansible does not manage it. Devices then try `webtop.pi4.example.com` for `webtop.pi4`.
- Caddy sees only the name you typed, so the search domain is not a Caddy setting.
- Type `http://` or a trailing slash (`webtop.pi4/`), or the browser treats the text as a search. The redirect is plain http because no certificate can cover a name that is not a real domain.
- A subdomain is one label: `webtop.pi4` redirects, `a.b.pi4` does not.

## Direct Ethernet link

Cable the Pi's idle Ethernet port straight to a laptop for fast transfers (about 117 MB/s measured, against about 4.3 MB/s over Tailscale on wifi). The Pi is `10.10.20.1`; the laptop gets `10.10.20.2` from a `dnsmasq` instance scoped to that port. The deploy refuses if the port carries the host's default route.

1. Set `direct_link_enabled: true` in `host_vars/<host>/vars.yml` (the address and port settings keep their defaults from `ansible/group_vars/all/defaults.yml` unless you override them), then `just deploy network --limit <host>`.
2. Plug the cable into the Pi and the laptop. The laptop picks up its address automatically.
3. Open `http://10.10.20.1:3923` for Copyparty.

The link can't reach the internet or collide with a VPN:
- `dnsmasq` hands out DHCP only (no DNS, no gateway), and neither end has a gateway, so there is no route off the cable.
- `10.10.20.0/30` has two usable addresses, too small to overlap common VPN or home-router ranges such as `10.8.0.0/24` or `192.168.1.0/24`.
