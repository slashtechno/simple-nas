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

# Migrate from old ~/simple-nas/ monolithic setup
ansible-playbook migrate.yml --ask-vault-pass
```

See `ansible/README.md` for full details.

---

## Backups

Fully automated via Ansible — cron jobs are created on the Pi automatically.

- Daily @ 2 AM: full `/mnt/t7` → local HDD (restic)
- Sunday @ 4 AM: critical paths → Google Drive (rclone + restic)

See [BACKUPS.md](./BACKUPS.md) for restore instructions.
