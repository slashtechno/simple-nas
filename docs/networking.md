# Networking

Manage wifi profiles on the host with `nmcli`, not Ansible. Ansible sets up the shared Docker network, the optional direct Ethernet link and the optional connectivity watchdog. HTTPS names and ports for the web apps are in [caddy-reference.md](./caddy-reference.md#web-addresses-and-https).

| I want to | Go to |
|---|---|
| Reach a host that dropped off the network | [If a host drops off the network](#if-a-host-drops-off-the-network) |
| Reconnect automatically when TCP stops working | [Connectivity watchdog](#connectivity-watchdog) |
| Copy big files over a cable | [Direct Ethernet link](#direct-ethernet-link) |
| Change network settings safely | [Rules for changing network config](#rules-for-changing-network-config) |

## If a host drops off the network

Work down the list. Stop when you can reach it.

1. **Tailscale.** If the host is online by any route (home wifi, a phone hotspot), `ssh user@<tailnet name>` reaches it from anywhere ([tailnet name](./glossary.md#names-logins-and-the-web)). Disable key expiry for each server in the Tailscale admin console: a headless host with an expired node key (180 days by default) locks you out.
2. **Direct Ethernet link**, if enabled: a cable between your laptop and the host. See [Direct Ethernet link](#direct-ethernet-link).
3. **Local console:** monitor and keyboard.

Once logged in:

```bash
nmcli con show                 # saved profiles, and which are active
nmcli con up "<home profile>"  # switch to home wifi
nmcli device wifi list         # networks the host can see right now
```

## Rules for changing network config

- Do not change the connection Ansible is using without a way back in (Tailscale or Ethernet).
- Run `just preview network --limit <host>` first.

<details>
<summary>How the host picks a network</summary>

- NetworkManager's `autoconnect-priority` chooses among saved networks that are in range. It does not check for internet: with home wifi up and the ISP down, the host stays on home wifi.
- Autoconnect does not replace an already active profile, so a host on a hotspot stays there when home wifi returns. Run `nmcli con up "<home profile>"` over Tailscale.
- There is no switch-back automation. To add one, use a NetworkManager dispatcher script (`/etc/NetworkManager/dispatcher.d/`) or a systemd timer running `nmcli`.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, alongside wifi.

</details>

<details>
<summary>What <code>roles/network</code> does</summary>

- Creates the shared Docker network `docker_network` (`services`) on every host.
- If `/etc/cloud/cloud.cfg.d` exists, writes `99-disable-network-config.cfg` (`network: {config: disabled}`). That stops cloud-init from rewriting the network config later. Raspberry Pi Imager and Ubuntu's Raspberry Pi images use cloud-init, which configures a machine at first boot.
- Sets up the direct Ethernet link when `direct_link_enabled` is true.
- Does not edit `/etc/netplan/90-NM-*.yaml`, which NetworkManager generates.
- The direct link uses whichever network stack the host runs. With NetworkManager (Raspberry Pi OS, Ubuntu Desktop) it is an `nmcli` profile named `direct-link` with a higher autoconnect priority than the installer's. Without it (Ubuntu Server, which configures the network with netplan, Ubuntu's network config files) it is `/etc/netplan/60-direct-link.yaml`. That file overrides the port's DHCP from the installer's file, and the deploy runs `netplan apply` to load it. A host with neither stops with a message.

</details>

## Connectivity watchdog

A host can stay on wifi with a valid address and working ping while every TCP connection and DNS lookup fails. Nothing reports it, and the host drops off Tailscale. `connectivity_watchdog_enabled: true` (default off) runs `connectivity-watchdog.sh` from root's `cron` every 2 minutes:

- It tries a TCP connection to port 443 of each address in `connectivity_probe_addresses`. The host is online if any connects. The tuning settings and their defaults are in `ansible/roles/connectivity_watchdog/defaults/main.yml`.
- After 3 failed checks in a row it runs `nmcli connection down` and `up` on the connection that carries the default route. That is wifi or Ethernet, never the direct link, which has no gateway.
- It waits 30 minutes between reconnects and stops after 6 per outage, so a real internet outage does not loop. It never reboots.
- A host without NetworkManager only logs.
- Every step is in the system log (`journalctl -t connectivity`). When the check works again after an outage, one alert goes through `alert.sh` ([ntfy](./services.md#ntfy-failure-alerts)).

Deploy it with `just deploy connectivity_watchdog --limit <host>`. Run `just deploy common` first if alerts are new. Setting the flag to false removes its cron job and script on the next deploy.

## Direct Ethernet link

Cable the host's idle Ethernet port straight to a laptop for fast transfers (about 117 MB/s, against about 4.3 MB/s over Tailscale on wifi). The host is `10.10.20.1`. The laptop gets `10.10.20.2` from a `dnsmasq` instance scoped to that port. The deploy refuses if the port carries the host's default route.

1. Set `direct_link_enabled: true` in `host_vars/<host>/vars.yml`. The address settings are in `ansible/group_vars/all/defaults-direct-link.yml`, and the same `vars.yml` can override them. Then `just deploy network --limit <host>`.
2. Plug the cable into the host and the laptop. The laptop picks up its address automatically.
3. Open `https://10.10.20.1:3923` for Copyparty (the default `direct_link_ip` and `copyparty_port`). Copyparty makes its own self-signed certificate and serves it on the same port as plain http, so the browser warns once. `http://` on that port works too.

The link has no route to the internet: `dnsmasq` hands out DHCP only (no DNS, no gateway). `10.10.20.0/30` does not overlap common VPN or home-router ranges such as `10.8.0.0/24` or `192.168.1.0/24`.
