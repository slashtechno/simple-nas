#!/bin/sh
# cloudflared/create_tunnel.sh
# Idempotent init script to create/reuse a Cloudflare Tunnel, render config.yml, and optionally create DNS records.
# Required env vars:
#   CF_API_TOKEN  - Cloudflare API token with DNS:Edit and Tunnels permissions (required)
#   CF_ACCOUNT_ID - Account ID (required when creating tunnel via API; optional if reusing existing)
#   CF_ZONE_ID    - Zone ID for DNS record creation (required if DNS creation is desired)
# Optional:
#   CF_TUNNEL_NAME - Tunnel name (default: pi-nas-tunnel)
#   HOSTNAMES     - Comma-separated hostnames (e.g. immich.example.com,gitea.example.com,copyparty.example.com)
#
# Notes:
# - This script is intended to run inside the cloudflared-init container with /etc/cloudflared mounted rw.
# - It is safe to run multiple times (idempotent): it will reuse existing credentials if present and will not recreate DNS records if already present.
# - The runtime container reads /etc/cloudflared/config.yml which this script generates.
#
# After creating this file: chmod +x cloudflared/create_tunnel.sh

set -eu
# Helper log
log() { printf '%s\n' "$*" >&2; }

: "${CF_API_TOKEN?CF_API_TOKEN is required (create token with DNS edit & tunnels permissions)}"
# CF_ZONE_ID is required only when DNS creation is desired; we still warn if missing when HOSTNAMES provided.
if [ -z "${HOSTNAMES:-}" ]; then
  log "Warning: HOSTNAMES not set. Script will still ensure tunnel credentials and config.yml are present, but no DNS entries will be created."
fi

CF_TUNNEL_NAME="${CF_TUNNEL_NAME:-pi-nas-tunnel}"
CLOUD_DIR="/etc/cloudflared"
mkdir -p "$CLOUD_DIR"
# Ensure permissions are permissive for creation; we'll tighten later.
umask 0077

