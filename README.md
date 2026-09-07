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

For fast local transfers, the Pi's Ethernet port (idle — the Pi normally runs on wifi) can be cabled straight to a laptop, bypassing wifi entirely. Static IPs (not DHCP/auto-assigned), so the address never changes: Pi `eth0` = `10.10.20.1`, laptop = `10.10.20.2` — just the two of them, no room for anything else on that cable.

**Setup:**
1. Set `direct_link_enabled: true` in `vars.yml`, then deploy (`ansible-playbook site.yml --ask-vault-pass --tags network`). This configures the Pi's side automatically.
2. On the laptop, plug in the cable, then set a manual IP on that Ethernet connection:
   **macOS:** System Settings → Network → (the new Ethernet entry) → Details → TCP/IP → Configure IPv4: *Manually* → IP Address `10.10.20.2`, Subnet Mask `255.255.255.252`, Router: *(leave blank)*.
3. Visit `http://10.10.20.1:3923` for Copyparty directly over the cable.

<details>
<summary>Why static, and why the link can't leak onto the internet or collide with a VPN</summary>

- Static beats auto-assigned addressing here because an auto-assigned address changes every time and you'd need extra tooling just to find it. Static means the IP is always the same, so you can bookmark `http://10.10.20.1:3923` for Copyparty.
- Neither end is told about a gateway, so this link has no path to the internet at all — plugging in can't accidentally reroute general browsing traffic through the Pi, even though wired connections are normally preferred over wifi.
- Collision risk with a VPN: `10.10.20.1`/`10.10.20.2` is a `/30` — a block of only 4 addresses, 2 of which are usable (the network/broadcast addresses at the ends aren't). In practice: a VPN route only conflicts if it covers this *exact* tiny 4-address block, not just "some `10.x` address somewhere." Common VPN defaults like `10.8.0.0/24` (OpenVPN, 256 addresses) or home routers like `192.168.0.1`/`192.168.1.1` live nowhere near `10.10.20.0`–`10.10.20.3`, so there's nothing to overlap with.

</details>
