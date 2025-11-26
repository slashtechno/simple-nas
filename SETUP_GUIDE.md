# Pi NAS Setup Guide
## Immich (Photos) + Copyparty (Files) + Gitea (Git) + Tailscale

Manual setup guide prioritizing understanding over automation. Works on any Linux system with Docker.

---

## Part 1: System Setup

### 1.1 Verify 64-bit OS

```bash
dpkg --print-architecture
uname -m
```

Must show `arm64` or `amd64`. If you see `armhf` or `armv7l`, your OS is 32-bit. **Immich requires 64-bit** - reflash with Raspberry Pi OS Lite 64-bit.

### 1.2 Install Docker (Official Method)

```bash
# Install prerequisites
sudo apt update && sudo apt upgrade -y
sudo apt install -y ca-certificates curl gnupg lsb-release git vim jq

# Add Docker's GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/debian/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Add Docker repository
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Enable and start Docker
sudo systemctl enable --now docker
sudo usermod -aG docker $(whoami)

# Log out and back in for group changes to take effect
```

Test Docker:
```bash
docker run --rm hello-world
docker compose version
```

---

## Part 2: Storage Setup

### 2.1 Identify Drives

```bash
sudo lsblk -o NAME,FSTYPE,LABEL,UUID,MOUNTPOINT,SIZE -f
sudo blkid
```

### 2.2 Format Drives (if new)

**WARNING: This destroys all data on the drive.**

```bash
# Replace sdX with your actual drive (e.g., sda, sdb)
sudo wipefs -a /dev/sdX
sudo parted /dev/sdX --script mklabel gpt mkpart primary ext4 0% 100%
sudo mkfs.ext4 -L primary /dev/sdX1
```

### 2.3 Add to fstab

After formatting, get new UUIDs and add to fstab:

```bash
SDA=/dev/sda1  # Replace with your actual partition
SDB=/dev/sdb1  # Replace with your actual partition

SDA_UUID=$(sudo blkid -s UUID -o value $SDA)
SDB_UUID=$(sudo blkid -s UUID -o value $SDB)

# Remove old entries (if any)
sudo sed -i '\|/mnt/t7|d;\|/mnt/backup|d' /etc/fstab

# Add new entries
printf "UUID=%s /mnt/t7 ext4 defaults,nofail 0 2\nUUID=%s /mnt/backup ext4 defaults,nofail 0 2\n" \
  "$SDA_UUID" "$SDB_UUID" | sudo tee -a /etc/fstab

# Create mount points and mount
sudo mkdir -p /mnt/t7 /mnt/backup
sudo mount -a
sudo chown $(whoami):$(whoami) /mnt/t7 /mnt/backup
```

Verify:
```bash
df -h | grep mnt
```

### 2.4 Create Directory Structure

**Create BEFORE starting Docker to avoid permission issues:**

```bash
# Main directories
mkdir -p /mnt/t7/{docker,photos,files,backups}
mkdir -p /mnt/t7/docker/{immich_postgres,copyparty_config,gitea}
mkdir -p /mnt/backup/{restic-repo,logs}

# Set Postgres permissions (runs as UID 999)
sudo chown -R 999:999 /mnt/t7/docker/immich_postgres
sudo chmod 700 /mnt/t7/docker/immich_postgres
```

---

## Part 3: Tailscale Setup

### 3.1 Install Tailscale

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up
```

Follow the login link.

### 3.2 Enable Funnel (After Caddy Starts)

**Important:** Enable Funnel AFTER starting Caddy in Part 5, not now. Skip this step for now and return to it after Part 5.1.

**Funnel only supports ports 443, 8443, 10000.** We use Caddy on port 443 to route all services.

```bash
# Run this AFTER docker compose up in Part 5.1
sudo tailscale funnel --bg --https=443 http://127.0.0.1:443
```

### 3.3 Get Your Domain

```bash
tailscale funnel status
```

Save your hostname: `your-machine.user-xxxxx.ts.net`

---

## Part 4: Configuration Files

### 4.1 Create Working Directory

**CRITICAL: All `docker compose` commands must run from this directory.**

```bash
mkdir -p ~/nas-docker
cd ~/nas-docker
```

### 4.2 Create Central .env File

Generate database password:
```bash
openssl rand -base64 32
```

Create `.env` with ALL configuration in one place:
```bash
nano .env
```

Paste (replace values as needed):
```bash
# Database
IMMICH_DB_PASSWORD=<paste-generated-password-here>

# Timezone
TIMEZONE=America/New_York

# Paths
UPLOAD_LOCATION=/mnt/t7/photos
DB_DATA_LOCATION=/mnt/t7/docker/immich_postgres
FILES_DIR=/mnt/t7/files
COPYPARTY_CONFIG=/mnt/t7/docker/copyparty_config
GITEA_DATA=/mnt/t7/docker/gitea

