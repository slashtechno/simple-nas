# Pi NAS: Self-Hosted Photo + File + Git Server

A self-hosted NAS on Raspberry Pi 4 with:
- **Immich**: Photo library (like Google Photos)
- **Copyparty**: File sharing
- **Gitea**: Git server (like GitHub)
- **Tailscale**: Secure remote access over WiFi

---

## Design

```
Raspberry Pi 4 (headless, WiFi only)
├─ 64GB microSD (OS boot)
├─ 500GB SSD (/mnt/t7) - primary data
└─ 500GB HDD (/mnt/backup) - full backups

Internet → Tailscale Funnel (443) → Caddy (reverse proxy)
├─ /immich → Immich (photos)
├─ /copyparty → Copyparty (files)
└─ /git → Gitea (repos)
```

**Why this design?**
- Single-user home lab (no multi-tenancy)
- Works over WiFi (no Ethernet needed)
- All data encrypted at rest via Tailscale tunnel
- Backups: local (daily) + cloud (weekly)
- Storage: SSD for speed, HDD for rotation

---

## Backup Strategy

**Local (daily)** → 500GB HDD
- Full backup: all photos, DBs, configs, files
- Keeps 2-3 rotating copies
- Space-constrained (can't fit 2 full backups simultaneously)

**Cloud (weekly)** → Google Drive
- Critical only: databases + configs (highly compressed)
- Incremental via restic + rclone
- Disaster recovery (SSD + HDD both fail)

---

## Documentation

- **[SETUP_GUIDE.md](./SETUP_GUIDE.md)** - Complete installation & operations
- **[BACKUPS.md](./BACKUPS.md)** - Backup/restore procedures & space planning

---

## Quick Restore

If data is corrupted, restore from latest backup (usually within 24 hours):

```bash
BACKUP=$(ls -d /mnt/backup/daily-* | sort -r | head -1)

# Database
docker compose stop immich_server immich_microservices
zcat "$BACKUP/immich-db.sql.gz" | docker exec -i immich_postgres psql -U immich
docker compose start immich_server immich_microservices

# All other data
docker compose stop gitea && rm -rf /mnt/t7/docker/gitea && \
  tar -xzf "$BACKUP/gitea.tar.gz" -C / && docker compose start gitea
rsync -av "$BACKUP/photos/" /mnt/t7/photos/
```

See [BACKUPS.md](./BACKUPS.md) for complete restore procedures.
