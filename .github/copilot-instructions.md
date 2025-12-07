# Pi NAS Project - AI Agent Instructions

Self-hosted single-user home NAS on Raspberry Pi 4 with Immich (photos), Copyparty (files), Gitea (git), and automated backups.

## Architecture Overview

**Service Stack** (Docker Compose):
- `immich_server` (port 2283) → PostgreSQL + Valkey (Redis) + ML service
- `gitea` (port 3000) → Git hosting
- `copyparty` (port 3923) → File sharing
- `cloudflared` (init + runtime) → Cloudflare Tunnel for secure public access

**Access Pattern**: `Internet → Cloudflare Tunnel (cloudflared) → Docker services (by hostname)`
- DNS: `immich.slashtechno.com`, `gitea.slashtechno.com`, `copyparty.slashtechno.com` → CNAME to `{TUNNEL_ID}.cfargotunnel.com`
- All services on internal `services` bridge network; cloudflared bridges to Cloudflare edge

## Critical Implementation Details

### Cloudflare Tunnel Setup (cloudflared/)
**Pattern**: API-based tunnel (not cert.pem). Init container creates tunnel + credentials, runtime container connects.

- `create_tunnel.sh`: POSIX shell script (not bash) that:
  1. Deletes existing tunnel if name conflict (with retries, 5s wait between attempts)
  2. Creates new tunnel via POST to `/cfd_tunnel` API
  3. Extracts `credentials_file` JSON from response (only available during creation)
  4. Renders `config.yml` from template with ingress rules for 3 services
  5. Creates/updates DNS records via Cloudflare API (deletes old ones if tunnel recreated)
  
- `Dockerfile.init`: Alpine + cloudflared binary (multi-stage from official image) + curl/jq + sh support
- `Dockerfile.runtime`: Alpine + cloudflared binary + debugging tools (curl, netcat, tcpdump, bash)
- `config.yml.template`: Jinja2-style template with `{{TUNNEL_ID}}`, `{{IMMICH_HOST}}`, etc.
- `config.yml`: Generated at runtime; contains tunnel ID + ingress routing rules

**Required env vars** (in `.env`):
- `CF_API_TOKEN` (account-level with Tunnels:Edit, DNS:Edit permissions)
- `CF_ACCOUNT_ID` (numeric account ID)
- `CF_ZONE_ID` (zone ID for slashtechno.com)
- `CF_TUNNEL_NAME` (default: pi-nas-tunnel; if exists, deleted and recreated)
- `HOSTNAMES` (comma-separated: immich.slashtechno.com,gitea.slashtechno.com,copyparty.slashtechno.com)

**Key gotchas**:
- Tunnel credentials only returned during POST creation, not GET. If credentials file missing, tunnel won't authenticate.
- Cloudflare API has eventual consistency (~5s) after deletion; retries + sleep needed before recreating same-name tunnel
- DNS records must point to `{TUNNEL_ID}.cfargotunnel.com`, not generic `tunnel.cloudflare.com`
- POSIX shell (not bash) required in init container (no `read -a` arrays, use `cut` for parsing)

### Docker Compose Orchestration
- **Init pattern**: `cloudflared-init` runs once (restart: "no"), generates credentials + config; `cloudflared` depends on it
- **Network**: All services on `services` bridge network; cloudflared uses same for accessing backends
- **Env file**: `.env` sourced by all services; `.env.example` documents all variables

### Backup Scripts (scripts/)
- `backup-restic-local.sh` (daily) → restic snapshot to `/mnt/backup` (HDD)
- `backup-restic-cloud.sh` (weekly) → restic to cloud storage (Google Drive via `backup-paths.txt`)
- `backup-services.sh` / `restore-services.sh` → Start/stop services during backup
- `copyparty-funnel.sh` → Optional Tailscale Funnel exposure for file sharing

## Developer Workflows

**First-time setup**:
```bash
cp .env.example .env
# Edit .env with CF_API_TOKEN, CF_ACCOUNT_ID, CF_ZONE_ID
docker compose up --build
```

**Tunnel debugging** (after containers up):
```bash
docker compose logs cloudflared -f               # Monitor tunnel connections
docker compose exec cloudflared curl http://immich_server:2283  # Test backend reachability
docker compose exec cloudflared cat /etc/cloudflared/config.yml  # Check routing rules
```

**Tunnel recreation** (if deleted/broken in Cloudflare UI):
```bash
rm -f cloudflared/*.json cloudflared/config.yml
docker compose down && docker compose up --build  # Init script recreates tunnel
```

**Full cleanup** (before fresh start):
```bash
# Via Cloudflare API: delete old tunnels by name, delete old DNS records
curl -X DELETE "https://api.cloudflare.com/client/v4/accounts/$CF_ACCOUNT_ID/cfd_tunnel/{TUNNEL_ID}" \
  -H "Authorization: Bearer $CF_API_TOKEN"
rm -f cloudflared/*.json cloudflared/config.yml
docker compose down && docker compose up --build
```

## Key Files & Patterns

- **docker-compose.yml**: Single file; no depends_on chains (services start in parallel)
- **SETUP_GUIDE.md**: Step-by-step onboarding (networking, storage mounts, Cloudflare setup)
- **BACKUPS.md**: Restic workflow, storage constraints, disaster recovery
- **.env.example**: Template with all vars; human-readable comments
- **scripts/**: All executable; designed for cron (immich backup, gitea updates, etc.)

## Design Philosophy

- **Single-user**: No multi-tenancy, no role-based access control
- **Simple**: Few services, straightforward networking (Docker bridge + Tailscale)
- **Reliable**: Health checks, automatic restarts, encrypted backups
- **Replicable**: Entire setup in one repo; easily redeploy to new Pi 