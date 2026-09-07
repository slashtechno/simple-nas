# Simple NAS

A self-hosted NAS on Raspberry Pi 4 managed by Ansible. Two drives, a Pi, and a handful of Docker services.

- **Immich** — photo library (Google Photos alternative)
- **Copyparty** — file sharing
- **Gitea** — Git server
- **Garage** — S3-compatible object storage
- **Cloudflare Tunnel** — public hostnames without port forwarding
- **Tailscale** — private remote access

```
Raspberry Pi 4
├─ 64GB microSD    (OS)
├─ 500GB SSD       (/mnt/t7  — primary data)
└─ 500GB HDD       (/mnt/backup — backups)

Internet → Cloudflare Tunnel
  ├─ immich.example.com    → Immich      (:2283)
  ├─ gitea.example.com     → Gitea       (:3000)
  ├─ copyparty.example.com → Copyparty   (:3923)
  └─ s3.example.com        → Garage S3   (:3900)
```

---

## Deploy

```bash
cd ansible/

# First time only
pip3 install ansible
ansible-galaxy install -r requirements.yml
cp inventory/hosts.yml.example inventory/hosts.yml   # add Pi's IP
cp group_vars/nas/vars.yml.example group_vars/nas/vars.yml
cp group_vars/nas/vault.yml.example group_vars/nas/vault.yml
# fill in vault.yml, then:
ansible-vault encrypt group_vars/nas/vault.yml

# Deploy everything
ansible-playbook site.yml --ask-vault-pass
```

See `ansible/README.md` for full details.

---

## Backups

Fully automated via Ansible — cron jobs are created on the Pi automatically.

- Daily @ 2 AM: full `/mnt/t7` → local HDD (restic)
- Sunday @ 4 AM: critical paths → Google Drive (rclone + restic)

See [BACKUPS.md](./BACKUPS.md) for restore instructions.

---

## Direct Ethernet link

For fast local transfers, the Pi's Ethernet port (idle — the Pi normally runs on wifi) can be cabled straight to a laptop, bypassing wifi entirely. The Pi's side is a fixed static IP (`10.10.20.1`); the laptop's IP (`10.10.20.2`) is handed out automatically by a scoped DHCP server on that port — just the two of them, no room for anything else on that cable.

**Setup:**
1. Set `direct_link_enabled: true` in `vars.yml`, then deploy (`ansible-playbook site.yml --ask-vault-pass --tags network`). This configures both the static IP and the auto-assign DHCP on the Pi's side.
2. Plug the cable into the Pi and the laptop — the laptop picks up `10.10.20.2` automatically, no manual TCP/IP config needed.
3. Visit `http://10.10.20.1:3923` for Copyparty directly over the cable.

<details>
<summary>Why the link can't leak onto the internet or collide with a VPN</summary>

- The Pi's IP is static so it's always the same to bookmark (`http://10.10.20.1:3923`). The laptop's IP is auto-assigned via a `dnsmasq` instance scoped strictly to `eth0` — DHCP only, its DNS-proxy function is disabled (`port=0`), and it never hands out a gateway or DNS servers, so it can't route anything beyond the two ends of the cable.
- Neither end is told about a gateway, so this link has no path to the internet at all — plugging in can't accidentally reroute general browsing traffic through the Pi, even though wired connections are normally preferred over wifi.
- Collision risk with a VPN: `10.10.20.1`/`10.10.20.2` is a `/30` — a block of only 4 addresses, 2 of which are usable (the network/broadcast addresses at the ends aren't). In practice: a VPN route only conflicts if it covers this *exact* tiny 4-address block, not just "some `10.x` address somewhere." Common VPN defaults like `10.8.0.0/24` (OpenVPN, 256 addresses) or home routers like `192.168.0.1`/`192.168.1.1` live nowhere near `10.10.20.0`–`10.10.20.3`, so there's nothing to overlap with.
- Copyparty encrypts even this direct connection: it ships a built-in self-signed cert and auto-detects HTTPS vs HTTP on the same port, no config needed (`https://10.10.20.1:3923` works out of the box — expect a browser cert warning, since the cert is copyparty's public default, not unique to your instance).

</details>