# Tailscale Domain (from Part 3.3)
TAILSCALE_DOMAIN=your-machine.user-xxxxx.ts.net

# Copyparty Authentication (optional - leave blank for no auth)
COPYPARTY_USER=
COPYPARTY_PASS=

# Gitea Configuration
GITEA__server__ROOT_URL=https://${TAILSCALE_DOMAIN}/git/
GITEA__server__DOMAIN=${TAILSCALE_DOMAIN}
GITEA__server__SSH_DOMAIN=${TAILSCALE_DOMAIN}
GITEA__server__SSH_PORT=2222
GITEA__database__DB_TYPE=sqlite3
GITEA__database__PATH=/data/gitea/gitea.db
```

Secure it:
```bash
chmod 600 .env
```

### 4.3 Create docker-compose.yml

```bash
cd ~/nas-docker
nano docker-compose.yml
```

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
      - ${UPLOAD_LOCATION}:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    environment:
      DB_HOSTNAME: immich_postgres
      DB_USERNAME: immich
      DB_PASSWORD: ${IMMICH_DB_PASSWORD}
      DB_DATABASE_NAME: immich
      TZ: ${TIMEZONE}
    networks:
      - services
    depends_on:
      - immich_postgres
      - immich_redis
    env_file:
      - .env

  immich_microservices:
    image: ghcr.io/immich-app/immich-server:release
    container_name: immich_microservices
    restart: unless-stopped
    command: ['start.sh', 'microservices']
    volumes:
      - ${UPLOAD_LOCATION}:/usr/src/app/upload
      - /etc/localtime:/etc/localtime:ro
    environment:
      DB_HOSTNAME: immich_postgres
      DB_USERNAME: immich
      DB_PASSWORD: ${IMMICH_DB_PASSWORD}
      DB_DATABASE_NAME: immich
      TZ: ${TIMEZONE}
    networks:
      - services
    depends_on:
      - immich_postgres
      - immich_redis
    env_file:
      - .env

  immich_machine_learning:
    image: ghcr.io/immich-app/immich-machine-learning:release
    container_name: immich_machine_learning
    restart: unless-stopped
    volumes:
      - ./immich_model_cache:/cache
      - /etc/localtime:/etc/localtime:ro
    environment:
      TZ: ${TIMEZONE}
    networks:
      - services
    env_file:
      - .env

  immich_postgres:
    image: tensorchord/pgvecto-rs:pg14-v0.2.0
    container_name: immich_postgres
    restart: unless-stopped
    environment:
      POSTGRES_USER: immich
      POSTGRES_PASSWORD: ${IMMICH_DB_PASSWORD}
      POSTGRES_DB: immich
      POSTGRES_INITDB_ARGS: '-U immich'
    volumes:
      - ${DB_DATA_LOCATION}:/var/lib/postgresql/data
    networks:
      - services
    env_file:
      - .env

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
      - ${FILES_DIR}:/files:rw
      - ${COPYPARTY_CONFIG}:/cfg:rw
    environment:
      TZ: ${TIMEZONE}
    command:
      - -v
      - /files::r:rw,ed,dd:c,g
      - -e2dsa
      - -e2ts
      - ${COPYPARTY_USER:+-a}
      - ${COPYPARTY_USER:+${COPYPARTY_USER}:${COPYPARTY_PASS}}
    networks:
      - services
    env_file:
      - .env

  gitea:
    image: gitea/gitea:latest
    container_name: gitea
    restart: unless-stopped
    volumes:
      - ${GITEA_DATA}:/data
      - /etc/localtime:/etc/localtime:ro
    environment:
      USER_UID: 1000
      USER_GID: 1000
      GITEA__server__ROOT_URL: ${GITEA__server__ROOT_URL}
      GITEA__server__DOMAIN: ${GITEA__server__DOMAIN}
      GITEA__server__SSH_DOMAIN: ${GITEA__server__SSH_DOMAIN}
      GITEA__server__SSH_PORT: ${GITEA__server__SSH_PORT}
      GITEA__database__DB_TYPE: ${GITEA__database__DB_TYPE}
      GITEA__database__PATH: ${GITEA__database__PATH}
    ports:
      - "2222:22"
    networks:
      - services
    env_file:
      - .env
```

### 4.4 Create Caddyfile

```bash
nano Caddyfile
```

Replace `your-machine.user-xxxxx.ts.net` with your actual Tailscale domain from Part 3.3:

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

Replace `your-machine.user-xxxxx.ts.net` with your actual Tailscale domain from Part 3.3.

---

## Part 5: Start Services

### 5.1 Start All Services

**First, make sure port 443 is free:**

```bash
# Check what's using port 443
sudo lsof -i :443

# If something is there, stop it:
sudo systemctl stop nginx     # or apache2, or whatever is running
sudo systemctl disable nginx  # prevent auto-start
```

