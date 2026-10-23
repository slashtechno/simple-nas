# Networking

Per-host network settings in `host_vars` and a self-reverting apply are not built yet; they are marked **Planned** (design in [plans/multi-host.md](./plans/multi-host.md)). Everything else here is current.

## If a Pi drops off the network

Work down the list; stop when you can reach it.

1. **Tailscale.** If the Pi is online by any route (home wifi, a phone hotspot), `ssh user@<tailscale name>` reaches it from anywhere. Disable key expiry for each server in the Tailscale admin console; a headless Pi with an expired node key (180 days by default) locks you out.
2. **Direct Ethernet link**, if enabled: cable between laptop and Pi; see [services.md](./services.md#direct-ethernet-link).
3. **Local console:** monitor and keyboard.

Once logged in:

```bash
nmcli con show                 # saved profiles, and which are active
nmcli con up "<home profile>"  # switch to home wifi
nmcli device wifi list         # networks the Pi can see right now
```

## How the Pi picks a network

- NetworkManager's `autoconnect-priority` chooses among saved networks that are in range. It does not check for internet: with home wifi up and the ISP down, the Pi stays on home wifi.
- Autoconnect does not replace an already active profile (NetworkManager docs), so a Pi on a hotspot probably stays there when home wifi returns; run `nmcli con up "<home profile>"` over Tailscale. Not verified on these Pis.
- There is no switch-back automation. If one is needed, the options are a NetworkManager dispatcher script (`/etc/NetworkManager/dispatcher.d/`, root-owned, run with the interface name and an event such as `up`) or a systemd timer running `nmcli device wifi rescan` and `nmcli con up`.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, alongside wifi.

## Rules for changing network config

- Do not change the connection Ansible is using without a way back in (Tailscale or Ethernet).
- Run `just preview network --limit <host>` first.
- **Planned:** apply with a built-in revert (`netplan try`, or a timed `nmcli` revert).

## What `roles/network` does

- Creates the shared Docker network `nas_network` (`nas-services`).
- If `/etc/cloud/cloud.cfg.d` exists, writes `99-disable-network-config.cfg` (`network: {config: disabled}`) so cloud-init, which configures a machine once at first boot, cannot rewrite the network config later.
- Sets up the direct Ethernet link when `direct_link_enabled` is true (`direct_link_*` in `host_vars`).
- Does not edit `/etc/netplan/90-NM-*.yaml`, which NetworkManager generates.
- Ubuntu Server renders netplan with systemd-networkd, not NetworkManager. Netplan vs `nmcli` for per-host profiles is undecided until the spike below is done.

## To do: netplan spike on pi5

Run by hand on pi5, which serves nothing. Keep a monitor handy or stay connected over Ethernet.

1. `mkdir -p ~/netplan-backup && sudo cp /etc/netplan/90-NM-*.yaml ~/netplan-backup/`
2. Write a test file such as `/etc/netplan/60-test.yaml` for `wlan0` with your SSID, then `sudo netplan try`. Do not press Enter at the prompt.
3. Pass 1: the change rolls back after the timeout.
4. Run `sudo netplan try` again and confirm; run `nmcli con show`. Pass 2: one profile per interface or SSID, no duplicates next to the `netplan-*` ones.
5. Remove the test file and run `sudo netplan apply`.

If either pass fails, the plan falls back to `nmcli` with per-host profile names.
