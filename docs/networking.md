# Networking

What is true today applies to the Pi 4 NAS. Parts marked **Planned** come from [plans/multi-host.md](./plans/multi-host.md) and are not built yet.

## If a Pi drops off the network

Work down the list; stop when you can reach it.

1. **Tailscale.** If the Pi is online through any connection (home wifi, a phone hotspot), it is reachable at its Tailscale name from anywhere: `ssh user@<name>`. Tailscale needs the node key to be valid; disable key expiry for each server in the admin console, or a headless Pi locks you out after 180 days.
2. **Direct Ethernet link**, if enabled: plug a cable between your laptop and the Pi; see [services.md](./services.md#direct-ethernet-link).
3. **Local console:** plug in a monitor and keyboard.

Once you can log in, list the profiles and choose the one you want:

```bash
nmcli con show                 # profiles, and which are active
nmcli con up "<home profile>"  # switch to home wifi
nmcli device wifi list         # networks the Pi can see right now
```

If the Pi is on a phone hotspot and stays there after home wifi returns, `nmcli con up "<home profile>"` over Tailscale moves it back. This is expected behavior, described next.

## How the Pi picks a network

- NetworkManager's `autoconnect-priority` chooses among saved networks that are **in range**. It knows nothing about whether the network has internet. With home wifi up and the ISP down, the Pi stays on home wifi and does not try the hotspot.
- NetworkManager's documentation says autoconnect "never replaces or competes with an already active profile". A Pi on the hotspot therefore probably stays there when home wifi comes back, though some bug reports describe priority being ignored. This has not been tested on these Pis.
- There is no switch-back automation, deliberately: it would be code with no current use. If one is needed later, the two usual shapes are a NetworkManager **dispatcher script** (an executable file in `/etc/NetworkManager/dispatcher.d/`, owned by root and not writable by others, run with the interface name and an event such as `up` or `down`) or a systemd timer that runs `nmcli device wifi rescan` and `nmcli con up`. Write and test it on the Pi when there is a real need.
- The direct Ethernet link is a static profile with no gateway, so it is up whenever the cable is in, alongside wifi.

## Rules for changing network config

- Never change the connection Ansible is using without a way back in (Tailscale or ethernet).
- Always `--check --diff` first.
- **Planned:** apply with a built-in revert (`netplan try`, or a timed `nmcli` revert) so a bad change undoes itself.

## Who owns the config

**Planned:** cloud-init (Raspberry Pi Imager, Ubuntu) configures a machine once at first boot. After that, Ansible owns networking through each host's `host_vars`, and a base role tells cloud-init to stop managing network config. Ansible never edits `/etc/netplan/90-NM-*.yaml`, which NetworkManager generates. Ubuntu Server renders netplan with systemd-networkd, not NetworkManager. The decision between netplan and `nmcli` waits on the spike below.

### Spike on pi5 (run by hand; nothing in the repo is involved)

pi5 is not serving anything, so this is safe. Keep a monitor handy or stay connected over ethernet.

1. `sudo cp /etc/netplan/90-NM-*.yaml ~/netplan-backup/` (keep copies).
2. Write a test file such as `/etc/netplan/60-test.yaml` for `wlan0` with your SSID, then run `sudo netplan try`. Do not press Enter on the confirmation prompt.
3. **Pass 1:** the change was rolled back after the timeout.
4. Run `sudo netplan try` again and confirm; run `nmcli con show`. **Pass 2:** exactly one profile per interface or SSID, with no duplicates next to the `netplan-*` ones.
5. Remove the test file and run `sudo netplan apply` to return to the starting state.

If either pass fails, the plan falls back to `nmcli` with per-host profile names.
