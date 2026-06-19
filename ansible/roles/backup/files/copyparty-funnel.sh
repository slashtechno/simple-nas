#!/usr/bin/env bash
# scripts/copyparty-funnel.sh
# Usage: copyparty-funnel.sh enable|disable|status [port]
set -euo pipefail

PORT="${2:-${COPYPARTY_PORT:-3923}}"
FWD_URL="http://127.0.0.1:${PORT}"
SUDO="sudo"

command -v tailscale >/dev/null 2>&1 || { echo "tailscale CLI not found in PATH"; exit 1; }

case "${1:-}" in
  enable)
    echo "Enabling Tailscale Funnel for Copyparty -> ${FWD_URL}"
    $SUDO tailscale funnel --bg --https=443 "${FWD_URL}"
    echo "Funnel status:"
    $SUDO tailscale funnel status
    ;;
  disable)
    echo "Disabling Tailscale Funnel for https=443"
    $SUDO tailscale funnel --https=443 off
    echo "Funnel status:"
    $SUDO tailscale funnel status
    ;;
  status)
    echo "Funnel status:"
    $SUDO tailscale funnel status
    ;;
  *)
    echo "Usage: $0 {enable|disable|status} [port]"
    echo "Examples:"
    echo "  $0 enable          # enable funnel -> http://127.0.0.1:3923"
    echo "  $0 disable         # disable funnel for https=443"
    echo "  $0 enable 8080     # enable funnel -> http://127.0.0.1:8080"
    exit 2
    ;;
esac