**Now start Docker services:**

```bash
cd ~/nas-docker
docker compose up -d
```

Wait 60 seconds for Postgres to initialize:
```bash
docker compose logs immich_postgres | grep "ready to accept connections"
```

### 5.2 Enable Tailscale Funnel

Now that Caddy is running on port 443, enable Funnel:

```bash
sudo tailscale funnel --bg --https=443 http://127.0.0.1:443
```

Verify:
```bash
tailscale funnel status
```

### 5.3 Check Status

```bash
docker compose ps
```

All services should show "Up" status.

Test locally:
```bash
curl http://localhost/immich
curl http://localhost/copyparty  
curl http://localhost/git
```

---

## Part 6: Initial Configuration

### Copyparty Authentication (Optional)

If you want to require login for uploading/editing files, add credentials to `.env`:

```bash
cd ~/nas-docker
nano .env
```

Set these values:
```bash
COPYPARTY_USER=your-username
COPYPARTY_PASS=your-password
```

Then restart Copyparty:
```bash
docker compose restart copyparty
```

**How it works:**
- Without authentication: Anyone can read and write
- With authentication: Anyone can read, only logged-in users can write/edit/delete

### Initial Service Setup

Open in browser:

1. **Immich**: `https://your-domain.ts.net/immich` → Create admin account
2. **Gitea**: `https://your-domain.ts.net/git` → Click "Install Gitea"
3. **Copyparty**: `https://your-domain.ts.net/copyparty` → Ready to use

Test Gitea SSH (local only):
```bash
ssh -p 2222 git@localhost
# Should output: "You've successfully authenticated"
```

---

## Part 7: Backups

See [BACKUPS.md](./BACKUPS.md) for complete backup procedures with restic.

**Quick summary:**
- Local backups: Everything to HDD daily
- Cloud backups: Configs + databases to Google Drive weekly
- Retention: 7 daily + 4 weekly + 1 monthly (local), 12 weekly + 6 monthly (cloud)

---

## Part 8: Useful Commands

```bash
# View logs
cd ~/nas-docker
docker compose logs immich_server -f
docker compose logs caddy -f

# Restart all services
docker compose restart

# Update all images
docker compose pull
docker compose up -d

# Stop everything
docker compose down

# Check disk usage
df -h
du -sh /mnt/t7/*
```

---

## What to Save in Password Manager

**Critical - Save These:**

1. **Immich admin username/password** (created during setup)
2. **Gitea admin username/password** (created during setup)
3. **Restic password** (from `~/.restic-password` - see BACKUPS.md)
4. **Immich DB password** (from `~/nas-docker/.env`)

**Backup These Files (encrypted):**

5. `~/nas-docker/.env` - All configuration in one place
6. `~/nas-docker/docker-compose.yml`
7. `~/nas-docker/Caddyfile`
8. `~/.config/rclone/rclone.conf` - Google Drive credentials

**Note These (not secret):**
- Tailscale domain: `your-machine.ts.net`
- Restic repos: `/mnt/backup/restic-repo` and `rclone:gdrive-nas:/pi-nas-backups`

---

## Troubleshooting

**Services won't start:**
```bash
cd ~/nas-docker
docker compose logs
docker compose ps
```

**Port 443 already in use:**
```bash
# Find what's using it
sudo lsof -i :443

# Stop conflicting service
sudo systemctl stop nginx  # or apache2
sudo systemctl disable nginx

# Or disable Funnel temporarily
sudo tailscale funnel --bg --https=443 off

# Restart Caddy
docker compose restart caddy

# Re-enable Funnel
sudo tailscale funnel --bg --https=443 http://127.0.0.1:443
```

**Can't reach services:**
```bash
# Test internal ports
curl http://localhost:3001  # Immich
curl http://localhost:3923  # Copyparty
curl http://localhost:3000  # Gitea

# Check Caddy routing
docker compose logs caddy
```

**Postgres permission denied:**
```bash
sudo chown -R 999:999 /mnt/t7/docker/immich_postgres
sudo chmod 700 /mnt/t7/docker/immich_postgres
cd ~/nas-docker
docker compose restart immich_postgres
```

**Disk full:**
```bash
# Find largest directories
du -sh /mnt/t7/* | sort -h

# Clean Docker cache
docker system prune -a

# Clean old backups (see BACKUPS.md)
```

---

## Next Steps

1. Install Immich mobile app → Point to `https://your-domain.ts.net/immich`
2. Test Git workflows with Gitea
3. Set up backups (see BACKUPS.md)
4. Share Tailscale domain for remote access

---

## References

- [Immich Documentation](https://immich.app/docs)
- [Gitea Documentation](https://docs.gitea.com)
- [Restic Documentation](https://restic.readthedocs.io)
- [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)