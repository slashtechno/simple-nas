# Pi NAS Setup Guide
## Immich (Photos) + Copyparty (Files) + Gitea (Git) + Tailscale

This is a manual setup guide for self-hosted NAS on any Linux system with Docker. It prioritizes understanding and troubleshooting over automation.

---

## Prerequisites

- Linux system (Raspberry Pi 4 recommended, ARM64/x86_64)
- 64-bit OS (required for Immich)
- 2+ external drives (USB SSD or SATA)
- Docker and Docker Compose installed
- SSH access

---

## Part 1: System Setup

### 1.1 Verify 64-bit OS

```bash
dpkg --print-architecture
uname -m
```

Should show `arm64` or `amd64`, not `armhf` or `armv7l`.

**If you see `armv7l`**: Your OS is 32-bit. Immich requires 64-bit. You must flash a 64-bit OS image (Raspberry Pi OS Lite 64-bit). This is a show-stopper—32-bit won't work.

### 1.2 Install Essentials

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git curl vim jq docker.io docker-compose-plugin
sudo usermod -aG docker $(whoami)
```

Log out and back in for Docker permissions.

### 1.3 Configure Firewall

```bash
sudo apt install -y ufw
sudo ufw allow 22/tcp       # SSH
sudo ufw allow 80/tcp       # HTTP (Caddy)
sudo ufw allow 443/tcp      # HTTPS (Caddy)
sudo ufw allow 2222/tcp     # Gitea SSH
sudo ufw --force enable
```

---

## Part 2: Storage Setup

### 2.1 Identify Drives

```bash
sudo blkid
```

Note the UUIDs for your external drives (not your boot drive).

### 2.2 Format Drives (if new)

Be careful—verify device names:

```bash
sudo mkfs.ext4 -L primary /dev/sda1
sudo mkfs.ext4 -L backup /dev/sdb1
```

### 2.3 Mount at Boot

Edit fstab:

```bash
sudo nano /etc/fstab
```

Add (replace UUIDs with your actual ones):

```
UUID=your-t7-uuid /mnt/t7 ext4 defaults,nofail 0 2
UUID=your-backup-uuid /mnt/backup ext4 defaults,nofail 0 2
```

Test:

```bash
sudo mount -a
df -h
```

### 2.4 Set Permissions

```bash
sudo chown $(whoami):$(whoami) /mnt/t7 /mnt/backup
chmod 755 /mnt/t7 /mnt/backup
```

**Note**: Docker containers may run as non-root users. Verify file permissions after starting services—you may need to adjust ownership for container-specific directories (e.g., `/mnt/t7/docker/` subdirs).

### 2.5 Create Directories with Proper Permissions

Create directories **before** starting Docker—this prevents permission issues:

```bash
mkdir -p /mnt/t7/{docker,photos,files,backups}
mkdir -p /mnt/t7/docker/{immich_postgres,copyparty_config,gitea}
mkdir -p /mnt/backup/local-backups
```

Set Docker container-specific ownership:

```bash
# Immich Postgres (runs as postgres user inside container)
sudo chown 999:999 /mnt/t7/docker/immich_postgres
sudo chmod 700 /mnt/t7/docker/immich_postgres

