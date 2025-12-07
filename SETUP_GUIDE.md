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

### 3.2 Enable Funnel (optional for Copyparty)

With Cloudflared handling public hostnames for most services, you generally do not need the Tailscale Funnel. If you still want a Tailscale-hosted URL for Copyparty in addition to its Cloudflare hostname, enable Funnel after services are up.

**Funnel only supports ports 443, 8443, 10000.** Use the Funnel to forward HTTPS to the local Copyparty port (3923):

```bash
# Optional: enable Funnel to expose Copyparty via Tailscale
sudo tailscale funnel --bg --https=443 http://127.0.0.1:3923
```

Use `tailscale funnel status` to retrieve the public Tailscale-hosted URL when enabled.

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

Copy the sample environment file and customize it (assuming you cloned the repo to `~/simple-nas`):
```bash
cp ~/simple-nas/.env.example .env
nano .env
```

**Required changes:**
- Replace `IMMICH_DB_PASSWORD=your-generated-password-here` with the password you just generated
- Update `TIMEZONE` to your timezone (run `timedatectl list-timezones` to see options)
- Update `TAILSCALE_DOMAIN` with your Tailscale domain from Part 3.3
- Set `COPYPARTY_USER` and `COPYPARTY_PASS` to your desired credentials

Secure it:
```bash
chmod 600 .env
```

### 4.3 Create docker-compose.yml

**CRITICAL: All `docker compose` commands must run from this directory.**

```bash
mkdir -p ~/nas-docker
cd ~/nas-docker
```

Copy the `docker-compose.yml` file from the project root (assuming `~/simple-nas`):

```bash
cp ~/simple-nas/docker-compose.yml .
```

### 4.4 Cloudflared Tunnel (replaces Caddy)

This setup uses a containerized Cloudflare Tunnel (`cloudflared`) to expose each service on its own hostname instead of path-based proxying.

Key points:
- Each service is routed by hostname (e.g. `immich.example.com`) to the internal container address.
- Runtime files and tunnel credentials are generated at init time; a template is tracked in the repo: [`cloudflared/config.yml.template`](cloudflared/config.yml.template:1).
- You still expose Copyparty via Tailscale Funnel optionally (see Part 5.2) while Cloudflare also provides a public hostname.

Required environment variables (add to your `.env`):
- `CF_API_TOKEN` — Cloudflare API token with DNS and Tunnel permissions
- `CF_ZONE_ID` — Cloudflare Zone ID for your domain
- `CF_TUNNEL_NAME` — name for the tunnel (default: `pi-nas-tunnel`)
- `HOSTNAMES` — comma-separated hostnames, e.g. `immich.example.com,gitea.example.com,copyparty.example.com`

Init and runtime (one-time + normal start):
```bash
# run the init script (one-time)
# the script can be run via `sh` or `bash` — no need to make it executable beforehand
sh ./cloudflared/create_tunnel.sh

# copy .env.example and add CF_* vars and HOSTNAMES (if you haven't already configured .env)
cp .env.example .env
nano .env

# start the stack — the init job will create or reuse a tunnel and render /etc/cloudflared/config.yml
docker compose up -d
```

After init, cloudflared will map hostnames to internal services:
- Immich -> `http://immich_server:2283`
- Gitea  -> `http://gitea:3000`
- Copyparty -> `http://copyparty:3923`

Local access to services (unchanged):
- Immich: `http://localhost:2283`
- Gitea: `http://localhost:3000`
- Copyparty: `http://localhost:3923`

---

## Part 5: Start Services

### 5.1 Start All Services

**First, make sure port 3923 is free:**

```bash
# Check what's using port 3923
sudo lsof -i :3923

# If something is there, stop it:
sudo systemctl stop nginx     # or apache2, or whatever is running
sudo systemctl disable nginx  # prevent auto-start
```

**Now start Docker services:**

```bash
cd ~/nas-docker
docker compose up -d
```


### 5.2 Tailscale Funnel and Copyparty (optional)

Cloudflared provides public hostnames for your services; the Funnel is optional. If you want to expose Copyparty via Tailscale in addition to its Cloudflare hostname, enable Funnel after services are up:

```bash
# Optional: forward public HTTPS to local Copyparty port (3923)
sudo tailscale funnel --bg --https=443 http://127.0.0.1:3923
```

Verify:

```bash
tailscale funnel status
```

The funnel will print the public URL (e.g. `your-machine.user-xxxxx.ts.net`). To disable Funnel:

```bash
sudo tailscale funnel --https=443 off
```

Notes:
- Use Cloudflared hostnames (see Part 4.4 HOSTNAMES) for primary public access.
- Keep Funnel enabled only while you need the Tailscale-hosted URL for Copyparty.

### 5.3 Check Status

```bash
docker compose ps
```

All services should show "Up" status.

Test locally:
```bash
curl http://localhost:2283  # Immich
curl http://localhost:3923  # Copyparty
curl http://localhost:3000  # Gitea
```

---

## Part 6: Initial Configuration

### Copyparty Authentication (Required)

Authentication is always required for all operations, including reading files. Only authenticated users can access the file server. Set the username and password in the .env file as COPYPARTY_USER and COPYPARTY_PASS.

**How it works:**
- Anonymous users cannot access anything
- Authenticated users have full access: read, write, edit, delete, etc.

### Initial Service Setup

Open in browser:

1. **Immich**: `http://your-tailscale-ip:2283` → Create admin account
2. **Gitea**: `http://your-tailscale-ip:3000` → Click "Install Gitea"
3. **Copyparty**: `http://your-tailscale-ip:3923` → Ready to use

Via public Funnel (after enabling in 5.2):
- **Immich**: `https://your-machine.ts.net/immich`
- **Gitea**: `https://your-machine.ts.net/gitea`
- **Copyparty**: `https://your-machine.ts.net/copyparty`

Test Gitea SSH (local only):
```bash
ssh -p 2222 git@localhost
# Should output: "You've successfully authenticated"
```

---

## Part 7: Backups

See [`BACKUPS.md`](BACKUPS.md:1) for backup instructions.

---

## Part 8: Useful Commands

```bash
# View logs
cd ~/nas-docker
docker compose logs immich_server -f
docker compose logs copyparty -f

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
7. `~/nas-docker/cloudflared/config.yml.template` - tracked template for cloudflared runtime config (do NOT commit generated `cloudflared/config.yml` or credentials)
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

**Port 3923 already in use:**
```bash
# Find what's using it
sudo lsof -i :3923

# Stop conflicting service
sudo systemctl stop nginx  # or apache2
sudo systemctl disable nginx

# Or disable Funnel temporarily
sudo tailscale funnel --https=443 off

# Restart Copyparty
docker compose restart copyparty

# Re-enable Funnel
sudo tailscale funnel --bg --https=443 http://127.0.0.1:3923
```

**Can't reach services:**
```bash
# Test internal ports
curl http://localhost:2283  # Immich
curl http://localhost:3923  # Copyparty
curl http://localhost:3000  # Gitea
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

1. Install Immich mobile app → Point to your Immich hostname (e.g. `https://immich.example.com`) — use the `HOSTNAMES` you set in `.env`
2. Test Git workflows with Gitea at its hostname (e.g. `https://gitea.example.com`)
3. Set up backups (see BACKUPS.md)
4. Optionally share the Tailscale Funnel URL for Copyparty if you enabled it (see Part 5.2)

---

## References

- [Immich Documentation](https://immich.app/docs)
- [Gitea Documentation](https://docs.gitea.com)
- [Restic Documentation](https://restic.readthedocs.io)
- [Tailscale Funnel](https://tailscale.com/kb/1223/funnel)