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
- Ubuntu Server renders netplan with systemd-networkd, not NetworkManager, and the direct link is built with `nmcli`. With the link on, the deploy stops with a message if NetworkManager is not running; leave the link off on Ubuntu Server. Ubuntu Desktop uses NetworkManager and works. The link expects the default Ethernet profile to be named `Wired connection 1`, as on Raspberry Pi OS and Ubuntu Desktop; on a host where it has another name, the link's disable and revert steps fail.
- The Ubuntu Server installer writes its own netplan file and a cloud-init file that already disables cloud-init's network config; Raspberry Pi Imager and Ubuntu's Raspberry Pi images use cloud-init at first boot. Either way the file `roles/network` writes makes cloud-init leave the network alone afterwards.

## Direct Ethernet link

Cable the Pi's idle Ethernet port straight to a laptop for fast transfers (about 117 MB/s measured, against about 4.3 MB/s over Tailscale on wifi). The Pi is `10.10.20.1`; the laptop gets `10.10.20.2` from a `dnsmasq` instance scoped to that port. The deploy refuses if the port carries the host's default route.

1. Set `direct_link_enabled: true` in `host_vars/<host>/vars.yml` (the address and port settings keep their defaults from `ansible/group_vars/all/defaults.yml` unless you override them), then `just deploy network --limit <host>`.
2. Plug the cable into the Pi and the laptop. The laptop picks up its address automatically.
3. Open `http://10.10.20.1:3923` for Copyparty.

The link can't reach the internet or collide with a VPN:
- `dnsmasq` hands out DHCP only (no DNS, no gateway), and neither end has a gateway, so there is no route off the cable.
- `10.10.20.0/30` has two usable addresses, too small to overlap common VPN or home-router ranges such as `10.8.0.0/24` or `192.168.1.0/24`.