# Copyparty and Gitea (usually run as root inside container, but verify)
sudo chown root:root /mnt/t7/docker/copyparty_config /mnt/t7/docker/gitea
sudo chmod 755 /mnt/t7/docker/{copyparty_config,gitea}
```

If containers still can't write, check logs and adjust:
```bash
docker compose logs immich_postgres
sudo chown -R 999:999 /mnt/t7/docker/immich_postgres  # Re-apply if needed
```

---

## Part 3: Tailscale Setup

### 3.1 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Follow the login link.

### 3.2 Enable Funnel

**Important**: Funnel only supports ports **443, 8443, 10000**. We route all services (Immich, Copyparty, Gitea) through Caddy on port 443 using path-based routing (`/immich/*`, `/copyparty/*`, `/git/*`).

```bash
sudo tailscale funnel --https=443 http://127.0.0.1:443
```

This exposes Caddy's HTTPS port to the internet. Caddy handles routing to internal services.

### 3.3 Get Your Domain

```bash
tailscale funnel status
```

The output shows your hostname: `your-machine.user-xxxxx.ts.net`

Save this for the Caddyfile setup below.

---

## Part 4: Docker Compose Setup

### 4.1 Create Central Config

Create `/mnt/t7/.env` (shared by all services):

```bash
nano /mnt/t7/.env
```

Add:

```
IMMICH_DB_PASSWORD=$(openssl rand -base64 32)
TIMEZONE=America/New_York
```

Generate the password:

```bash
openssl rand -base64 32
```

Secure it (contains secrets):

```bash
chmod 600 /mnt/t7/.env
```

### 4.2 Create Symlinks to Services

For each service directory, symlink to the central `.env`:

```bash
ln -s /mnt/t7/.env /mnt/t7/docker/.env
```

Later, each service's `docker-compose.yml` will `env_file: ../.env`.

### 4.3 Create docker-compose.yml

**Important**: Caddy uses relative path `./Caddyfile`, so you **must** `cd` to the working directory before running `docker compose`:

```bash
mkdir -p ~/nas-docker
cd ~/nas-docker  # This is CRITICAL—all docker compose commands must run from here
nano docker-compose.yml
```

Paste:

```yaml
version: "3.8"

networks:
  services:
    driver: bridge

volumes:
  caddy_data:
  caddy_config:

services:
  caddy:
    image: caddy:latest
    container_name: caddy
    restart: unless-stopped
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - services
    env_file: /mnt/t7/.env
    depends_on:
      - immich_server
      - copyparty
      - gitea

  immich_server:
    image: ghcr.io/immich-app/immich-server:release
    container_name: immich_server
    restart: unless-stopped
    command: ['start.sh', 'immich']
    volumes:
      - /mnt/t7/photos:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    environment:
      DB_HOSTNAME: immich_postgres
      DB_USERNAME: immich
      DB_PASSWORD: ${IMMICH_DB_PASSWORD}
      DB_NAME: immich
      TZ: ${TIMEZONE}
    networks:
      - services
    depends_on:
      - immich_postgres
      - immich_redis
    env_file: /mnt/t7/.env

  immich_microservices:
    image: ghcr.io/immich-app/immich-server:release
    container_name: immich_microservices
    restart: unless-stopped
    command: ['start.sh', 'microservices']
    volumes:
      - /mnt/t7/photos:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    environment:
      DB_HOSTNAME: immich_postgres
      DB_USERNAME: immich
      DB_PASSWORD: ${IMMICH_DB_PASSWORD}
      DB_NAME: immich
      TZ: ${TIMEZONE}
    networks:
      - services
    depends_on:
      - immich_postgres
      - immich_redis
    env_file: /mnt/t7/.env

  immich_machine_learning:
    image: ghcr.io/immich-app/immich-machine-learning:release-arm64  # VERIFY THIS MATCHES YOUR ARCHITECTURE
    container_name: immich_machine_learning
    restart: unless-stopped
    volumes:
      - ./immich_model_cache:/cache
      - /etc/localtime:/etc/localtime:ro
    environment:
      TZ: ${TIMEZONE}
    networks:
      - services
    env_file: /mnt/t7/.env

  immich_postgres:
    image: tensorchord/pgvecto-rs:pg14-v0.2.0
    container_name: immich_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: immich
      POSTGRES_PASSWORD: ${IMMICH_DB_PASSWORD}
      POSTGRES_DB: immich
      POSTGRES_INITDB_ARGS: "-c shared_preload_libraries=vectors"
    volumes:
      - /mnt/t7/docker/immich_postgres:/var/lib/postgresql/data
    networks:
      - services
    env_file: /mnt/t7/.env

  immich_redis:
    image: redis:7.2-alpine
    container_name: immich_redis
    restart: unless-stopped
    networks:
      - services

  copyparty:
    image: copyparty/ac
    container_name: copyparty
    restart: unless-stopped
    volumes:
      - /mnt/t7/files:/files:rw
      - /mnt/t7/docker/copyparty_config:/cfg:rw
    environment:
      TZ: ${TIMEZONE}
    command:
      - -v
      - /files::r:rw,ed,dd:c,g
      - -e2dsa
      - -e2ts
    networks:
      - services
    env_file: /mnt/t7/.env

  gitea:
    image: gitea/gitea:latest
    container_name: gitea
    restart: unless-stopped
    volumes:
      - /mnt/t7/docker/gitea:/data
      - /etc/localtime:/etc/localtime:ro
    environment:
      TZ: ${TIMEZONE}
      GITEA__server__ROOT_URL: http://localhost/git
      GITEA__server__DOMAIN: localhost
      GITEA__server__SSH_DOMAIN: localhost
      GITEA__server__SSH_PORT: 2222
      GITEA__database__DB_TYPE: sqlite3
      GITEA__database__PATH: /data/gitea.db
      GITEA__picture__ENABLE_FEDERATED_AVATAR: "false"
    ports:
      - "2222:22"
    networks:
      - services
    env_file: /mnt/t7/.env
```

### 4.4 Create Caddyfile

```bash
nano Caddyfile
```

Use your Tailscale domain from Part 3. `auto_https off` is safe here because Tailscale Funnel handles TLS:

```caddyfile
{
  auto_https off
}

your-machine.user-xxxxx.ts.net {
  handle /immich/* {
    reverse_proxy immich_server:3001
  }

  handle /copyparty/* {
    reverse_proxy copyparty:3923
  }

  handle /git/* {
    reverse_proxy gitea:3000
  }

  handle / {
    respond "NAS Ready"
  }
}
```

**Note**: Make sure the paths (`/immich/*`, `/copyparty/*`, `/git/*`) match where you access these services. Adjust if needed.

### 4.5 Verify Architecture Before Starting

Check your CPU architecture matches the ML image:

```bash
uname -m
```

- If `aarch64` or `arm64`: use `release-arm64` ✓
- If `x86_64`: change image to `ghcr.io/immich-app/immich-machine-learning:release-amd64`

Update the Immich machine learning image tag in `docker-compose.yml` if needed.

### 4.6 Start Services

**IMPORTANT**: Make sure you're in the `~/nas-docker` directory:

```bash
cd ~/nas-docker
docker compose up -d
docker ps
```

Wait 30 seconds, then verify:

```bash
curl http://localhost/immich
curl http://localhost/copyparty
curl http://localhost/git
```

---

## Part 5: Wait for Postgres to Initialize

Postgres needs ~30-60 seconds to create the database after first start:

```bash
docker compose logs immich_postgres
# Wait for: "database system is ready to accept connections"
```

Once ready, other services will auto-start. If they don't, restart them:

```bash
docker compose restart immich_server immich_microservices
```

---

## Part 6: Initial Configuration

Open in browser and follow each setup wizard:

1. **Immich**: `http://localhost/immich` → Create admin account
2. **Gitea**: `http://localhost/git` → Click "Install Gitea"
3. **Copyparty**: `http://localhost/copyparty` → No setup needed

Test Gitea SSH (use port 2222, not 22):

```bash
ssh -p 2222 git@localhost
```

Should output: `Hi there. You've successfully authenticated, but Gitea does not provide shell access.`

Note: Gitea SSH is only accessible locally on port 2222. For remote access over Tailscale, you'll need to configure an additional SSH reverse proxy or use HTTPS git URLs.

---

## Part 7: Remote Access

Visit your Tailscale domain from Part 3:

```
https://your-machine.user-xxxxx.ts.net/immich
https://your-machine.user-xxxxx.ts.net/copyparty
https://your-machine.user-xxxxx.ts.net/git
```

Tailscale handles HTTPS automatically.

---

## Part 8: Backups

Backups use **restic** for incremental, deduplicated backups with compression. See [BACKUPS.md](./BACKUPS.md) for complete procedures.

**Quick start:**

```bash
# 1. Install restic
sudo apt install -y restic

# 2. Create password file
openssl rand -base64 32 > ~/.restic-password
chmod 600 ~/.restic-password

# 3. Initialize local repository (HDD)
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo
restic init

# 4. Create daily backup script
cat > ~/backup-restic-local.sh << 'EOF'
#!/bin/bash
set -o pipefail
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo
LOG_FILE="/mnt/backup/logs/restic-local-$(date +%Y-%m-%d).log"
mkdir -p "$(dirname "$LOG_FILE")"
{
  echo "=== Local Backup: $(date) ==="
  restic backup /mnt/t7 \
    --exclude "/mnt/t7/immich_model_cache" \
    --exclude "/mnt/t7/**/.cache" \
    --tag daily --verbose
  [ $? -eq 0 ] && restic forget --keep-daily 7 --keep-weekly 4 --keep-monthly 1 --prune
  echo "=== Complete: $(date) ==="
} | tee -a "$LOG_FILE"
EOF

