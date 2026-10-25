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

For `https://` names with real certificates, use Caddy with a private domain, below. One choice is yours: which service is the root of the server. Point a name at it with `caddy_sites`: Homepage for a launcher, Copyparty for a file server, Dockge for an app host.

### Names for apps: `caddy_private_domains`

For `https://<app>.<host>.<your domain>` with a Let's Encrypt certificate, tailnet only, with no port forwarding:

```yaml
caddy_enabled: true
caddy_private_domains: [pi4.example.com]
```

- The domain must contain one from `cloudflare_zones`, and the Cloudflare token in the vault needs `Zone:DNS:Edit` on that zone ([ansible/README.md](../ansible/README.md#vault-secrets)).
- A deploy keeps two DNS-only records, `pi4.example.com` and `*.pi4.example.com`, pointing at the host's Tailscale address. Anyone off the tailnet gets an address they cannot reach. Every record carries the comment `managed by simple-nas, caddy <host>`; a name that already has a record without it stops the deploy, and records with it for a domain that is not in the list are deleted. `--check` prints the plan.
- Caddy asks Let's Encrypt for each name through the Cloudflare DNS challenge, so no port is opened. Names appear in public certificate logs.
- A service from this repo takes a name with `caddy_sites`, a map of name to `container:port` on the `services` network. The root of the server as the start page:

  ```yaml
  caddy_sites: {home.pi4.example.com: "homepage:3000"}
  homepage_host: home.pi4.example.com   # Homepage refuses any other address
  ```

  Gitea, ntfy and similar apps build links from a configured base URL, so change that too.
- An app of your own takes a name with labels: `caddy: webtop.pi4.example.com` and `caddy.reverse_proxy: "{{upstreams 3000}}"` ([caddy-reference.md](./caddy-reference.md)).
- Caddy needs port 443 on the host. Tailscale keeps `tailscale serve` settings across reboots, so a host that ever served on 443 needs `sudo tailscale serve reset` first.
- To remove the records, set the list to `[]` and deploy before `teardown.yml --tags caddy`; teardown does not call Cloudflare.
- Public names do not use this: they are entries in `cloudflared_ingress`, and Cloudflare serves their certificate.
- Both the bare name and any name under it can be a `caddy_sites` address, so `pi4.example.com` itself can open the start page, Copyparty or Dockge.
- Caddy's token is in its compose file on the host (the compose files are in the offsite backup), and Caddy sits next to the Docker socket. It is the same vault token the tunnel uses, with DNS edit on every zone and the tunnel permission.

## Direct Ethernet link

Cable the Pi's idle Ethernet port straight to a laptop for fast transfers (about 117 MB/s measured, against about 4.3 MB/s over Tailscale on wifi). The Pi is `10.10.20.1`; the laptop gets `10.10.20.2` from a `dnsmasq` instance scoped to that port. The deploy refuses if the port carries the host's default route.

1. Set `direct_link_enabled: true` in `host_vars/<host>/vars.yml` (the address and port settings keep their defaults from `ansible/group_vars/all/defaults.yml` unless you override them), then `just deploy network --limit <host>`.
2. Plug the cable into the Pi and the laptop. The laptop picks up its address automatically.
3. Open `http://10.10.20.1:3923` for Copyparty.

The link can't reach the internet or collide with a VPN:
- `dnsmasq` hands out DHCP only (no DNS, no gateway), and neither end has a gateway, so there is no route off the cable.
- `10.10.20.0/30` has two usable addresses, too small to overlap common VPN or home-router ranges such as `10.8.0.0/24` or `192.168.1.0/24`.