# Check if credentials file already exists (indicating tunnel is already set up)
existing_json=$(ls "$CLOUD_DIR"/*.json 2>/dev/null | head -n1 || true)

if [ -n "$existing_json" ]; then
  TUNNEL_ID="$(basename "$existing_json" .json)"
  log "Found existing credentials file: $existing_json (tunnel id: $TUNNEL_ID)"
  log "Tunnel already configured. Skipping recreation."
  SKIP_CREATION=1
else
  log "No existing credentials found. Will create new tunnel."
  SKIP_CREATION=0
  TUNNEL_ID=""
fi

if [ -z "${CF_ACCOUNT_ID:-}" ]; then
  log "ERROR: CF_ACCOUNT_ID is required to create a tunnel via API. Please set CF_ACCOUNT_ID in your .env"
  exit 2
fi


if [ "$SKIP_CREATION" = "0" ]; then
  log "Creating new tunnel named '$CF_TUNNEL_NAME'..."
  
  # First check if a tunnel with this name already exists and delete it
  existing_tunnel=$(curl -s -X GET "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/cfd_tunnel?name=${CF_TUNNEL_NAME}" \
    -H "Authorization: Bearer ${CF_API_TOKEN}" \
    -H "Content-Type: application/json" 2>&1)
  
  EXISTING_ID=$(printf '%s' "$existing_tunnel" | jq -r '.result[0].id // empty' 2>/dev/null || true)
  
  if [ -n "$EXISTING_ID" ]; then
    log "Found existing tunnel with name '$CF_TUNNEL_NAME' (ID: $EXISTING_ID). Deleting it..."
    delete_response=$(curl -s -X DELETE "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/cfd_tunnel/${EXISTING_ID}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" 2>&1)
    
    delete_success=$(printf '%s' "$delete_response" | jq -r '.success // false' 2>/dev/null || echo "false")
    if [ "$delete_success" = "true" ]; then
      log "Successfully deleted existing tunnel. Waiting 5 seconds for API to propagate..."
      sleep 5
    else
      log "WARNING: Failed to delete existing tunnel. Response: $delete_response"
      log "Attempting to create anyway after waiting 3 seconds..."
      sleep 3
    fi
  fi
  
  # Try to create tunnel with retries
  CREATE_ATTEMPTS=0
  MAX_ATTEMPTS=3
  while [ $CREATE_ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    CREATE_ATTEMPTS=$((CREATE_ATTEMPTS + 1))
    log "Tunnel creation attempt $CREATE_ATTEMPTS of $MAX_ATTEMPTS..."
    
    # Create tunnel via Cloudflare API
    tunnel_response=$(curl -s -X POST "https://api.cloudflare.com/client/v4/accounts/${CF_ACCOUNT_ID}/cfd_tunnel" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "{\"name\":\"${CF_TUNNEL_NAME}\",\"config_src\":\"local\"}" 2>&1)
    
    # Extract tunnel id from response
    TUNNEL_ID=$(printf '%s' "$tunnel_response" | jq -r '.result.id // empty' 2>/dev/null || true)
    
    if [ -n "$TUNNEL_ID" ]; then
      log "API Response: $tunnel_response"
      log "Successfully created tunnel on attempt $CREATE_ATTEMPTS"
      break
    fi
    
    error_code=$(printf '%s' "$tunnel_response" | jq -r '.errors[0].code // "unknown"' 2>/dev/null || echo "unknown")
    
    if [ "$error_code" = "1013" ] && [ $CREATE_ATTEMPTS -lt $MAX_ATTEMPTS ]; then
      # Tunnel name still exists, wait and retry
      log "Tunnel name still in use (error 1013). Waiting 5 seconds before retry..."
      sleep 5
    else
      # Different error or last attempt
      error_msg=$(printf '%s' "$tunnel_response" | jq -r '.errors[0].message // "Unknown error"' 2>/dev/null || echo "Unknown error")
      log "ERROR: Failed to create tunnel after $CREATE_ATTEMPTS attempts. Error: $error_msg"
      log "Full response: $tunnel_response"
      exit 2
    fi
  done
  
  if [ -z "$TUNNEL_ID" ]; then
    log "ERROR: Failed to create tunnel after $MAX_ATTEMPTS attempts"
    exit 2
  fi
  
  log "Created tunnel id: $TUNNEL_ID"
  
  # Extract credentials_file from response
  credentials_file=$(printf '%s' "$tunnel_response" | jq -c '.result.credentials_file' 2>/dev/null || true)
  
  if [ -n "$credentials_file" ] && [ "$credentials_file" != "null" ]; then
    # Use the credentials file directly from the API
    echo "$credentials_file" > "$CLOUD_DIR/${TUNNEL_ID}.json"
    log "Created credentials file from API response"
  else
    log "ERROR: Could not extract credentials_file from tunnel creation response"
    exit 2
  fi
  
  # Since we created a new tunnel, delete old DNS records so they get recreated with the new tunnel ID
  if [ -n "${HOSTNAMES:-}" ] && [ -n "${CF_ZONE_ID:-}" ]; then
    log "Deleting old DNS records to recreate with new tunnel ID..."
    
    for host in "$IMMICH_HOST" "$GITEA_HOST" "$COPYPARTY_HOST"; do
      host=$(printf '%s' "$host" | tr -d '[:space:]')
      [ -z "$host" ] && continue
      
      # Find existing DNS records for this hostname
      records=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records?name=${host}" \
        -H "Authorization: Bearer ${CF_API_TOKEN}" \
        -H "Content-Type: application/json" 2>&1)
      
      # Delete each record found
      record_ids=$(printf '%s' "$records" | jq -r '.result[].id' 2>/dev/null || true)
      if [ -n "$record_ids" ]; then
        while IFS= read -r record_id; do
          [ -z "$record_id" ] && continue
          curl -s -X DELETE "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records/${record_id}" \
            -H "Authorization: Bearer ${CF_API_TOKEN}" \
            -H "Content-Type: application/json" >/dev/null 2>&1
          log "Deleted old DNS record for ${host} (id: ${record_id})"
        done <<EOF
$record_ids
EOF
      fi
    done
  fi
fi

# Verify credentials file was created
if [ ! -f "$CLOUD_DIR/${TUNNEL_ID}.json" ]; then
  log "ERROR: Credentials file was not created"
  exit 2
fi

log "Created credentials file: $CLOUD_DIR/${TUNNEL_ID}.json"

CREDENTIALS_FILE="$CLOUD_DIR/${TUNNEL_ID}.json"
if [ ! -f "$CREDENTIALS_FILE" ]; then
  # If credentials with a different name, attempt to find any json named like the tunnel id or fallback to first json.
  if [ -f "$CLOUD_DIR/$TUNNEL_ID.json" ]; then
    CREDENTIALS_FILE="$CLOUD_DIR/$TUNNEL_ID.json"
  else
    CREDENTIALS_FILE=$(ls "$CLOUD_DIR"/*.json 2>/dev/null | head -n1 || true)
  fi
fi

if [ -z "$CREDENTIALS_FILE" ] || [ ! -f "$CREDENTIALS_FILE" ]; then
  log "ERROR: No credentials JSON found in $CLOUD_DIR. Aborting."
  exit 3
fi

log "Using credentials file: $CREDENTIALS_FILE"

# Render config.yml into CLOUD_DIR/config.yml.
# HOSTNAMES is expected as comma-separated: immich.example.com,gitea.example.com,copyparty.example.com
# Parse hostnames manually since 'read -a' is bash-only
HOSTNAMES_STR="${HOSTNAMES:-}"
IMMICH_HOST=""
GITEA_HOST=""
COPYPARTY_HOST=""

if [ -n "$HOSTNAMES_STR" ]; then
  # Extract first hostname
  IMMICH_HOST=$(printf '%s' "$HOSTNAMES_STR" | cut -d',' -f1 | tr -d '[:space:]')
  # Extract second hostname
  GITEA_HOST=$(printf '%s' "$HOSTNAMES_STR" | cut -d',' -f2 | tr -d '[:space:]')
  # Extract third hostname
  COPYPARTY_HOST=$(printf '%s' "$HOSTNAMES_STR" | cut -d',' -f3 | tr -d '[:space:]')
fi

CONFIG_PATH="$CLOUD_DIR/config.yml"

log "Rendering $CONFIG_PATH"
cat > "$CONFIG_PATH" <<EOF
# Generated by create_tunnel.sh
tunnel: ${TUNNEL_ID}
credentials-file: /etc/cloudflared/${TUNNEL_ID}.json

ingress:
EOF

if [ -n "$IMMICH_HOST" ]; then
  cat >> "$CONFIG_PATH" <<EOF
  - hostname: ${IMMICH_HOST}
    service: http://immich_server:2283
EOF
fi

if [ -n "$GITEA_HOST" ]; then
  cat >> "$CONFIG_PATH" <<EOF
  - hostname: ${GITEA_HOST}
    service: http://gitea:3000
EOF
fi

if [ -n "$COPYPARTY_HOST" ]; then
  cat >> "$CONFIG_PATH" <<EOF
  - hostname: ${COPYPARTY_HOST}
    service: http://copyparty:3923
EOF
fi

# Optional: keep a default rule
cat >> "$CONFIG_PATH" <<'EOF'

  # Default rule (return 404)
  - service: http_status:404

# Optional originRequest config (uncomment & tune if needed)
# originRequest:
#   noHappyEyeballs: true
#   connectTimeout: 30s
EOF

# Ensure permissions so runtime cloudflared can read files
chmod 0644 "$CONFIG_PATH"
chmod 0644 "$CREDENTIALS_FILE" || true

# Optional: create DNS records for each hostname if CF_ZONE_ID is provided.
if [ -n "${CF_ZONE_ID:-}" ] && [ -n "${HOSTNAMES:-}" ]; then
  log "Ensuring DNS records exist in zone $CF_ZONE_ID for hostnames: $HOSTNAMES"

  # Process each hostname
  for host in "$IMMICH_HOST" "$GITEA_HOST" "$COPYPARTY_HOST"; do
    host=$(printf '%s' "$host" | tr -d '[:space:]')
    [ -z "$host" ] && continue

    log "Processing DNS for $host"

    # Prefer using cloudflared route command if available
    if command -v cloudflared >/dev/null 2>&1; then
      if cloudflared tunnel route dns "$TUNNEL_ID" "$host" >/dev/null 2>&1; then
        log "cloudflared route dns succeeded for $host"
        continue
      else
        log "cloudflared route dns failed or not supported for $host — falling back to Cloudflare API"
      fi
    fi

    # Check if a record exists
    existing=$(curl -s -X GET "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records?name=${host}" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" | jq -r '.result[] | .id' 2>/dev/null || true)

    if [ -n "$existing" ]; then
      log "DNS record already exists for ${host} (id: ${existing})"
      continue
    fi

    # Create a CNAME record pointing to the tunnel's cfargotunnel.com domain
    payload=$(cat <<JSON
{
  "type": "CNAME",
  "name": "${host}",
  "content": "${TUNNEL_ID}.cfargotunnel.com",
  "ttl": 1,
  "proxied": false
}
JSON
)
    resp=$(curl -s -X POST "https://api.cloudflare.com/client/v4/zones/${CF_ZONE_ID}/dns_records" \
      -H "Authorization: Bearer ${CF_API_TOKEN}" \
      -H "Content-Type: application/json" \
      -d "${payload}")

    ok=$(printf '%s' "$resp" | jq -r '.success' 2>/dev/null || echo "false")
    if [ "$ok" = "true" ]; then
      id=$(printf '%s' "$resp" | jq -r '.result.id' 2>/dev/null || echo "")
      log "Created DNS record for ${host} (id: ${id})"
    else
      log "WARNING: Failed to create DNS record for ${host}. Cloudflare response: $(printf '%s' "$resp" | tr '\n' ' ')"
      # Continue; do not exit so script remains idempotent in partial environments.
    fi
  done
else
  log "CF_ZONE_ID not provided or HOSTNAMES empty — skipping DNS creation."
fi

log "Init complete. Credentials: $CREDENTIALS_FILE, config: $CONFIG_PATH"
exit 0