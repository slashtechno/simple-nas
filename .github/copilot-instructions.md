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
- **Critical**: DNS records must have `proxied: true` (Cloudflare orange cloud icon), not just pointing to tunnel
- All services on internal `services` bridge network; cloudflared bridges to Cloudflare edge

## Critical Implementation Details

### Cloudflare Tunnel Setup (cloudflared/)
**Pattern**: API-based tunnel with `config_src: local` (routes defined in config.yml, not Cloudflare dashboard).

- `create_tunnel.sh`: POSIX shell script (not bash) that:
  1. Checks for existing **active** tunnels (filters out soft-deleted ones via `deleted_at == null`)
  2. Creates new tunnel via POST to `/cfd_tunnel` API with `config_src: local`
  3. Extracts `credentials_file` JSON from response (only available during POST, not GET)
  4. Renders `config.yml` with ingress rules for 3 services + default 404 rule
  5. Creates/updates DNS records with `proxied: true` for Cloudflare routing
  6. Parses `HOSTNAMES` env var (comma-separated) into individual service hostnames
  
- `Dockerfile.init`: Alpine + cloudflared binary + curl/jq + sh support
- `Dockerfile.runtime`: Alpine + cloudflared binary + debugging tools (curl, netcat, tcpdump, bash)
- `config.yml`: Generated at runtime; contains tunnel ID + ingress routing rules (read by runtime cloudflared)
- `config.yml.template`: Placeholder; actual template is generated in script

**Required env vars** (in `.env`):
- `CF_API_TOKEN` (account-level with Tunnels:Edit, DNS:Edit permissions)
- `CF_ACCOUNT_ID` (numeric account ID)
- `CF_ZONE_ID` (zone ID for slashtechno.com)
- `CF_TUNNEL_NAME` (default: pi-nas-tunnel)
- `HOSTNAMES` (comma-separated: immich.slashtechno.com,gitea.slashtechno.com,copyparty.slashtechno.com)

**Key gotchas**:
- **DNS must be proxied**: `proxied: true` is required for Cloudflare routing to work (orange cloud)
- Tunnel credentials only returned during POST creation, not GET. Stored in `{TUNNEL_ID}.json`
- Soft-deleted tunnels appear in API list but have `deleted_at` set; filter these when checking for conflicts
- Init container runs once (`restart: "no"`); use `docker compose restart cloudflared-init` to re-run
- DNS record conflicts: script auto-detects wrong tunnel ID and deletes+recreates with correct one
- Runtime cloudflared automatically registers routes from config.yml with Cloudflare edge

### Docker Compose Orchestration
- **Init pattern**: `cloudflared-init` (restart: "no") generates credentials + config.yml, then `cloudflared` reads them
- **Network**: All services on `services` bridge network (hostname-based routing)
- **Env file**: `.env` sourced by all services; all services have `env_file: - .env`
- **No depends_on chains**: Services can start in parallel (immich needs postgres/redis but not cloudflared)

### Backup Scripts (scripts/)
- `backup-restic-local.sh` (daily) → restic snapshot to `/mnt/backup` (HDD)
- `backup-restic-cloud.sh` (weekly) → restic to cloud storage (Google Drive)
- `backup-services.sh` / `restore-services.sh` → Stop/start services during backup (prevent data inconsistency)
- `copyparty-funnel.sh` → Optional Tailscale Funnel exposure for file sharing

## Developer Workflows

**Tunnel debugging**:
```bash
docker compose logs cloudflared -f                    # Monitor connections
docker compose logs cloudflared-init                  # Check init script output
docker compose exec cloudflared curl http://immich_server:2283  # Test backend reachability
cat cloudflared/config.yml                            # Verify ingress rules
```

**Tunnel recreation** (if corrupted):
```bash
rm -f cloudflared/*.json cloudflared/config.yml
docker compose restart cloudflared-init               # Re-run init script
```

**DNS route mismatch** (if DNS points to old tunnel ID):
```bash
# Script auto-detects and fixes this, but if manual:
rm cloudflared/config.yml
docker compose restart cloudflared-init               # Recreates DNS with correct tunnel ID
```

**Tunnel conflict resolution** (if tunnel already exists in Cloudflare):
```bash
# Init script will error and suggest:
docker compose run --rm --entrypoint sh cloudflared-init -c \
  'curl -X DELETE "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/{TUNNEL_ID}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}"'
docker compose up -d
```

## Key Files & Patterns

- **docker-compose.yml**: Single file orchestration (no distributed config)
- **cloudflared/create_tunnel.sh**: Idempotent tunnel setup (safe to re-run, filters soft-deleted tunnels, auto-fixes DNS)
- **SETUP_GUIDE.md**: Step-by-step onboarding (Cloudflare account setup, DNS config, storage mounts)
- **BACKUPS.md**: Restic workflow, storage constraints, restore procedures
- **.env.example**: All required variables documented with comments
- **scripts/**: All bash, designed for cron jobs and manual operations

## Design Philosophy

- **Single-user**: No multi-tenancy, no RBAC
- **Reliable**: Health checks, automatic restarts, daily local backups + weekly cloud backups
- **Simple**: Local config sources (no complex orchestration), straightforward routing (hostname → service)
- **Replicable**: Entire setup in one repo, can redeploy to new Pi by copying .env and data
- **Failure-tolerant**: DNS auto-correction, soft-delete handling for tunnels, idempotent scripts
 