chmod +x ~/backup-restic-local.sh
~/backup-restic-local.sh  # Test first
```

Schedule it:

```bash
crontab -e
# Add: 0 2 * * * /home/$(whoami)/backup-restic-local.sh
```

### Quick Restore from Backup

If something breaks, restore the latest snapshot:

```bash
export RESTIC_PASSWORD_FILE=~/.restic-password
export RESTIC_REPOSITORY=/mnt/backup/restic-repo

# List snapshots
restic snapshots

# Restore everything to original paths
restic restore latest --target /

# Or restore specific directory
restic restore latest --include "/mnt/t7/docker/gitea" --target /
```

For cloud backups (Google Drive), Google Drive setup, complete restore procedures, and disaster recovery scenarios, see [BACKUPS.md](./BACKUPS.md).

---

## Part 9: Useful Commands

```bash
# View logs
docker compose logs immich_server -f
docker compose logs caddy -f

# Restart all services
docker compose restart

# Update all images
docker compose pull
docker compose up -d

# Check disk usage
df -h
du -sh /mnt/t7/*

# Stop everything
docker compose down
```

---

## Troubleshooting

**Services won't start:**
```bash
docker compose logs
```

**Can't connect to services:**
```bash
curl http://localhost:3001  # Immich internal
curl http://localhost:3923  # Copyparty internal
```

**Gitea SSH doesn't work:**
```bash
netstat -tlnp | grep 2222
ssh -v -p 2222 git@localhost
```

**Disk full:**
```bash
rm -rf ~/immich_model_cache/*
du -sh /mnt/t7/* | sort -h
```

---

## What to Save in Password Manager

Save these credentials **only**:

1. **Immich Admin Username/Password**
2. **Gitea Admin Username/Password**
3. **Restic Password** (from `~/.restic-password` on Pi)

Also note (not secret):
- Restic local repo: `/mnt/backup/restic-repo`
- Restic cloud repo: `rclone:gdrive-nas:/pi-nas-backups`

**Why?**
- Database password is already in restic backups (the entire `/mnt/t7/docker/immich_postgres` directory is backed up)
- Rclone config is already protected on Pi with restricted file permissions
- Tailscale domain and remote names are operational info, not secrets
- Keep `.env` file only on Pi (encrypted drive) or encrypted laptop backup, never in password manager

---

## Next Steps

1. Install [Immich mobile app](https://docs.immich.app/docs/features/mobile-app) and point to your Funnel domain
2. Test Git workflows with Gitea
3. Verify backups complete successfully
4. Share Tailscale domain with users who need remote access

---

## References

- [Immich docs](https://docs.immich.app)
- [Gitea docs](https://docs.gitea.com)
- [Caddy docs](https://caddyserver.com/docs)
- [Tailscale Funnel limits](https://tailscale.com/kb/1223/funnel) (ports 443, 8443, 10000 only)
- [Docker Compose reference](https://docs.docker.com/compose)
