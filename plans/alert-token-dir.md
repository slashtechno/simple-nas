# Alert token folder on pinas

Status: waits for the owner's next pinas deploy.

The alert tokens moved from `/opt/services/ntfy-token` and `/opt/services/unlock-ntfy-token` into `/opt/services/alert-tokens/<sender>`. `alert.sh` takes the sender as its first argument. The old files are in no exclude list now, so a backup run would carry them offsite until removed.

1. `just deploy common,backup,connectivity_watchdog,encryption --limit pinas` (all four: each runs `alert.sh` with the new arguments).
2. On pinas: `sudo rm -f /opt/services/ntfy-token /opt/services/unlock-ntfy-token`.
3. Delete this file.
